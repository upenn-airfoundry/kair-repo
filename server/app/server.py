import os
import sys
from typing import Optional
import bcrypt
import logging
import uuid

import shelve

server = os.getenv("SERVER", "localhost")

# Feature flags
SKIP_ENRICHMENT = os.getenv("SKIP_ENRICHMENT", "true").lower() in ("1", "true", "yes")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "http://" + server + ":3000")
SESSION_TTL_SECONDS = int(os.environ.get("SESSION_TTL_SECONDS", "1800"))  # 30 min default

logging.info("Starting server with the following configuration:")
logging.info(f"  SERVER: {server}")
logging.info(f"  SKIP_ENRICHMENT: {SKIP_ENRICHMENT}")
logging.info(f"  ALLOWED_ORIGIN: {ALLOWED_ORIGIN}")
logging.info(f"  SESSION_TTL_SECONDS: {SESSION_TTL_SECONDS}")
    
# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import tornado.ioloop
import tornado.web
import tornado.options
from torndsession.session import SessionMixin
import json
from datetime import datetime
from dotenv import load_dotenv, find_dotenv

# Load environment variables from .env file
_ = load_dotenv(find_dotenv())

from backend.graph_db import GraphAccessor
from backend.enrichment_daemon import EnrichmentDaemon
from prompts.llm_prompts import PeoplePrompts
from qa.answer_question import AnswerQuestionHandler

state = shelve.open("server_state.db", writeback=True)

# Defer importing search until runtime to avoid DB init at import time

# Configure logging
logging.basicConfig(level=logging.INFO)


class BaseHandler(tornado.web.RequestHandler, SessionMixin):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.set_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.set_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.set_header("Access-Control-Allow-Credentials", "true")
    
    def options(self, *args, **kwargs):
        self.set_status(204)
        self.finish()

    def prepare(self):
        global graph_accessor
        if os.getenv("SKIP_ENRICHMENT", "").lower() in ("1", "true", "yes"):
            return
        if graph_accessor is None and self.request.uri != "/health":
            self.set_status(503)
            self.finish({"error": "Service temporarily unavailable: database is not configured"})
            return

    def get_json(self):
        try:
            return json.loads(self.request.body)
        except json.JSONDecodeError:
            return None
        
    def is_session_expired(self):
        session = getattr(self, "session", None)
        if not session:
            return True
        # expires_at = session.get("expires_at")
        # if not expires_at or time.time() > expires_at:
        #     return True
        return False

    def is_authenticated(self):
        # Checks if session exists and is not expired
        session_id = self.get_cookie("msid")
        if session_id:
            session_data = state.get(session_id)
            if session_data and "username" in session_data:
                self.session.session = session_data
                # Ensure user_id is available for other handlers
                if "user_id" not in self.session.session:
                     (user_id, _) = graph_accessor.get_user_and_project_ids(self.session.session.get("email"))
                     self.session.session["user_id"] = user_id
                return True
        return False

    def renew_session(self):
        """Refresh the msid cookie max-age to keep the session alive."""
        try:
            session_id = self.get_cookie("msid")
            if not session_id:
                return
            # Ensure the session is still present in our shelve store
            sess = state.get(session_id)
            if not sess:
                return
            # Refresh cookie expiry
            self.set_cookie(
                "msid",
                session_id,
                expires_days=None,
                max_age=SESSION_TTL_SECONDS,
                httponly=True,
                secure=False,  # set True if serving over HTTPS
            )
            # Optionally track last_seen
            try:
                sess["last_seen"] = datetime.utcnow().isoformat()  # noqa: F405 (datetime already imported)
                state[session_id] = sess
                state.sync()
            except Exception:
                pass
        except Exception:
            pass

    def redirect_to_login(self):
        #self.redirect("/login")  # Adjust path as needed
        pass

########### Main ###########

# Initialize the GraphAccessor, but don't crash if DB is unavailable (or skip)
graph_accessor: Optional[GraphAccessor] = None
question_handlers = {}
try:
    graph_accessor = GraphAccessor()
    
    if not SKIP_ENRICHMENT:
        EnrichmentDaemon.initialize_enrichment(graph_accessor)

except Exception as e:
    logging.error(f"Failed to initialize database connection: {e}")

class LoginHandler(BaseHandler):
    def post(self):
        try:
            data = self.get_json()
            email = data.get("email")
            password = data.get("password")
            if not email or not password:
                self.set_status(400)
                self.write({"error": "'email' and 'password' are required"})
                return

            if graph_accessor is None:
                logging.error("Login attempted but database is not configured (graph_accessor is None)")
                self.set_status(503)
                self.write({
                    "success": False,
                    "message": "Service temporarily unavailable: database is not configured"
                })
                return

            user = graph_accessor.exec_sql(
                "SELECT name, organization, avatar, password_hash FROM users WHERE email = %s;", (email,)
            )
            if not user:
                self.set_status(401)
                self.write({"success": False, "message": "Invalid credentials"})
                return

            password_hash = user[0][3].encode("utf-8")
            if bcrypt.checkpw(password.encode("utf-8"), password_hash):
                # Create a unique session
                session_id = str(uuid.uuid4())
                session = {}
                
                session["session_id"] = session_id
                session["username"] = user[0][0]
                session["email"] = email

                # Set session ID as a cookie for the client
                self.set_cookie("msid", session_id, expires_days=None, max_age=SESSION_TTL_SECONDS, httponly=True, secure=False)
                
                profile = graph_accessor.get_user_profile(email)  # Load user profile if needed
                session["profile"] = profile
                if profile is not None and 'publications' not in profile:
                    scholar_id = profile.get("scholar_id") if profile else None

                    if scholar_id:
                        pubs = PeoplePrompts.get_person_publications(graph_accessor, user[0][0], user[0][1], scholar_id)

                        if session and "profile" in session and pubs:
                            session['profile']["publications"] = pubs
                        
                results = graph_accessor.get_user_and_project_ids(email)
                
                if results is None:
                    self.set_status(500)
                    self.write({"error": "Failed to retrieve user and project IDs"})
                    return
                (user_id, project_id) = results

                # Get project details
                project_details = graph_accessor.exec_sql(
                    "SELECT project_name, project_description FROM projects WHERE project_id = %s;", (project_id,)
                )
                project_name = ""
                project_description = ""
                if project_details:
                    project_name = project_details[0][0]
                    project_description = project_details[0][1]

                state[session_id] = session
                state.sync()  # Force the session data to be written to disk immediately
                self.session.session = session

                question_handlers[session_id] = AnswerQuestionHandler(graph_accessor, user[0][0], session['profile'], user_id, project_id)

                self.write({
                    "success": True, 
                    "user": {
                        "name": user[0][0],
                        "organization": user[0][1],
                        "avatar": user[0][2],
                        "profile": self.session.get("profile", {}),
                        "project_id": project_id,
                        "project_name": project_name,
                        "project_description": project_description,
                    },
                    "session_id": session_id,
                    "message": "Login successful"
                })
            else:
                self.set_status(401)
                self.write({"success": False, "message": "Invalid credentials"})
        except Exception as e:
            self.set_status(500)
            self.write({"error": f"An error occurred: {e}"})

class CreateAccountHandler(BaseHandler):
    def post(self):
        try:
            data = self.get_json()
            email = data.get("userId") or data.get("email")
            avatar = data.get("avatarUrl", "")
            organization = data.get("organization", "")
            name = data.get("name", "")
            password = data.get("password")
            if not email or not password or not avatar or not organization or not name:
                self.set_status(400)
                self.write({"error": "'userId' (or 'email') and 'password' as well as 'avatar', 'name', and 'organization' are required"})
                return

            # Ensure database is available
            if graph_accessor is None:
                logging.error("Create account attempted but database is not configured (graph_accessor is None)")
                self.set_status(503)
                self.write({
                    "success": False,
                    "message": "Service temporarily unavailable: database is not configured"
                })
                return

            # Check if user already exists
            existing = graph_accessor.exec_sql(
                "SELECT 1 FROM users WHERE email = %s;", (email,)
            )
            if existing:
                self.set_status(409)
                self.write({"success": False, "message": "Account already exists"})
                return

            # Hash the password with bcrypt
            password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            graph_accessor.execute(
                "INSERT INTO users (email, password_hash, name, organization, avatar) VALUES (%s, %s, %s, %s, %s);",
                (email, password_hash, name, organization, avatar)
            )

            # Create an initial user profile
            graph_accessor.save_user_profile(email, PeoplePrompts.get_person_profile(name, organization))
            graph_accessor.commit()
            self.write({"success": True, "message": "Account created"})
        except Exception as e:
            self.set_status(500)
            self.write({"error": f"An error occurred: {e}"})

class HealthCheckHandler(BaseHandler):
    def get(self):
        self.write({"status": "healthy"})

class DbPingHandler(BaseHandler):
    def get(self):
        try:
            if graph_accessor is None:
                self.set_status(503)
                self.write({"ok": False, "error": "database is not configured"})
                return
            result = graph_accessor.exec_sql("SELECT 1;")
            self.write({"ok": True, "result": result[0][0] if result else None})
        except Exception as e:
            self.set_status(500)
            self.write({"ok": False, "error": f"{e}"})

class FindRelatedEntitiesByTagHandler(BaseHandler):
    def get(self):
        # Guard: only allow if session is valid and not expired
        if self.is_session_expired() or not self.is_authenticated():
            self.set_status(401)
            self.write({"error": "Session expired or not authenticated"})
            self.redirect_to_login()
            return
        self.renew_session()  # Renew expiration on access

        tag_name = self.get_argument('tag_name', None)
        query = self.get_argument('query', None)
        k = int(self.get_argument('k', 10))

        if not tag_name or not query:
            self.set_status(400)
            self.write({"error": "Both 'tag_name' and 'query' parameters are required"})
            return

        query_embedding = graph_accessor.generate_embedding(query)
        results = graph_accessor.find_entities_by_tag_embedding(query_embedding, tag_name, k)
        self.write({"results": results})

class FindRelatedEntitiesHandler(BaseHandler):
    def get(self):
        # Guard: only allow if session is valid and not expired
        if self.is_session_expired() or not self.is_authenticated():
            self.set_status(401)
            self.write({"error": "Session expired or not authenticated"})
            self.redirect_to_login()
            return
        self.renew_session()  # Renew expiration on access
        query = self.get_argument('query', None)
        k = int(self.get_argument('k', 10))
        entity_type = self.get_argument('entity_type', None)
        keywords = self.get_argument('keywords', None)
        
        if keywords:
            keywords = keywords.split(',')
            if keywords[0] == '':
                keywords = None
        
        if not query:
            self.set_status(400)
            self.write({"error": "'query' parameter is required"})
            return
            
        logging.debug("Find related entities: " + query)
        if keywords:
            logging.debug("Keywords: " + str(keywords))
        results = graph_accessor.find_related_entities(query, k, entity_type, keywords)
        self.write({"results": results})

class AddToCrawlQueueHandler(BaseHandler):
    def post(self):
        # Guard: only allow if session is valid and not expired
        if self.is_session_expired() or not self.is_authenticated():
            self.set_status(401)
            self.write({"error": "Session expired or not authenticated"})
            self.redirect_to_login()
            return
        self.renew_session()  # Renew expiration on access

        data = self.get_json()
        if not data or 'url' not in data:
            self.set_status(400)
            self.write({"error": "'url' parameter is required"})
            return

        url = data['url']
        comment = data.get('comment')

        # Check if the URL already exists in the crawl_queue table
        exists = graph_accessor.exec_sql("SELECT 1 FROM crawl_queue WHERE url = %s;", (url,))
        if len(exists) > 0:
            self.write({"message": "URL already exists in the crawl queue"})
            return

        # Insert the URL into the crawl_queue table
        graph_accessor.execute(
            "INSERT INTO crawl_queue (create_time, url, comment) VALUES (%s, %s, %s);",
            (datetime.now().date(), url, comment)
        )
        graph_accessor.commit()
        self.write({"message": "URL added to crawl queue"})

class CrawlFilesHandler(BaseHandler):
    def post(self):
        # Guard: only allow if session is valid and not expired
        if self.is_session_expired() or not self.is_authenticated():
            self.set_status(401)
            self.write({"error": "Session expired or not authenticated"})
            self.redirect_to_login()
            return
        self.renew_session()  # Renew expiration on access
        try:
            # Lazy import to avoid prompts dependency at startup
            from crawl.web_fetch import fetch_and_crawl_frontier
            fetch_and_crawl_frontier()
            self.write({"message": "Crawling completed successfully"})
        except Exception as e:
            self.set_status(500)
            self.write({"error": f"An error occurred during crawling: {e}"})

class ParsePDFsAndIndexHandler(BaseHandler):
    def post(self):
        # Guard: only allow if session is valid and not expired
        if self.is_session_expired() or not self.is_authenticated():
            self.set_status(401)
            self.write({"error": "Session expired or not authenticated"})
            self.redirect_to_login()
            return
        self.renew_session()  # Renew expiration on access
        try:
            # if parse_files_and_index is None or SKIP_ENRICHMENT:
            #     self.set_status(503)
            #     self.write({"error": "Parsing not available at startup"})
            #     return
            EnrichmentDaemon.parse_files_and_index(use_aryn=False)
            self.write({"message": "PDF parsing and indexing completed successfully"})
        except Exception as e:
            self.set_status(500)
            self.write({"error": f"An error occurred during parsing and indexing: {e}"})

class UncrowledEntriesHandler(BaseHandler):
    def get(self):
        try:
            query = """
                SELECT cq.id, cq.create_time, cq.url, cq.comment
                FROM crawl_queue cq
                LEFT JOIN crawled c ON cq.id = c.id
                WHERE c.id IS NULL;
            """
            uncrawled_entries = graph_accessor.exec_sql(query)
            results = [
                {"id": row[0], "create_time": row[1], "url": row[2], "comment": row[3]}
                for row in uncrawled_entries
            ]
            self.write({"uncrawled_entries": results})
        except Exception as e:
            self.set_status(500)
            self.write({"error": f"An error occurred while fetching uncrawled entries: {e}"})

class GetAssessmentCriteriaHandler(BaseHandler):
    def get(self):
        # Guard: only allow if session is valid and not expired
        if self.is_session_expired() or not self.is_authenticated():
            self.set_status(401)
            self.write({"error": "Session expired or not authenticated"})
            self.redirect_to_login()
            return
        self.renew_session()  # Renew expiration on access
        try:
            name = self.get_argument('name', None)
            criteria = graph_accessor.get_assessment_criteria(name)
            if criteria:
                self.write({"criteria": criteria})
            else:
                if name:
                    self.set_status(404)
                    self.write({"error": "No criteria found for the given name"})
                else:
                    self.set_status(404)
                    self.write({"error": "Please create some assessment criteria"})
        except Exception as e:
            self.set_status(500)
            self.write({"error": f"An error occurred: {e}"})

class AddAssessmentCriterionHandler(BaseHandler):
    def post(self):
        # Guard: only allow if session is valid and not expired
        if self.is_session_expired() or not self.is_authenticated():
            self.set_status(401)
            self.write({"error": "Session expired or not authenticated"})
            self.redirect_to_login()
            return
        self.renew_session()  # Renew expiration on access
        try:
            data = self.get_json()
            name = data.get('name')
            scope = data.get('scope')
            prompt = data.get('prompt')
            promise = data.get('promise', 1.0)

            if not name or not prompt or not scope:
                self.set_status(400)
                self.write({"error": "'name', 'scope', and 'prompt' fields are required"})
                return
            
            logging.info("Adding assessment criterion with name: " + name)
            logging.debug("Scope: " + scope)
            logging.debug("Prompt: " + prompt)

            criterion_id = EnrichmentDaemon.add_enrichment_task(name, prompt, scope, promise)

            self.write({
                "message": "New assessment criterion added successfully",
                "criterion_id": criterion_id
            })
        except Exception as e:
            self.set_status(500)
            self.write({"error": f"An error occurred: {e}"})

class AddEnrichmentHandler(BaseHandler):
    def post(self):
        # Guard: only allow if session is valid and not expired
        if self.is_session_expired() or not self.is_authenticated():
            self.set_status(401)
            self.write({"error": "Session expired or not authenticated"})
            self.redirect_to_login()
            return
        self.renew_session()  # Renew expiration on access
        try:
            data = self.get_json()
            name = data.get('name')
            EnrichmentDaemon.run_enrichment_task(name)
            self.write({"message": "All enrichment tasks queued"})
        except Exception as e:
            self.set_status(500)
            self.write({"error": f"An error occurred: {e}"})

class ExpandSearchHandler(BaseHandler):
    async def post(self):
        # Guard: only allow if session is valid and not expired
        if self.is_session_expired() or not self.is_authenticated():
            self.set_status(401)
            self.write({"error": "Session expired or not authenticated"})
            self.redirect_to_login()
            return
        self.renew_session()  # Renew expiration on access
        try:
            # Ensure search module can access the same graph accessor
            try:
                import search as search_module
                search_module.graph_accessor = graph_accessor
            except Exception:
                pass
            data = self.get_json()
            user_prompt = data.get('prompt')
            # Optional: task to target with this interaction
            selected_task_id_raw = data.get('selected_task_id')
            selected_task_id = None
            try:
                if selected_task_id_raw is not None:
                    selected_task_id = int(selected_task_id_raw)
            except Exception:
                selected_task_id = None
            
            if not user_prompt:
                logging.error("'prompt' parameter is missing")
                self.set_status(400)
                self.write({"error": "'prompt' parameter is required"})
                return

            session = self.session.session
            
            # user_profile = session.get("profile", {})
            email = session.get("email")
            
            (user_id, project_id) = graph_accessor.get_user_and_project_ids(email)

            session_id = self.get_cookie("msid")
            
            if session_id not in question_handlers:
                self.set_status(500)
                self.write({"error": "Session expired, please log in again"})
                return

            question_handlers[session_id].set_project_id(project_id)

            try:
                (answer, answer_type) = await question_handlers[session_id].answer_question(
                    user_prompt,
                    selected_task_id=selected_task_id
                )

                if answer is not None:
                    if answer_type == 1:
                        logging.info("Answer created a task")
                        self.write({
                            "data": {
                                "message": answer,
                                "refresh_project": project_id
                            }
                        })
                    else:
                        logging.info("Answer returned without criteria")
                        self.write({
                            "data": {
                                "message": answer
                            }
                        })
                else:
                    logging.error("Answer returned was None")
                    self.write({"error": "No relevant answers were found"})
                    return
            except Exception as e:
                logging.error(f"Error while answering question: {e}")
                self.set_status(500)
                self.write({"error": f"An error occurred while processing the question: {e}"})
                return     
        except Exception as e:
            self.set_status(500)
            self.write({"error": f"An error occurred: {e}"})
            return       
            
class StartSchedulerHandler(BaseHandler):
    def post(self):
        try:
            # TODO: Implement scheduler start logic
            self.write({"message": "Scheduler started successfully"})
        except Exception as e:
            self.set_status(500)
            self.write({"error": f"Failed to start scheduler: {e}"})

class StopSchedulerHandler(BaseHandler):
    def post(self):
        try:
            # TODO: Implement scheduler stop logic
            self.write({"message": "Scheduler stopped successfully"})
        except Exception as e:
            self.set_status(500)
            self.write({"error": f"Failed to stop scheduler: {e}"})

class AccountInfoHandler(BaseHandler):
    def get(self):
        if self.is_session_expired() or not self.is_authenticated():
            self.set_status(401)
            self.write({"error": "Session expired or not authenticated"})
            return
        email = self.session.session.get("email")
        user_id = graph_accessor.exec_sql("SELECT user_id FROM users WHERE email = %s;", (email,))[0][0]
        profile = graph_accessor.get_user_profile(email)
        projects = graph_accessor.get_user_projects(user_id)
        self.write({
            "user": {
                "name": self.session.session.get("username"),
                "email": email,
                "profile": profile,
                "projects": projects
            }
        })

class UpdateAccountHandler(BaseHandler):
    def post(self):
        if self.is_session_expired() or not self.is_authenticated():
            self.set_status(401)
            self.write({"error": "Session expired or not authenticated"})
            return
        data = self.get_json()
        email = self.session.session.get("email")
        graph_accessor.update_user_profile(email, data.get("profile", {}))
        self.write({"success": True})

class SelectProjectHandler(BaseHandler):
    def post(self):
        """Select an existing project for the current user and persist it in the profile."""
        if self.is_session_expired() or not self.is_authenticated():
            self.set_status(401); self.write({"error": "Session expired or not authenticated"}); return
        try:
            data = self.get_json()
            project_id = int(data.get("project_id", 0))
            if not project_id:
                self.set_status(400); self.write({"error": "Missing project_id"}); return

            email = self.session.session.get("email")
            user_id = graph_accessor.exec_sql("SELECT user_id FROM users WHERE email = %s;", (email,))[0][0]
            # Validate membership
            rows = graph_accessor.exec_sql(
                "SELECT 1 FROM user_projects WHERE user_id = %s AND project_id = %s;",
                (user_id, project_id)
            )
            if not rows:
                self.set_status(403); self.write({"error": "Not a member of this project"}); return

            # Persist selection
            graph_accessor.set_selected_project_for_user(user_id, project_id)

            # Update session + handler
            self.session.session["project_id"] = project_id
            session_id = self.get_cookie("msid")
            if session_id in question_handlers:
                question_handlers[session_id].set_project_id(project_id)
            state[session_id] = self.session.session; state.sync()

            proj = graph_accessor.exec_sql(
                "SELECT project_name, project_description FROM projects WHERE project_id = %s;",
                (project_id,)
            )
            self.write({
                "success": True,
                "project": {
                    "id": project_id,
                    "name": proj[0][0] if proj else "",
                    "description": proj[0][1] if proj else ""
                }
            })
        except Exception as e:
            self.set_status(500)
            self.write({"error": f"An error occurred: {e}"})

class ListProjectsHandler(BaseHandler):
    def get(self):
        if self.is_session_expired() or not self.is_authenticated():
            self.set_status(401)
            self.write({"error": "Session expired or not authenticated"})
            return
        # If mine=1, return the full set of this user's projects (no limit)
        mine = self.get_argument("mine", "").lower() in ("1", "true", "yes")
        if mine:
            email = self.session.session.get("email")
            user_id = graph_accessor.exec_sql("SELECT user_id FROM users WHERE email = %s;", (email,))[0][0]
            projects = graph_accessor.get_user_projects(user_id)
            self.write({"projects": projects})
            return

        search = self.get_argument("search", "")
        projects = graph_accessor.search_projects(search)
        self.write({"projects": projects})

class CreateProjectHandler(BaseHandler):
    def post(self):
        if self.is_session_expired() or not self.is_authenticated():
            self.set_status(401); self.write({"error": "Session expired or not authenticated"}); return
        try:
            data = self.get_json()
            name = data.get("name")
            description = data.get("description", "")
            email = self.session.session.get("email")
            user_id = graph_accessor.exec_sql("SELECT user_id FROM users WHERE email = %s;", (email,))[0][0]
            project_id = graph_accessor.create_project(name, description, user_id)
            # Persist new selection in profile
            graph_accessor.set_selected_project_for_user(user_id, project_id)
            # Update session cached handler project if exists
            session_id = self.get_cookie("msid")
            if session_id in question_handlers:
                question_handlers[session_id].set_project_id(project_id)
            # Reflect selection in session
            self.session.session["project_id"] = project_id
            state[session_id] = self.session.session; state.sync()
            self.write({"project_id": project_id})
        except Exception as e:
            self.set_status(500)
            self.write({"error": f"An error occurred: {e}"})

class ProjectTaskHandler(BaseHandler):
    def post(self, project_id):
        """Create a new project task."""
        if not self.is_authenticated():
            self.set_status(401); self.write({"error": "Not authenticated"}); return
        
        data = self.get_json()
        name = data.get("name")
        description = data.get("description")
        schema = data.get("schema")

        if not all([name, description, schema]):
            self.set_status(400); self.write({"error": "Missing name, description, or schema"}); return

        task_id = graph_accessor.create_project_task(int(project_id), name, description, schema)
        self.write({"success": True, "task_id": task_id})

    def get(self, project_id):
        """Retrieve all tasks for a project or find the most related one."""
        if not self.is_authenticated():
            self.set_status(401); self.write({"error": "Not authenticated"}); return
        
        description = self.get_argument("description", None)
        if description:
            task = graph_accessor.find_most_related_task_in_project(int(project_id), description)
            self.write({"task": task})
        else:
            tasks = graph_accessor.get_tasks_for_project(int(project_id))
            self.write({"tasks": tasks})


class TaskEntityHandler(BaseHandler):
    def post(self, task_id):
        """Add and link an entity to a task."""
        if not self.is_authenticated():
            self.set_status(401); self.write({"error": "Not authenticated"}); return
        
        data = self.get_json()
        entity_id = data.get("entity_id")
        feedback_rating = data.get("feedback_rating")

        if not entity_id or feedback_rating is None:
            self.set_status(400); self.write({"error": "Missing entity_id or feedback_rating"}); return

        graph_accessor.link_entity_to_task(int(task_id), entity_id, feedback_rating)
        self.write({"success": True})

    def get(self, task_id):
        """Retrieve all entities for a task."""
        if not self.is_authenticated():
            self.set_status(401); self.write({"error": "Not authenticated"}); return
        
        entities = graph_accessor.get_entities_for_task(int(task_id))
        self.write({"entities": entities})


class TaskDependencyHandler(BaseHandler):
    def post(self, dependent_task_id):
        """Create a dependency between two tasks."""
        if not self.is_authenticated():
            self.set_status(401); self.write({"error": "Not authenticated"}); return

        data = self.get_json()
        source_task_id = data.get("source_task_id")
        relationship_description = data.get("relationship_description")
        data_schema = data.get("data_schema")
        data_flow = data.get("data_flow")

        if not all([source_task_id, relationship_description, data_schema, data_flow]):
            self.set_status(400); self.write({"error": "Missing required fields for dependency"}); return

        graph_accessor.create_task_dependency(
            int(source_task_id),
            int(dependent_task_id),
            relationship_description,
            data_schema,
            data_flow
        )
        self.write({"success": True, "message": "Task dependency created."})

    def get(self, dependent_task_id):
        """Retrieve all tasks that a given task depends on."""
        if not self.is_authenticated():
            self.set_status(401); self.write({"error": "Not authenticated"}); return

        dependencies = graph_accessor.get_task_dependencies(int(dependent_task_id))
        self.write({"dependencies": dependencies})


class ProjectDependenciesHandler(BaseHandler):
    def get(self, project_id):
        """Retrieve all task dependencies for a project."""
        if not self.is_authenticated():
            self.set_status(401); self.write({"error": "Not authenticated"}); return

        dependencies = graph_accessor.get_all_dependencies_for_project(int(project_id))
        self.write({"dependencies": dependencies})


class UserFindTaskHandler(BaseHandler):
    def get(self):
        """Find the most similar task for a user across all projects."""
        if not self.is_authenticated():
            self.set_status(401); self.write({"error": "Not authenticated"}); return
        
        user_id = self.session.session.get("user_id")
        description = self.get_argument("description", None)

        if not description:
            self.set_status(400); self.write({"error": "Missing description parameter"}); return

        task = graph_accessor.find_most_related_task_for_user(user_id, description)
        self.write({"task": task})


class ChatHistoryHandler(BaseHandler):
    def get(self):
        if not self.is_authenticated():
            self.set_status(401)
            self.write({"error": "Session expired or not authenticated"})
            return

        try:
            project_id = self.get_argument("project_id")
            user_id = graph_accessor.get_user_and_project_ids(self.session.session.get("email"))[0]

            if not user_id or not project_id:
                self.set_status(400)
                self.write({"error": "User ID and Project ID are required."})
                return

            # Fetch history from the database
            history_tuples = graph_accessor.get_user_history(user_id, int(project_id))
            
            # Was in desc order by age, but we want chronological
            history_tuples.reverse()

            # Format for the client
            messages = []
            for i, (prompt, response, desc) in enumerate(history_tuples):
                messages.append({"id": f"hist_{i}_user", "sender": "user", "content": prompt})
                messages.append({"id": f"hist_{i}_bot", "sender": "bot", "content": response})

            self.write({"history": messages})

        except Exception as e:
            logging.error(f"Error fetching chat history: {e}")
            self.set_status(500)
            self.write({"error": "An error occurred while fetching chat history."})

class RenameProjectHandler(BaseHandler):
    def post(self):
        if self.is_session_expired() or not self.is_authenticated():
            self.set_status(401); self.write({"error": "Session expired or not authenticated"}); return
        try:
            data = self.get_json()
            project_id = int(data.get("project_id", 0))
            name = (data.get("name") or "").strip()
            if not project_id or not name:
                self.set_status(400); self.write({"error": "Missing project_id or name"}); return

            email = self.session.session.get("email")
            user_id = graph_accessor.exec_sql("SELECT user_id FROM users WHERE email = %s;", (email,))[0][0]
            # Ensure user has membership
            rows = graph_accessor.exec_sql(
                "SELECT 1 FROM user_projects WHERE user_id = %s AND project_id = %s;",
                (user_id, project_id)
            )
            if not rows:
                self.set_status(403); self.write({"error": "Not a member of this project"}); return

            graph_accessor.execute(
                "UPDATE projects SET project_name = %s WHERE project_id = %s;",
                (name, project_id)
            )
            graph_accessor.commit()
            self.write({"success": True, "project": {"id": project_id, "name": name}})
        except Exception as e:
            self.set_status(500)
            self.write({"error": f"An error occurred: {e}"})


class DeleteProjectHandler(BaseHandler):
    def post(self):
        if self.is_session_expired() or not self.is_authenticated():
            self.set_status(401); self.write({"error": "Session expired or not authenticated"}); return
        try:
            data = self.get_json()
            project_id = int(data.get("project_id", 0))
            if not project_id:
                self.set_status(400); self.write({"error": "Missing project_id"}); return

            email = self.session.session.get("email")
            user_id = graph_accessor.exec_sql("SELECT user_id FROM users WHERE email = %s;", (email,))[0][0]
            # Ensure user has membership
            rows = graph_accessor.exec_sql(
                "SELECT 1 FROM user_projects WHERE user_id = %s AND project_id = %s;",
                (user_id, project_id)
            )
            if not rows:
                self.set_status(403); self.write({"error": "Not a member of this project"}); return

            # If the deleted project is currently selected, pick a fallback after deletion
            current_selected = self.session.session.get("project_id")

            # Delete the project (cascades to user_projects and tasks)
            graph_accessor.execute("DELETE FROM projects WHERE project_id = %s;", (project_id,))
            graph_accessor.commit()

            new_selected = None
            if current_selected == project_id:
                # Choose another project owned by the user, if any
                remaining = graph_accessor.get_user_projects(user_id)
                if remaining and len(remaining) > 1:
                    new_selected = remaining[0]["id"] if isinstance(remaining[0], dict) else remaining[0][0]
                    # Persist selection
                    graph_accessor.set_selected_project_for_user(user_id, new_selected)
                    self.session.session["project_id"] = new_selected
                    session_id = self.get_cookie("msid")
                    if session_id in question_handlers:
                        question_handlers[session_id].set_project_id(new_selected)
                    state[session_id] = self.session.session; state.sync()

            self.write({"success": True, "new_selected_project_id": new_selected})
        except Exception as e:
            self.set_status(500)
            self.write({"error": f"An error occurred: {e}. Note you must have at least one project!"})


class KeepAliveHandler(BaseHandler):
    def get(self):
        """Keep the session alive by refreshing the cookie max-age."""
        if not self.is_authenticated():
            self.set_status(401)
            self.write({"ok": False, "error": "Not authenticated"})
            return
        self.renew_session()
        self.write({"ok": True, "ttl": SESSION_TTL_SECONDS})


class Application(tornado.web.Application):
    def __init__(self, handlers):
        settings = dict(
            #debug=True,
        )
        session_settings = dict(
            driver="memory",
            driver_settings=dict(
                host=self,
            ),
            sid_name='msid',  # default is msid.
            session_lifetime=1800,  # default is 1200 seconds.
            force_persistence=True,
        )
        settings.update(session=session_settings)
        tornado.web.Application.__init__(self, handlers=handlers, **settings)




class FleshOutTaskHandler(BaseHandler):
    async def post(self, task_id):
        """Invoke AnswerQuestionHandler.flesh_out_task for a given task."""
        # Guard: only allow if session is valid and not expired
        if self.is_session_expired() or not self.is_authenticated():
            self.set_status(401)
            self.write({"error": "Session expired or not authenticated"})
            self.redirect_to_login()
            return
        self.renew_session()  # Renew expiration on access

        try:
            data = self.get_json() or {}
        except Exception:
            data = {}

        parent_task_id = data.get("parent_task_id")
        try:
            parent_task_id = int(parent_task_id) if parent_task_id is not None else None
        except Exception:
            parent_task_id = None

        try:
            session_id = self.get_cookie("msid")
            if not session_id or session_id not in question_handlers:
                self.set_status(500)
                self.write({"error": "Session expired, please log in again"})
                return

            email = self.session.session.get("email")
            (user_id, project_id) = graph_accessor.get_user_and_project_ids(email)
            # Ensure the handler is on the current project
            handler = question_handlers[session_id]
            handler.set_project_id(project_id)

            # Flesh out the task (dependencies not required; method queries DB directly)
            answer_text, code = await handler.flesh_out_task(int(task_id), dependencies=None, parent_task_id=parent_task_id)

            self.write({
                "success": True,
                "task_id": int(task_id),
                "refresh_project": project_id,
                "message": answer_text or "",
                "code": code or 0
            })
        except Exception as e:
            logging.error(f"Error during task flesh-out: {e}")
            self.set_status(500)
            self.write({"error": f"An error occurred while fleshing out the task: {e}"})

class RenameTaskHandler(BaseHandler):
    def post(self, task_id):
        if self.is_session_expired() or not self.is_authenticated():
            self.set_status(401); self.write({"error": "Session expired or not authenticated"}); return
        try:
            data = self.get_json() or {}
            new_name = (data.get("name") or data.get("task_name") or "").strip()
            if not new_name:
                self.set_status(400); self.write({"error": "Missing new task name"}); return

            # Verify task exists and user membership in the task's project
            row = graph_accessor.exec_sql("SELECT project_id FROM project_tasks WHERE task_id = %s;", (int(task_id),))
            if not row:
                self.set_status(404); self.write({"error": "Task not found"}); return
            project_id = int(row[0][0])

            email = self.session.session.get("email")
            user_id = graph_accessor.exec_sql("SELECT user_id FROM users WHERE email = %s;", (email,))[0][0]
            mem = graph_accessor.exec_sql("SELECT 1 FROM user_projects WHERE user_id = %s AND project_id = %s;", (user_id, project_id))
            if not mem:
                self.set_status(403); self.write({"error": "Not a member of this project"}); return

            graph_accessor.rename_project_task(int(task_id), new_name)
            self.write({"success": True, "task_id": int(task_id), "name": new_name, "project_id": project_id})
        except Exception as e:
            logging.error(f"RenameTask error: {e}")
            self.set_status(500)
            self.write({"error": f"{e}"})


class DeleteTaskHandler(BaseHandler):
    def post(self, task_id):
        if self.is_session_expired() or not self.is_authenticated():
            self.set_status(401); self.write({"error": "Session expired or not authenticated"}); return
        try:
            # Verify task exists and user membership in the task's project
            row = graph_accessor.exec_sql("SELECT project_id FROM project_tasks WHERE task_id = %s;", (int(task_id),))
            if not row:
                self.set_status(404); self.write({"error": "Task not found"}); return
            project_id = int(row[0][0])

            email = self.session.session.get("email")
            user_id = graph_accessor.exec_sql("SELECT user_id FROM users WHERE email = %s;", (email,))[0][0]
            mem = graph_accessor.exec_sql("SELECT 1 FROM user_projects WHERE user_id = %s AND project_id = %s;", (user_id, project_id))
            if not mem:
                self.set_status(403); self.write({"error": "Not a member of this project"}); return

            graph_accessor.delete_project_task(int(task_id))
            self.write({"success": True, "deleted_task_id": int(task_id), "project_id": project_id})
        except Exception as e:
            logging.error(f"DeleteTask error: {e}")
            self.set_status(500)
            self.write({"error": f"{e}"})

def make_app():
    return Application([
        (r"/health", HealthCheckHandler),
        (r"/db_ping", DbPingHandler),
        (r"/api/session/keepalive", KeepAliveHandler),
        (r"/find_related_entities_by_tag", FindRelatedEntitiesByTagHandler),
        (r"/find_related_entities", FindRelatedEntitiesHandler),
        (r"/add_to_crawl_queue", AddToCrawlQueueHandler),
        (r"/crawl_files", CrawlFilesHandler),
        (r"/parse_pdfs_and_index", ParsePDFsAndIndexHandler),
        (r"/uncrawled_entries", UncrowledEntriesHandler),
        (r"/get_assessment_criteria", GetAssessmentCriteriaHandler),
        (r"/add_assessment_criterion", AddAssessmentCriterionHandler),
        (r"/add_enrichment", AddEnrichmentHandler),
        (r"/expand", ExpandSearchHandler),
        (r"/start_scheduler", StartSchedulerHandler),
        (r"/stop_scheduler", StopSchedulerHandler),
        (r"/api/login", LoginHandler),
        (r"/api/create", CreateAccountHandler),        
        (r"/api/chat/history", ChatHistoryHandler),
        (r"/api/chat", ExpandSearchHandler),
        (r"/api/account", AccountInfoHandler),
        (r"/api/account/update", UpdateAccountHandler),
        (r"/api/projects/list", ListProjectsHandler),
        (r"/api/projects/create", CreateProjectHandler),
        (r"/api/projects/select", SelectProjectHandler),
        (r"/api/projects/rename", RenameProjectHandler),
        (r"/api/projects/delete", DeleteProjectHandler),
        (r"/api/project/(\d+)/tasks", ProjectTaskHandler),
        (r"/api/task/(\d+)/entities", TaskEntityHandler),
        (r"/api/task/(\d+)/dependencies", TaskDependencyHandler),
        (r"/api/project/(\d+)/dependencies", ProjectDependenciesHandler),
        (r"/api/task/(\d+)/flesh_out", FleshOutTaskHandler),
        (r"/api/task/(\d+)/rename", RenameTaskHandler),
        (r"/api/task/(\d+)/delete", DeleteTaskHandler),
        (r"/api/user/find_task", UserFindTaskHandler),
    ])

if __name__ == "__main__":
    try:
        tornado.options.parse_command_line()
        print("Initializing Tornado app...")
        app = make_app()
        port = int(os.getenv("BACKEND_PORT", os.getenv("BACKEND_PORT", 8080)))
        print(f"About to listen on 0.0.0.0:{port}")
        app.listen(port, address="0.0.0.0")
        print(f"Server running on 0.0.0.0:{port}")
        tornado.ioloop.IOLoop.current().start()
    except Exception as e:
        print(f"Fatal server startup error: {e}")
        raise
