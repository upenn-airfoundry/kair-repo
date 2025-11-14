from typing import Any, List, Dict, Optional, Tuple, Union
import asyncio
import logging

from backend.graph_db import GraphAccessor
from prompts.llm_prompts import QueryPrompts, TaskDependencyList, WebPrompts, PlanningPrompts, ReviewPrompts, summarize_paper_via_llm
from prompts.llm_prompts import extract_expertise_spec, ExpertRequestSpec
from pydantic import BaseModel, Field
from langchain.prompts import ChatPromptTemplate
from enrichment.llms import get_analysis_llm
from crawl.crawler_queue import CrawlQueue

from search import search_over_criteria, search_multiple_criteria, generate_rag_answer, search_basic, is_relevant_answer_with_data
from prompts.llm_prompts import UpstreamTaskContext
from prompts.llm_prompts import PeoplePrompts, ExpertBiosketch, summarize_paper_via_notebooklm
from qa.qa_tasks import TaskHelper

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

    def set_project_id(self, project_id: int) -> None:
        self.project_id = project_id

    def get_history(self, user_id: int, project_id: int) -> List[Dict[str, Any]]:
        return self.graph_accessor.get_user_history(user_id, project_id, limit=20)

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
        task_id = TaskHelper.get_or_create_task(self.graph_accessor, self.project_id, task_summary, selected_task_id, parent_task_id)

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
        if task_id:
            TaskHelper.add_task_entities(self.graph_accessor, task_id, {'sources': resource_summary})

        # Trigger crawl + TEI generation + indexing with task-specific eval prompt and schema
        results = []
        if items and task_id:
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
                task_context=task.model_dump()
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
                    TaskHelper.add_task_entities(self.graph_accessor, selected_task_id, {"answer": {"response": answer, "source_prompt": user_prompt}})
                
                self.graph_accessor.add_user_history(self.user_id, self.project_id, original_prompt, answer)
                return (answer, 0)
            
            elif classification.query_class == "info_about_an_expert":
                # Produce structured biosketch with timeout and safe fallback
                try:
                    biosketch: ExpertBiosketch = await asyncio.wait_for(
                        PeoplePrompts.generate_expert_biosketch_from_prompt(original_prompt),
                        timeout=120,
                    )
                except Exception as e:
                    logging.warning(f"Biosketch generation failed, using minimal fallback: {e}")
                    biosketch = ExpertBiosketch(
                        name=None,
                        organization=None,
                        headshot_url=None,
                        scholar_id=None,
                        biosketch=original_prompt.strip(),
                        education_and_experience=[],
                        major_research_projects_and_entrepreneurship=[],
                        honors_and_awards=[],
                        expertise_and_contributions=[],
                        recent_publications_or_products=[],
                        all_articles=[],
                    )
                # Find a suitable existing task or create one
                task_id = TaskHelper.get_or_create_task(self.graph_accessor, self.project_id, task_summary, selected_task_id, parent_task_id)
                # Store as json_data if a task is selected
                if biosketch is not None:
                    try:
                        TaskHelper.add_task_entities(self.graph_accessor, task_id, {"expert_biosketch": biosketch.model_dump()})  # type: ignore
                    except Exception as e:
                        logging.warning(f"Failed to store biosketch entity: {e}")

                answer_md = PeoplePrompts.format_biosketch_as_markdown(biosketch)
                # Save to user history
                self.graph_accessor.add_user_history(self.user_id, self.project_id, original_prompt, answer_md)
                # Project state may have been modified if we linked json_data; returning 0 is fine for UI

                PeoplePrompts.persist_biosketch_to_graph(
                    self.graph_accessor,
                    biosketch
                )

                return (answer_md, 1)
            
            # elif classification.query_class == "find_an_expert_for_a_topic":
            #     answer = await search_basic(
            #         user_prompt,
            #         "You are an expert assistant. Please recommend an expert for the following topic."
            #     )

            #     if ReviewPrompts.assess_responsiveness(user_prompt, answer).fully_responsive and selected_task_id is not None:
            #         TaskHelper.add_task_entities(self.graph_accessor, selected_task_id, {"answer": {"response": answer, "source_prompt": user_prompt}})
                
            #     self.graph_accessor.add_user_history(self.user_id, self.project_id, original_prompt, answer)
            #     return (answer, 0)

            elif classification.query_class == "find_experts_for_task_or_area":
                # Extract normalized expertise specifiers via LLM (with robust fallback)
                try:
                    spec: ExpertRequestSpec = extract_expertise_spec(original_prompt)
                except Exception:
                    spec = ExpertRequestSpec(desired_expertise=[original_prompt.strip()])

                # Build a search query string from extracted expertise terms
                expertise_query = " ".join([s for s in (spec.desired_expertise or []) if isinstance(s, str) and s.strip()])
                if not expertise_query:
                    expertise_query = original_prompt.strip()

                # Use tag-embedding similarity search over 'expertise' tags
                try:
                    candidate_ids: List[Tuple[int, float]] = self.graph_accessor.find_related_entity_ids_by_tag(expertise_query, "expertise", k=50)
                except Exception as e:
                    logging.warning(f"find_related_entity_ids_by_tag failed: {e}")
                    candidate_ids = []

                candidate_ids = [cid for cid in candidate_ids if (cid[1] is not None) and (cid[1] < 0.9)]
                
                
                if not candidate_ids:
                    answer = await search_basic(
                        user_prompt,
                        "You are an expert assistant. Please recommend an expert for the following topic."
                    )

                    if ReviewPrompts.assess_responsiveness(user_prompt, answer).fully_responsive and selected_task_id is not None:
                        TaskHelper.add_task_entities(self.graph_accessor, selected_task_id, {"answer": {"response": answer, "source_prompt": user_prompt}})
                    
                    self.graph_accessor.add_user_history(self.user_id, self.project_id, original_prompt, answer)
                    return (answer, 0)

                # Fetch entity core info for google_scholar_profile candidates
                rows: List[tuple] = []
                try:
                    sql = f"""
                        SELECT e.entity_id, e.entity_name, e.entity_url
                        FROM {self.graph_accessor.schema}.entities e
                        JOIN unnest(%s::int[]) WITH ORDINALITY AS u(id, ord) ON e.entity_id = u.id
                        WHERE e.entity_type = 'google_scholar_profile'
                        ORDER BY u.ord
                    """
                    rows = self.graph_accessor.exec_sql(sql, ([cid[0] for cid in candidate_ids],)) or []
                except Exception as e:
                    logging.warning(f"Expert fetch SQL failed: {e}")

                if not rows:
                    answer = "No matching experts were found."
                    self.graph_accessor.add_user_history(self.user_id, self.project_id, original_prompt, answer)
                    return (answer, 0)

                # Fetch expertise tags for these entities
                expertise_rows: List[tuple] = []
                expertise_map: Dict[int, List[str]] = {}
                try:
                    sql_tags = f"""
                        SELECT et.entity_id, et.tag_value
                        FROM {self.graph_accessor.schema}.entity_tags et
                        WHERE et.tag_name='expertise' AND et.entity_id = ANY(%s)
                    """
                    expertise_rows = self.graph_accessor.exec_sql(sql_tags, ([cid[0] for cid in candidate_ids],)) or []
                    for eid, tag_val in expertise_rows:
                        if eid not in expertise_map:
                            expertise_map[eid] = []
                        if isinstance(tag_val, str) and tag_val.strip():
                            expertise_map[eid].append(tag_val.strip())
                except Exception as e:
                    logging.warning(f"Failed fetching expertise tags: {e}")

                # Define structured selection models
                class ExpertCandidate(BaseModel):
                    entity_id: int
                    name: str
                    url: Optional[str] = None
                    expertise: List[str] = Field(default_factory=list)

                class ExpertSelectionItem(BaseModel):
                    entity_id: int
                    name: str
                    url: Optional[str] = None
                    expertise: List[str]
                    justification: str

                class ExpertSelection(BaseModel):
                    matches: List[ExpertSelectionItem]

                # Build candidate list
                candidates: List[ExpertCandidate] = []
                for (eid, name, url) in rows:
                    candidates.append(ExpertCandidate(
                        entity_id=int(eid),
                        name=name or f"Expert {eid}",
                        url=url,
                        expertise=expertise_map.get(int(eid), [])
                    ))

                # LLM selection prompt
                llm = get_analysis_llm()
                selection: Optional[ExpertSelection] = None
                if llm is not None:
                    try:
                        cand_text_lines = []
                        for c in candidates:
                            exp_str = "; ".join(c.expertise) if c.expertise else "(no expertise tags)"
                            cand_text_lines.append(f"ID {c.entity_id} | {c.name} | {exp_str}")
                        cand_block = "\n".join(cand_text_lines)
                        prompt = ChatPromptTemplate.from_messages([
                            ("system", "You are selecting the most relevant experts for the user's request. You MUST return JSON matching the ExpertSelection schema. Include only experts whose expertise clearly maps to the request. For each selected expert provide a concise justification referencing their expertise list. If there is no justification, omit the expert from the list."),
                            ("user", f"Original request: {original_prompt}\n\nCandidate experts (one per line):\n{cand_block}\n\nReturn JSON.")
                        ])
                        structured_llm = llm.with_structured_output(ExpertSelection)  # type: ignore[attr-defined]
                        selection_raw = structured_llm.invoke(prompt.format())
                        if isinstance(selection_raw, ExpertSelection):
                            selection = selection_raw
                    except Exception as e:
                        logging.warning(f"Structured expert selection failed: {e}")

                if selection is None or not getattr(selection, "matches", None):
                    # Fallback: include all candidates with heuristic justification
                    fallback_items = []
                    for c in candidates[:20]:
                        just = f"Matches query terms via expertise: {', '.join(c.expertise[:5]) if c.expertise else 'general relevance'}"
                        fallback_items.append(ExpertSelectionItem(
                            entity_id=c.entity_id,
                            name=c.name,
                            url=c.url,
                            expertise=c.expertise,
                            justification=just
                        ))
                    selection = ExpertSelection(matches=fallback_items)

                # Build maps for filling missing details
                eid_to_url: Dict[int, Optional[str]] = {int(eid): url for (eid, _name, url) in rows}
                eid_to_name: Dict[int, str] = {int(eid): (_name or f"Expert {eid}") for (eid, _name, _url) in rows}
                eid_to_expertise: Dict[int, List[str]] = {int(eid): expertise_map.get(int(eid), []) for (eid, _n, _u) in rows}

                # Build markdown output
                lines = [f"# Top experts for: {expertise_query}", ""]
                results_payload: List[Dict[str, Any]] = []
                for idx, m in enumerate(selection.matches, start=1):
                    sel_url = m.url or eid_to_url.get(int(m.entity_id))
                    sel_name = m.name or eid_to_name.get(int(m.entity_id), f"Expert {m.entity_id}")
                    sel_exp = m.expertise or eid_to_expertise.get(int(m.entity_id), [])
                    exp_str = ", ".join(sel_exp) if sel_exp else "(no expertise tags)"
                    name_display = f"[{sel_name}]({sel_url})" if sel_url else sel_name
                    lines.append(f"{idx}. {name_display}\n   * Expertise: {exp_str}\n   * Justification: {m.justification}")
                    results_payload.append({
                        "entity_id": int(m.entity_id),
                        "name": sel_name,
                        "url": sel_url,
                        "expertise": sel_exp,
                        "justification": m.justification,
                    })
                answer_md = "\n".join(lines)

                # Persist to task & link entities
                task_id = TaskHelper.get_or_create_task(self.graph_accessor, self.project_id, task_summary or f"Find experts: {expertise_query}", selected_task_id, parent_task_id)
                try:
                    if task_id:
                        TaskHelper.add_task_entities(self.graph_accessor, int(task_id), {"expert_matches": results_payload})
                        for m in selection.matches[:20]:
                            try:
                                self.graph_accessor.link_entity_to_task(int(task_id), int(m.entity_id), 8.7)
                            except Exception:
                                continue
                except Exception as e:
                    logging.warning(f"Failed to persist expert match entities: {e}")

                self.graph_accessor.add_user_history(self.user_id, self.project_id, original_prompt, answer_md)
                return (answer_md, 1)

            elif classification.query_class == "learning_resources_or_technical_training" or classification.query_class == "information_from_prior_work_like_papers_or_videos_or_articles":
                return await self.search_over_papers(user_prompt, original_prompt, task_summary, selected_task_id, parent_task_id=parent_task_id)
            elif classification.query_class == "summarize_paper_at_url":
                # Extract URL from original prompt (simple heuristic)
                import re
                url_match = re.search(r"https?://\S+", original_prompt)
                if not url_match:
                    answer = "No URL found to summarize. Please provide a direct paper URL."
                    self.graph_accessor.add_user_history(self.user_id, self.project_id, original_prompt, answer)
                    return (answer, 0)
                paper_url = url_match.group(0).rstrip(').,;')
                # summary_md = await summarize_paper_via_notebooklm(paper_url)
                summary_md = await summarize_paper_via_llm(paper_url, task_summary)
                # Create or associate task
                task_id = TaskHelper.get_or_create_task(self.graph_accessor, self.project_id, task_summary or "Summarize paper", selected_task_id, parent_task_id)
                if task_id is not None:
                    try:
                        TaskHelper.add_task_entities(self.graph_accessor, int(task_id), {"paper_summary": {"url": paper_url, "markdown": summary_md}})
                    except Exception as e:
                        logging.warning(f"Failed to store paper summary entity: {e}")
                self.graph_accessor.add_user_history(self.user_id, self.project_id, original_prompt, summary_md)
                return (summary_md, 1)

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
            error_msg = f"An internal error occurred while processing your request. Details: {e}"
            try:
                self.graph_accessor.add_user_history(self.user_id, self.project_id, user_prompt, error_msg)
            except Exception:
                pass
            return (error_msg, 0)
        return None
    
