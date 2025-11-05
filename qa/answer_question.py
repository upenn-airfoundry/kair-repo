from typing import Any, List, Dict, Optional, Union
import logging
from datetime import datetime
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

#from flask import json
from backend.graph_db import GraphAccessor
from prompts.llm_prompts import QueryPrompts, TaskDependencyList, WebPrompts, PlanningPrompts, ReviewPrompts
from prompts.llm_prompts import QueryClassification, DecisionPrompts, RequiresHumanDecision
from crawl.crawler_queue import CrawlQueue
import asyncio
# from prompts.llm_prompts import LearningResource, LearningResourceList, PotentialSource, TaskOutput, SolutionTask, SolutionPlan
from search import search_over_criteria, search_multiple_criteria, generate_rag_answer, search_basic, is_relevant_answer_with_data
from enrichment.llms import gemini_query_embedding
from prompts.llm_prompts import SolutionTask, SolutionPlan, TaskDependency, UpstreamTaskContext
from prompts.llm_prompts import PeoplePrompts, ExpertBiosketch

import json

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

class AnswerQuestionHandler():
    def __init__(self, graph_accessor: GraphAccessor, username: str, user_profile: dict[str, Any], user_id: int, project_id: int) -> None:
        self.graph_accessor = graph_accessor
        self.username = username
        self.user_profile = user_profile
        self.user_id = user_id
        self.project_id = project_id
        system_profile = graph_accessor.get_system_profile()
        if system_profile and "profile_context" in system_profile:
            self.system_profile = system_profile["profile_context"]

    @classmethod
    def get_gemini_similarity(cls, embed1: List[float], embed2: List[float]) -> float:
        """
        Safe cosine similarity:
        - Handles different vector lengths by truncating to min length.
        - Replaces non-finite values with 0.
        - Returns 0.0 if either vector has zero norm.
        - Returns -1.0 only on unexpected errors.
        """
        try:
            v1 = np.asarray(embed1, dtype=np.float64).ravel()
            v2 = np.asarray(embed2, dtype=np.float64).ravel()
            n = min(v1.size, v2.size)
            if n == 0:
                return -1.0
            if v1.size != v2.size:
                v1 = v1[:n]
                v2 = v2[:n]
            # Replace NaN/Inf with 0 to avoid warnings
            v1[~np.isfinite(v1)] = 0.0
            v2[~np.isfinite(v2)] = 0.0
            n1 = float(np.linalg.norm(v1))
            n2 = float(np.linalg.norm(v2))
            if n1 == 0.0 or n2 == 0.0:
                return 0.0
            return float(np.dot(v1, v2) / (n1 * n2))
        except Exception:
            return -1.0
    
        
    def set_project_id(self, project_id: int) -> None:
        self.project_id = project_id

    def get_history(self, user_id: int, project_id: int) -> List[Dict[str, Any]]:
        return self.graph_accessor.get_user_history(user_id, project_id, limit=20)

    def add_task_entities(self, task_id: int, entity_contents: dict[str, Any]) -> None:
        """Link entities to a task.

        Args:
            task_id (int): The ID of the task to link entities to.
            entity_ids (List[int]): A list of entity IDs to link to the task.
            entity_contents (dict): A dictionary containing the content of the entities.
        """
        existing_entities = self.graph_accessor.get_entities_for_task(task_id)
        entities = {}
        # {"id": r[0], "type": r[1], "name": r[2], "detail": r[3], "url": r[4], "rating": r[5]}
        for eid in [row['id'] for row in existing_entities] or []:
            entities[eid] = self.graph_accessor.get_json(eid)

        for name, e_contents in entity_contents.items():
            entity_id = self.graph_accessor.add_json(name, '', e_contents)
            if entity_id and entity_id not in entities:
                self.graph_accessor.link_entity_to_task(task_id, entity_id, 9.0)
                entities[entity_id] = json.dumps(e_contents)
                
    def get_task_entities(self, task_id: int) -> dict[int, Any]:
        """
        Retrieves all entities associated with a given task, returning a dictionary
        mapping entity IDs to their JSON content.

        Args:
            task_id (int): The ID of the task.

        Returns:
            dict[int, Any]: A dictionary with entity IDs as keys and their JSON objects as values.
        """
        entities = {}
        # get_entities_for_task returns a list of dicts, each with an 'id' key.
        existing_entities = self.graph_accessor.get_entities_for_task(task_id)
        
        if not existing_entities:
            return entities

        for entity_info in existing_entities:
            entity_id = entity_info.get('id')
            if entity_id:
                # get_json retrieves the JSON content for the given entity ID.
                entity_content = self.graph_accessor.get_json(entity_id)
                if entity_content:
                    try:
                        # Ensure the content is a Python object, not a JSON string.
                        entities[entity_id] = json.loads(entity_content) if isinstance(entity_content, str) else entity_content
                    except json.JSONDecodeError:
                        # Handle cases where the content is not valid JSON.
                        logging.warning(f"Could not decode JSON for entity ID {entity_id}")
                        entities[entity_id] = entity_content

        return entities

    def modify_task_entities(self, task_id: int, prompt: str) -> None:
        entities = self.get_task_entities(task_id)

        raise NotImplementedError()
        pass
    
    def get_most_suitable_task(self, task_summary: str, selected_task_id: Optional[int]) -> Optional[int]:
        """
        Returns the most suitable task_id for the given task_summary:
          - If selected_task_id belongs to the current project, return it.
          - Otherwise, find an existing task in the project with high embedding similarity to task_summary.
          - If none are suitable, return None.
        """
        # Prefer explicitly selected task if it belongs to this project
        if selected_task_id is not None:
            project = self.graph_accessor.get_task_project(selected_task_id)
            if project and int(project) == int(self.project_id):
                return int(selected_task_id)

        # Otherwise, find the most similar existing task in this project        
        if not (rows := self.graph_accessor.get_task_names_for_project(self.project_id)):
            return None

        # Embed the summary once
        try:
            embed_summary = gemini_query_embedding(task_summary)
        except Exception:
            embed_summary = None

        best_id: Optional[int] = None
        best_sim: float = -1.0
        for task_id, task_name in rows:
            if embed_summary is None:
                continue
            try:
                embed_name = gemini_query_embedding(task_name)
                sim = AnswerQuestionHandler.get_gemini_similarity(embed_name, embed_summary)
                # Original behavior: require a high threshold; keep the best above it
                if sim > 0.9 and sim > best_sim:
                    best_sim = sim
                    best_id = int(task_id)
            except Exception:
                continue
        return best_id

    async def search_over_papers(self, user_prompt: str, original_prompt: str, task_summary: str, selected_task_id: Optional[int], parent_task_id: Optional[int] = None) -> tuple[Optional[str], Optional[int]]:
        """
        Federated search for papers and return a relevant answer with links.
        """
        answer = await WebPrompts.find_learning_resources(user_prompt)
        markdown_answer = WebPrompts.format_resources_as_markdown(answer)
        
        self.graph_accessor.add_user_history(self.user_id, self.project_id, original_prompt, markdown_answer)
 
        # TODO: consider whether to change this prompt to see if the papers are promising
        # for providing answers.       
        # if ReviewPrompts.assess_responsiveness(user_prompt, markdown_answer).fully_responsive is False:
        #     answer = await search_basic(
        #         user_prompt,
        #         "You are an expert assistant. Please answer the following question concisely and accurately, providing web links if appropriate.\n\nIf you don't know the answer, just say you don't know. Do not make up an answer."
        #     )
        #     self.graph_accessor.add_user_history(self.user_id, self.project_id, original_prompt, answer)
        #     return (answer, 0)

        # Derive an evaluation prompt and output schema for downstream crawling/indexing
        eval_prompt = task_summary or original_prompt
        outputs_schema = ""
        try:
            spec = PlanningPrompts.extract_paper_question_spec(original_prompt)
            if getattr(spec, "evaluation_prompt", ""):
                eval_prompt = spec.evaluation_prompt
            # Prefer explicit outputs_schema; otherwise derive from outputs
            if getattr(spec, "outputs_schema", ""):
                outputs_schema = spec.outputs_schema
            if not outputs_schema and getattr(spec, "outputs", None):
                parts = []
                for o in spec.outputs:
                    try:
                        parts.append(f"{o.name}:{o.datatype or 'string'}")
                    except Exception:
                        continue
                outputs_schema = f"({', '.join(parts)})" if parts else ""
        except Exception as e:
            logging.warning(f"extract_paper_question_spec failed; using defaults: {e}")
        if not outputs_schema:
            outputs_schema = "(title:string,answer:string,url:string)"

        # Find a suitable existing task or create one
        task_id = self.get_most_suitable_task(task_summary, selected_task_id)
        if task_id is None:
            task_id = self.graph_accessor.create_project_task(
                self.project_id,
                task_summary,
                "Learning resources for project " + str(self.project_id),
                "(title:string,rationale:string,url:string)"
            )
            # If this is being created under a parent task, add the parent-subtask edge
            try:
                if parent_task_id is not None:
                    self.graph_accessor.create_task_dependency(
                        source_task_id=int(parent_task_id),
                        dependent_task_id=int(task_id),
                        relationship_description="Parent to subtask",
                        data_schema="",
                        data_flow="parent task-subtask",
                    )
            except Exception as e:
                logging.warning(f"Failed to create parent->subtask dependency ({parent_task_id} -> {task_id}): {e}")

        # Collect paper URLs to crawl, while creating/linking entities
        items: List[str] = []
        for resource in answer.resources:
            url = resource.open_access_pdf or resource.url
            entity_id = self.graph_accessor.get_entity_by_url(url)
            video_sites = ['youtube.com', 'youtu.be', 'vimeo.com', 'coursera.org', 'edx.org', 'khanacademy.org', 'udemy.com', 'dailymotion.com']
            # If it's a paper, add to crawl queue
            entity_type = 'learning_resource' if any(site in url for site in video_sites) else 'paper'
            if entity_id is None:
                # Entity does not exist, create a new one
                entity_id = self.graph_accessor.add_source(url, entity_type, resource.title)

            #if entity_type == 'paper':
            items.append(url)
            # else:
            #     logging.info(f"Entity for URL {resource.url} already exists with ID {entity_id}.")
            
            # Link the task to the new or existing entity
            if entity_id and task_id:
                self.graph_accessor.link_entity_to_task(task_id, entity_id, 9.0)

        resource_summary = [resource.model_dump() for resource in answer.resources]
        self.add_task_entities(task_id, {'sources': resource_summary})

        # Trigger crawl + TEI generation + indexing with task-specific eval prompt and schema
        results = []
        if items:
            try:
                results = await CrawlQueue.fetch_url_content(items, task_id, eval_prompt, outputs_schema)
            except Exception as e:
                logging.warning(f"fetch_url_content failed: {e}")
                
        if results:
            # Trigger text extraction of documents
            
            # TODO: leverage enrichment tasks for analysis here
            # Also incorporate new enrichment tasks for any remaining questions
            await CrawlQueue.analyze_documents([int(result['id']) for result in results])
            
        # TODO: after analyze_documents is done and enriched -- search for results
        # with the key criteria, return results and annotations to build the task schema

        # Update the project task info!
        return (markdown_answer, task_id)

    async def search_papers_by_criteria(self, user_prompt: str, original_prompt: str, task_summary: str, selected_task_id: Optional[int]) -> tuple[Optional[str], Optional[int]]:
        """Search for papers in the local index based on user criteria.

        Args:
            user_prompt (str): The user's search query.
            original_prompt (str): The original user prompt.
            selected_task_id (Optional[int]): The ID of the selected task, if any.

        Returns:
            tuple[Optional[str], Optional[int]]: A tuple containing the search results and the task ID.
        """
        questions = search_over_criteria(user_prompt, self.graph_accessor.get_assessment_criteria(None))
        logging.info(f'Expanded into subquestions: {questions}')
        
        relevant_docs = search_multiple_criteria(questions)
        main = self.graph_accessor.find_related_entity_ids_by_tag(user_prompt, "summary", 50)

        logging.debug(f"Relevant docs: {relevant_docs}")
        logging.debug(f"Main papers: {main}")

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

        print(f"Items matching criteria: {docs_in_order}")

        if docs_in_order is None or not len(docs_in_order):
            return (None, 0)

        paper_info = self.graph_accessor.get_entities_with_summaries(list(docs_in_order))
        answer = generate_rag_answer(paper_info, user_prompt)

        self.graph_accessor.add_user_history(self.user_id, self.project_id, questions, answer)
        if answer is None or len(answer) == 0 or "i am sorry" in answer.lower() or not is_relevant_answer_with_data(user_prompt, answer):
            questions = None
            answer = await search_basic(user_prompt)
        
        if questions is None:
            return (answer, 0)
        
        question_str = ''
        question_map = json.loads(questions)
        for q in question_map.keys():
            question_str += f' * {q}: {question_map[q]}\n'

        return (answer + '\n\nWe additionally looked for assessment criteria: \n\n' + question_str, 1)
        
    async def flesh_out_task(self, task_id: int, dependencies: "TaskDependencyList", parent_task_id: Optional[int] = None) -> tuple[Optional[str], Optional[int]]:
        """
        Expand a task into more detail or sub-tasks.
        """
        # 1) Load task core via GraphAccessor
        task_row = self.graph_accessor.get_task_core(task_id, project_id=self.project_id)
        if not task_row:
            logging.error(f"Task with ID {task_id} not found in project {self.project_id}.")
            return (f"Error: Task with ID {task_id} not found.", 0)

        task_name = task_row.get("task_name") or ""
        task_description = task_row.get("task_description") or ""
        task_schema = task_row.get("task_schema") or ""
        task_context_json = task_row.get("task_context")

        # Build upstream contexts
        upstream_contexts: List[UpstreamTaskContext] = []
        prior_task_ids = self.graph_accessor.get_upstream_task_ids(task_id)
        prior_tasks = self.graph_accessor.get_tasks_core_by_ids(prior_task_ids) if prior_task_ids else []
        if prior_task_ids:
            prior_task_map: Dict[int, dict] = {int(t["task_id"]): t for t in prior_tasks if t.get("task_id") is not None}
            for prior_id in prior_task_ids:
                ents = self.graph_accessor.get_entities_for_task(prior_id) or []
                json_ids = [int(e["id"]) for e in ents if isinstance(e, dict) and e.get("type") == "json_data"]
                if not json_ids:
                    continue
                title = (prior_task_map.get(int(prior_id), {}) or {}).get("task_description") or f"Task {prior_id}"
                json_blobs: List[Union[str, dict]] = []
                for eid in json_ids:
                    blob = self.graph_accessor.get_json(eid)
                    if blob is None:
                        continue
                    try:
                        json_blobs.append(json.loads(blob) if isinstance(blob, str) else blob)
                    except Exception:
                        json_blobs.append(blob)
                if json_blobs:
                    upstream_contexts.append(UpstreamTaskContext(title=title, json_entities=json_blobs))

        spec = PlanningPrompts.build_flesh_out_prompt(
            task_name=task_name,
            task_description=task_description,
            task_schema=task_schema,
            task_context=task_context_json,
            upstream_contexts=upstream_contexts,
        )
        if spec.needs_user_clarification:
            return ("This task needs further clarification from you before it can be expanded. Please provide more details.", 0)
        prompt = spec.prompt

        # 2) Use an LLM to generate a more detailed plan or sub-tasks
        return await self.answer_question(prompt, selected_task_id=task_id, parent_task_id=parent_task_id)

        # Here you could create sub-tasks, link new entities, or update the existing task.
        # For now, we just return the generated text.
        
        # 3. Add the generated plan to the user's history
        # The original prompt is not available here, so we'll use a generic one.
        # original_prompt = f"Flesh out task: {task_name}"
        # self.graph_accessor.add_user_history(self.user_id, self.project_id, original_prompt, response_text)

        # # Return the response and a status code indicating if the project state changed (0 for no change here)
        # return (response_text, 0)

    async def flesh_out_plan(self, user_prompt: str, original_prompt: str, task_summary: str, selected_task_id: Optional[int], parent_task_id: Optional[int] = None) -> tuple[Optional[str], Optional[int]]:
        solution_plan = PlanningPrompts.generate_solution_plan(original_prompt)

        if not solution_plan or not solution_plan.tasks:# or not ReviewPrompts.assess_responsiveness(user_prompt, str(solution_plan)).fully_responsive:
            answer = await search_basic(
                user_prompt,
                "You are an expert data engineer who understands data resources, data modeling, schemas and types, MCP servers, and related elements. Please suggest how to break the task into steps (tasks). For each task, identify where to get the necessary information, as well as a complete set of fields (i.e., a schema with expected and required properties and features with their expected modalities or datatypes) that should be produced by the task and are required to clearly identify the best solutions to the task. Include evidence such as sources and processes, properties useful for rating and how these properties are assessed, and justifications for answers.\n\nIf you don't know the answer, just say you don't know. Do not make up an answer or a property value."
            )
            self.graph_accessor.add_user_history(self.user_id, self.project_id, original_prompt, answer)
            return (answer, 0)
        
        # Return 1 to indicate that the project was modified and should be refreshed
        # Convert the SolutionPlan to a markdown string for display
        markdown_response = f"# Proposed Plan for: {task_summary}\n\n"
        markdown_response += "Here is a breakdown of the steps to address your request:\n\n"

        for i, task in enumerate(solution_plan.tasks):
            task_name = f"Task {i+1}: {task.description_and_goals.split('.')[0]}"
            markdown_response += f"### {task_name}\n"
            markdown_response += f"**Goal:** {task.description_and_goals}\n\n"
            
            if task.outputs:
                markdown_response += "**Outputs to be generated:**\n"
                for output in task.outputs:
                    markdown_response += f"- **{output.name}** (`{output.datatype}`): {output.description}\n"
                markdown_response += "\n"
        

        self.graph_accessor.add_user_history(self.user_id, self.project_id, original_prompt, markdown_response)
        
        task_descriptions_to_ids = {}
        # Process each task in the generated plan
        for i, task in enumerate(solution_plan.tasks):
            # Create a concise task name from the description
            task_name = f"Task {i+1}: {task.description_and_goals.split('.')[0]}"
            # Create a schema string from the task outputs
            schema_parts = [f"{output.name}:{output.datatype}" for output in task.outputs]
            schema_string = f"({', '.join(schema_parts)})"
            # Create the task in the database
            task_id = self.graph_accessor.create_project_task(
                project_id=self.project_id,
                name=task_name,
                description=task.description_and_goals,
                schema=schema_string,
                task_context=task.model_dump_json()
            )
            # Optional: connect this new task under the parent task as a subtask
            try:
                if parent_task_id is not None:
                    self.graph_accessor.create_task_dependency(
                        source_task_id=int(parent_task_id),
                        dependent_task_id=int(task_id),
                        relationship_description="Parent to subtask",
                        data_schema="",
                        data_flow="parent task-subtask",
                    )
            except Exception as e:
                logging.warning(f"Failed to create parent->subtask dependency ({parent_task_id} -> {task_id}): {e}")
            task_descriptions_to_ids[f"task_{i}"] = task_id

        # After creating all tasks, determine and create their dependencies
        dependency_list = PlanningPrompts.determine_task_dependencies(solution_plan)
        if dependency_list and dependency_list.dependencies:
            for dep in dependency_list.dependencies:
                if dep.data_flow_type == "parent task-subtask":
                    continue  # Skip parent-subtask edges as dependencies
                source_name = dep.source_task_id
                source_id = task_descriptions_to_ids.get(source_name)
                dependent_name = dep.dependent_task_id
                dependent_id = task_descriptions_to_ids.get(dependent_name)

                if source_id and dependent_id:
                    self.graph_accessor.create_task_dependency(
                        source_task_id=source_id,
                        dependent_task_id=dependent_id,
                        relationship_description=dep.relationship_description,
                        data_schema=dep.data_schema,
                        data_flow=dep.data_flow_type
                    )
                else:
                    logging.warning(f"Could not find task IDs for dependency: {dep.source_task_description} -> {dep.dependent_task_description}")

        # Auto-execute tasks that can run without user input and whose upstream deps have json_data
        try:
            # Build upstream dependency map: dependent_id -> [source_ids]
            upstream_map: Dict[int, List[int]] = {}
            if dependency_list and getattr(dependency_list, "dependencies", None):
                for dep in dependency_list.dependencies:
                    # Skip back-flow edges!
                    if dep.data_flow_type == "rethinking the previous task":
                        continue
                    if dep.data_flow_type == "parent task-subtask":
                        continue  # Skip parent-subtask edges as dependencies
                    s_name = getattr(dep, "source_task_id", None)
                    d_name = getattr(dep, "dependent_task_id", None)
                    s_id = task_descriptions_to_ids.get(s_name) if s_name is not None else None
                    d_id = task_descriptions_to_ids.get(d_name) if d_name is not None else None
                    if s_id and d_id:
                        upstream_map.setdefault(int(d_id), []).append(int(s_id))

            def has_json_data_entities(tid: int) -> bool:
                try:
                    ents = self.graph_accessor.get_entities_for_task(tid) or []
                    return any((e.get("type") == "json_data") for e in ents if isinstance(e, dict))
                except Exception as _e:
                    logging.warning(f"Failed checking json_data for task {tid}: {_e}")
                    return False

            # Iterate all created tasks
            for _, tid in task_descriptions_to_ids.items():
                if not tid:
                    continue
                # Check upstream readiness
                upstream_ids = upstream_map.get(int(tid), [])
                ready = all(has_json_data_entities(uid) for uid in upstream_ids)
                if not ready:
                    continue
                # Check if human input is required
                # try:
                #     needs_human = await self.requires_human_by_id(int(tid))
                # except Exception as _e:
                #     logging.warning(f"requires_human check failed for task {tid}: {_e}")
                #     needs_human = True  # conservative
                # if needs_human:
                #     continue
                # Execute
                try:
                    await self.flesh_out_task(int(tid), dependency_list, parent_task_id=parent_task_id)
                    pass
                except Exception as _e:
                    logging.error(f"Auto-execute flesh_out_task failed for task {tid}: {_e}")
        except Exception as e:
            logging.error(f"Auto-execution loop error: {e}")
        
        return (markdown_response, 1)
        

    async def answer_question(self, user_prompt: str, selected_task_id: Optional[int] = None, parent_task_id: Optional[int] = None) -> tuple[Optional[str], Optional[int]]:
        try:
            if self.project_id is None:
                # Create a new project and associate it with the user
                self.project_id = self.graph_accessor.create_project( f"{self.username}'s Project", "New project created", self.user_id)

            user_history = self.get_history(self.user_id, self.project_id)

            # 1. Classify query and get task summary
            classification = QueryPrompts.classify_query_and_summarize(user_prompt)
            query_class = classification.query_class
            task_summary = classification.task_summary
            
            # 2. Build expanded prompt
            expanded_prompt = QueryPrompts.build_expanded_prompt(self.system_profile, self.user_profile, user_history, task_summary, user_prompt)

            print(f"Expanded prompt: {expanded_prompt}")
            
            original_prompt = user_prompt
            user_prompt = expanded_prompt

            # query_class: Literal["general_knowledge", "technical_training", "papers_reports_or_prior_work", "solutions_sources_and_justifications"]

            if query_class == "general_knowledge" or query_class == "other":
                answer = await search_basic(
                    user_prompt,
                    "You are an expert assistant. Please answer the following general knowledge question concisely and accurately.\n\nIf you don't know the answer, just say you don't know. Do not make up an answer."
                )

                if ReviewPrompts.assess_responsiveness(user_prompt, answer).fully_responsive and selected_task_id is not None:
                    self.add_task_entities(selected_task_id, {"answer": {"response": answer, "source_prompt": user_prompt}})
                
                self.graph_accessor.add_user_history(self.user_id, self.project_id, original_prompt, answer)
                return (answer, 0)
            
            elif classification.query_class == "info_about_an_expert":
                # Produce structured biosketch
                biosketch: ExpertBiosketch = await PeoplePrompts.generate_expert_biosketch_from_prompt(original_prompt)
                # Store as json_data if a task is selected
                if selected_task_id is not None and biosketch is not None:
                    try:
                        self.add_task_entities(selected_task_id, {"expert_biosketch": biosketch.model_dump()})  # type: ignore
                    except Exception as e:
                        logging.warning(f"Failed to store biosketch entity: {e}")
                # Create a readable markdown summary for UI
                name_line = "## " + (biosketch.name or "Expert") + (f" ({biosketch.organization})" if biosketch.organization else "")
                md = [name_line, ""]
                if biosketch.biosketch:
                    md += ["### Biographical Sketch", biosketch.biosketch.strip(), ""]
                if biosketch.headshot_url:
                    md += [f"![Headshot]({biosketch.headshot_url})", ""]
                if biosketch.education_and_experience:
                    md += ["### Education and Experience"] + [f"- {item}" for item in biosketch.education_and_experience] + [""]
                if biosketch.major_research_projects_and_entrepreneurship:
                    md += ["### Major Research Projects and Entrepreneurship"] + [f"- {item}" for item in biosketch.major_research_projects_and_entrepreneurship] + [""]
                if biosketch.honors_and_awards:
                    md += ["### Honors and Awards"] + [f"- {item}" for item in biosketch.honors_and_awards] + [""]
                if biosketch.expertise_and_contributions:
                    md += ["### Expertise and Major Contributions"] + [f"- {item}" for item in biosketch.expertise_and_contributions] + [""]
                if biosketch.recent_publications_or_products:
                    md += ["### Recent Publications or Products"] + [f"- {item}" for item in biosketch.recent_publications_or_products] + [""]
                answer_md = "\n".join(md).strip()
                # Save to user history
                self.graph_accessor.add_user_history(self.user_id, self.project_id, original_prompt, answer_md)
                # Project state may have been modified if we linked json_data; returning 0 is fine for UI
                return (answer_md, 1)

            elif classification.query_class == "learning_resources_or_technical_training" or classification.query_class == "information_from_prior_work_like_papers_or_videos_or_articles":
                return await self.search_over_papers(user_prompt, original_prompt, task_summary, selected_task_id, parent_task_id=parent_task_id)

            elif classification.query_class == "papers_reports_or_prior_work":
                # TODO: Needs to be merged with above
                return await self.search_papers_by_criteria(user_prompt, original_prompt, task_summary, selected_task_id)
            elif classification.query_class == "multi_step_planning_or_problem_solving":
                # Generate a structured plan from the user's prompt
                # Create a wrapper task node representing this planning request
                try:
                    node_name = f"Plan: {task_summary[:200]}" if task_summary else "Plan node"
                    # Prefer to serialize the classifier if possible
                    try:
                        classification_ctx = classification.model_dump_json()  # pydantic v2
                    except Exception:
                        try:
                            classification_ctx = json.dumps(getattr(classification, "dict", lambda: {})())
                        except Exception:
                            classification_ctx = str(classification)
                    plan_context = json.dumps({
                        "type": "SolutionTaskNode",
                        "original_prompt": original_prompt,
                        "expanded_prompt": user_prompt,
                        "classification": classification_ctx,
                    })
                    wrapper_task_id = self.graph_accessor.create_project_task(
                        project_id=self.project_id,
                        name=node_name,
                        description=task_summary or original_prompt,
                        schema="",
                        task_context=plan_context # type: ignore
                    )
                    # If there is a parent, add a parent->subtask edge to this wrapper node
                    if parent_task_id is not None:
                        try:
                            self.graph_accessor.create_task_dependency(
                                source_task_id=int(parent_task_id),
                                dependent_task_id=int(wrapper_task_id),
                                relationship_description="Parent to subtask",
                                data_schema="",
                                data_flow="parent task-subtask",
                            )
                        except Exception as e:
                            logging.warning(f"Failed to link parent->plan node ({parent_task_id}->{wrapper_task_id}): {e}")
                except Exception as e:
                    logging.warning(f"Failed to create wrapper plan task node: {e}")
                    wrapper_task_id = None

                # Use the wrapper node as the parent for tasks created in flesh_out_plan
                return await self.flesh_out_plan(
                    user_prompt,
                    original_prompt,
                    task_summary,
                    selected_task_id,
                    parent_task_id=wrapper_task_id if wrapper_task_id is not None else parent_task_id
                )
            else:
                raise ValueError(f"Unknown query class: {classification.query_class}")
        except Exception as e:
            logging.error(f"Error during expansion: {e}")
            raise e
        return None
    
    async def requires_human(self,
                             task: Dict[str, Any],
                             upstream_tasks: List[Dict[str, Any]],
                             downstream_tasks: List[Dict[str, Any]]) -> bool:
        """
        Determine whether 'task' needs human input, given upstream info and downstream needs.
        Returns True if human is required; False if LLM/tools can proceed autonomously.
        """
        task_id = int(task.get("task_id") or task.get("id") or 0)
        task_name = task.get("task_name") or task.get("name") or f"Task {task_id}"
        task_desc = task.get("description") or task.get("task_description") or task.get("goals") or ""
        outputs_schema = task.get("schema") or task.get("outputs_schema") or "(unknown)"

        # Summarize upstream entities/info
        def _safe_join(items: List[str]) -> str:
            return "\n".join(f"- {s}" for s in items if s)

        upstream_entity_summaries: List[str] = []

        # Try to load entity ids linked to upstream tasks
        try:
            upstream_ids = [int(t.get("task_id") or t.get("id")) for t in upstream_tasks if (t.get("task_id") or t.get("id"))]
            entity_ids: List[int] = []
            if upstream_ids:
                # Attempt via GraphAccessor helper if available
                if hasattr(self.graph_accessor, "get_entities_for_tasks"):
                    entity_ids = self.graph_accessor.get_entities_for_tasks(upstream_ids)  # List[int]
                else:
                    # Fallback: direct SQL from a common linking table name
                    rows = self.graph_accessor.exec_sql(
                        "SELECT entity_id FROM task_entities WHERE task_id = ANY(%s);",
                        (upstream_ids,)
                    )
                    entity_ids = [int(r[0]) for r in rows] if rows else []
            if entity_ids:
                ents = self.graph_accessor.get_entities_with_summaries(entity_ids)  # expect list of dicts
                for e in ents or []:
                    title = e.get("title") or e.get("name") or f"Entity {e.get('id','?')}"
                    summary = e.get("summary") or e.get("abstract") or ""
                    upstream_entity_summaries.append(f"{title}: {summary[:500]}")
        except Exception as e:
            logging.warning(f"Upstream entity summary failed: {e}")

        upstream_text = _safe_join(upstream_entity_summaries)

        # Summarize downstream needs (from dependent tasks' schemas and relationship descriptions)
        downstream_bits: List[str] = []
        for dt in downstream_tasks or []:
            dname = dt.get("task_name") or dt.get("name") or "Dependent Task"
            dneed = dt.get("schema") or dt.get("outputs_schema") or ""
            rel = dt.get("relationship_description") or ""
            if dneed:
                downstream_bits.append(f"{dname} expects: {dneed}")
            if rel:
                downstream_bits.append(f"Criteria/relationship: {rel}")
        downstream_text = _safe_join(downstream_bits)

        decision: RequiresHumanDecision = await DecisionPrompts.requires_human(
            task_name=task_name,
            task_description=task_desc,
            outputs_schema=outputs_schema,
            upstream_text=upstream_text,
            downstream_needs_text=downstream_text
        )
        return bool(decision.requires_human)

    # Optional helper: fetch by IDs from DB
    async def requires_human_by_id(self, task_id: int) -> bool:
        """
        Convenience: load the task, its upstream and downstream neighbors from the DB, then decide.
        """
        # Load task core
        row = self.graph_accessor.get_task_core(task_id)
        if not row:
            return True  # conservative default
        task = {
            "task_id": row["task_id"],
            "task_name": row["task_name"],
            "description": row["task_description"],
            "schema": row["task_schema"],
        }

        # Load dependencies (both directions) and classify upstream/downstream
        deps = self.graph_accessor.get_dependencies_rows_for_task(task_id) or []

        upstream_tasks: List[Dict[str, Any]] = []
        downstream_tasks: List[Dict[str, Any]] = []
        if deps:
            upstream_ids = [int(r[0]) for r in deps if int(r[1]) == task_id]
            downstream_ids = [int(r[1]) for r in deps if int(r[0]) == task_id]

            # Batch fetch task cores
            upstream_tasks = [
                {
                    "task_id": t["task_id"],
                    "task_name": t["task_name"],
                    "description": t["task_description"],
                    "schema": t["task_schema"],
                }
                for t in self.graph_accessor.get_tasks_core_by_ids(upstream_ids)
            ]
            downstream_tasks = [
                {
                    "task_id": t["task_id"],
                    "task_name": t["task_name"],
                    "description": t["task_description"],
                    "schema": t["task_schema"],
                }
                for t in self.graph_accessor.get_tasks_core_by_ids(downstream_ids)
            ]

            # Attach relationship info for downstream
            rel_map: Dict[int, Dict[str, Optional[str]]] = {
                int(r[1]): {"relationship_description": r[2], "data_schema": r[3]}
                for r in deps
                if int(r[0]) == task_id
            }
            for dt in downstream_tasks:
                if info := rel_map.get(int(dt["task_id"])):
                    dt.update(info)

        return await self.requires_human(task, upstream_tasks, downstream_tasks)
