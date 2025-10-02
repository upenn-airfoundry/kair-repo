import os
import sys
import bcrypt
import logging
import uuid
import time

# Feature flags
SKIP_ENRICHMENT = os.getenv("SKIP_ENRICHMENT", "").lower() in ("1", "true", "yes")

# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import tornado.ioloop
import tornado.web
import tornado.options
from torndsession.session import SessionManager
from torndsession.session import SessionMixin
import json
from datetime import datetime
from dotenv import load_dotenv, find_dotenv
from torndsession.sessionhandler import SessionBaseHandler

# Load environment variables from .env file
_ = load_dotenv(find_dotenv())

from backend.graph_db import GraphAccessor
from backend.enrichment_daemon import EnrichmentDaemon
from prompts.llm_prompts import PeoplePrompts
# from enrichment.langchain_ops import AssessmentOps


# Defer importing search until runtime to avoid DB init at import time

# Configure logging
logging.basicConfig(level=logging.INFO)


# class MainHandler(SessionBaseHandler):
#     def get(self):
#         self.write("Memory Session Object Demo:<br/>")
#         if "sv" in self.session:
#             current_value = self.session["sv"]
#         else:
#             current_value = 0
#         if not current_value:
#             self.write("current_value is None(0)<br/>")
#             current_value = 1
#         else:
#             current_value = int(current_value) + 1
#         self.write('<br/> Current Value is: %d' % current_value)
#         self.write('<br/>Current Python Version: %s' % version)
#         self.session["sv"] = current_value


# class DeleteHandler(SessionBaseHandler):
#     def get(self):
#         '''
#         Please don't do this in production environments.
#         '''
#         self.write("Memory Session Object Demo:")
#         if "sv" in self.session:
#             current_value = self.session["sv"]
#             self.write("current sv value is %s, and system will delete this value.<br/>" % self.session["sv"])
#             self.session.delete("sv")
#             if "sv" not in self.session:
#                 self.write("current sv value is empty")
#         else:
#             self.write("Session data not found")

class BaseHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.set_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
    
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

########### Main ###########

# Initialize the GraphAccessor, but don't crash if DB is unavailable (or skip)
graph_accessor = None
try:
    graph_accessor = GraphAccessor()
    
    if not SKIP_ENRICHMENT:
        EnrichmentDaemon.initialize_enrichment(graph_accessor)

except Exception as e:
    logging.error(f"Failed to initialize database connection: {e}")

class LoginHandler(BaseHandler, SessionMixin):
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
                self.session["session_id"] = session_id
                self.session["username"] = user[0][0]

                # Set session ID as a cookie for the client
                self.set_cookie("session_id", session_id, expires_days=None, max_age=600, httponly=True, secure=False)
                
                profile = graph_accessor.get_user_profile(email)  # Load user profile if needed
                self.session["profile"] = profile
                if profile is not None and 'publications' not in profile:
                    scholar_id = profile.get("scholar_id") if profile else None

                    if scholar_id:
                        pubs = PeoplePrompts.get_person_publications(graph_accessor, user[0][0], user[0][1], scholar_id)

                        self.session['profile']["publications"] = pubs

                self.write({
                    "success": True, 
                    "user": {
                        "name": user[0][0],
                        "organization": user[0][1],
                        "avatar": user[0][2],
                        "profile": self.session.get("profile", {})
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

class FindRelatedEntitiesByTagHandler(BaseHandler, SessionMixin):
    def get(self):
        # Guard: only allow if session is valid and not expired
        if self.is_session_expired():
            self.set_status(401)
            self.write({"error": "Session expired or not authenticated"})
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
        results = graph_accessor.find_related_entities(query, k, entity_type, keywords)
        self.write({"results": results})

class AddToCrawlQueueHandler(BaseHandler):
    def post(self):
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
        try:
            data = self.get_json()
            name = data.get('name')
            EnrichmentDaemon.run_enrichment_task(name)
            self.write({"message": "All enrichment tasks queued"})
        except Exception as e:
            self.set_status(500)
            self.write({"error": f"An error occurred: {e}"})

class ExpandSearchHandler(BaseHandler):
    def post(self):
        try:
            # Lazy import to avoid startup failures if LLM/DB not ready
            from search import (
                search_over_criteria,
                search_multiple_criteria,
                generate_rag_answer,
                is_search_over_papers,
                search_basic,
                is_relevant_answer_with_data,
            )
            # Ensure search module can access the same graph accessor
            try:
                import search as search_module
                search_module.graph_accessor = graph_accessor
            except Exception:
                pass
            data = self.get_json()
            user_prompt = data.get('prompt')
            
            if not user_prompt:
                logging.error("'prompt' parameter is missing")
                self.set_status(400)
                self.write({"error": "'prompt' parameter is required"})
                return

            if not is_search_over_papers(user_prompt):
                answer = search_basic(user_prompt)
                self.write({
                    "data": {
                        "message": answer
                    }})
                return
            
            if graph_accessor is None:
                # Fall back to basic LLM answer when DB isn't available
                answer = search_basic(user_prompt)
                self.write({
                    "data": {
                        "message": answer
                    }
                })
                return
            questions = search_over_criteria(user_prompt, graph_accessor.get_assessment_criteria(None))
            logging.info('Expanded into subquestions: ' + questions)
            
            relevant_docs = search_multiple_criteria(questions)
            main = graph_accessor.find_related_entity_ids_by_tag(user_prompt, "summary", 50)
            
            logging.debug("Relevant docs: " + str(relevant_docs))
            logging.debug("Main papers: " + str(main))
            
            docs_in_order = []
            count = 0
            for doc in relevant_docs:
                if doc in set(main):
                    docs_in_order.append(doc)
                    count += 1
                    if count >= 10:
                        break
                
            other_docs = 0    
            while count < 10 and other_docs < len(main):
                if main[other_docs] not in set(relevant_docs):
                    docs_in_order.append(main[other_docs])
                    count += 1
                other_docs += 1
            
            print("Items matching criteria: " + str(docs_in_order))
            
            if len(docs_in_order):
                paper_info = graph_accessor.get_entities_with_summaries(list(docs_in_order))
                answer = generate_rag_answer(paper_info, user_prompt)
                
                if answer is None or len(answer) == 0 or "i am sorry" in answer.lower() or not is_relevant_answer_with_data(user_prompt, answer):
                    questions = None
                    answer = search_basic(user_prompt)
                
                if questions:
                    question_str = ''
                    question_map = json.loads(questions)
                    for q in question_map.keys():
                        question_str += f' * {q}: {question_map[q]}\n'
                        
                    self.write({
                        "data": {
                            "message": answer + '\n\nWe additionally looked for assessment criteria: \n\n' + question_str
                        }
                    })
                else:
                    self.write({
                        "data": {
                            "message": answer
                        }
                    })
            else:
                self.set_status(404)
                self.write({"error": "No relevant papers found"})
        except Exception as e:
            logging.error(f"Error during expansion: {e}")
            self.set_status(500)
            self.write({"error": f"An error occurred: {e}"})
            
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

class Application(tornado.web.Application):
    def __init__(self, handlers):
        settings = dict(
            debug=True,
        )
        session_settings = dict(
            driver="memory",
            driver_settings=dict(
                host=self,
            ),
            sid_name='torndsession-mem',  # default is msid.
            session_lifetime=1800,  # default is 1200 seconds.
            force_persistence=True,
        )
        settings.update(session=session_settings)
        tornado.web.Application.__init__(self, handlers=handlers, **settings)




def make_app():
    return Application([
        (r"/health", HealthCheckHandler),
        (r"/db_ping", DbPingHandler),
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
        (r"/api/chat", ExpandSearchHandler),
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