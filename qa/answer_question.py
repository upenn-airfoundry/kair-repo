from typing import Any, List, Dict, Optional
import logging
from datetime import datetime

from flask import json
from backend.graph_db import GraphAccessor
from prompts.llm_prompts import QueryPrompts, WebPrompts, PlanningPrompts
from prompts.llm_prompts import QueryClassification

import asyncio
# from prompts.llm_prompts import LearningResource, LearningResourceList, PotentialSource, TaskOutput, SolutionTask, SolutionPlan
from search import search_over_criteria, search_multiple_criteria, generate_rag_answer, search_basic, is_relevant_answer_with_data
from enrichment.llms import gemini_query_embedding


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
    
    async def answer_question(self, user_prompt: str) -> tuple[Optional[str], Optional[int]]:
        try:
            if self.project_id is None:
                # Create a new project and associate it with the user
                new_project_id = self.graph_accessor.exec_sql(
                    "INSERT INTO projects (project_name, project_description, created_at) VALUES (%s, %s, %s) RETURNING project_id;",
                    (f"{self.username}'s Project", "New project created", datetime.now())
                )
                self.graph_accessor.commit()
                if new_project_id is None or len(new_project_id) == 0:
                    raise Exception("Failed to create a new project.")
                
                new_project_id = new_project_id[0][0]
                self.graph_accessor.execute(
                    "INSERT INTO user_projects (user_id, project_id) VALUES (%s, %s);",
                    (self.user_id, new_project_id)
                )
                self.graph_accessor.commit()
                self.project_id = new_project_id

            user_history = self.get_history(self.user_id, self.project_id)

            # 1. Classify query and get task summary
            classification = QueryPrompts.classify_query_and_summarize(user_prompt)
            query_class = classification.query_class
            task_summary = classification.task_summary
            
            # 2. Build expanded prompt
            expanded_prompt = QueryPrompts.build_expanded_prompt(self.system_profile, self.user_profile, user_history, task_summary, user_prompt)

            print("Expanded prompt: " + expanded_prompt)
            
            original_prompt = user_prompt
            user_prompt = expanded_prompt

            # query_class: Literal["general_knowledge", "technical_training", "papers_reports_or_prior_work", "solutions_sources_and_justifications"]

            if query_class == "general_knowledge":
                answer = await search_basic(
                    user_prompt,
                    "You are an expert assistant. Please answer the following general knowledge question concisely and accurately.\n\nIf you don't know the answer, just say you don't know. Do not make up an answer."
                )
                self.graph_accessor.add_user_history(self.user_id, self.project_id, original_prompt, answer)
                return (answer, 0)
            elif classification.query_class == "learning_resources_or_technical_training" or classification.query_class == "papers_reports_or_prior_work":
                # answer = search_basic(user_prompt, "You are an expert technical trainer. Please provide a clear and concise explanation, or a list of resources for further learning.\n\nIf you don't know the answer, just say you don't know. Do not make up an answer.")
                answer = await WebPrompts.find_learning_resources(user_prompt)
                markdown_answer = WebPrompts.format_resources_as_markdown(answer)

                existing_task = self.graph_accessor.exec_sql("SELECT task_id, task_name FROM project_tasks WHERE project_id = %s", (self.project_id,))
                
                for item in existing_task:
                    embed1 = gemini_query_embedding(item[1])
                    embed2 = gemini_query_embedding(task_summary)
                    similarity = sum(a*b for a, b in zip(embed1, embed2))
                    if similarity > 0.9:
                        existing_task = [item]
                        break
                    else:
                        existing_task = []
                
                if existing_task and len(existing_task) > 0:
                    # Task already exists, no need to create a new one
                    task_id = existing_task[0][0]
                else:
                    task_id = self.graph_accessor.create_project_task(self.project_id, task_summary, "Learning resources for project " + str(self.project_id), "(title:string,rationale:string,resource:url)")
                    
                for resource in answer.resources:
                    entity_id = self.graph_accessor.get_entity_by_url(resource.url)
                    
                    if entity_id is None:
                        # Entity does not exist, create a new one
                        video_sites = ['youtube.com', 'youtu.be', 'vimeo.com', 'coursera.org', 'edx.org', 'khanacademy.org', 'udemy.com', 'dailymotion.com']
                        entity_type = 'learning_resource' if any(site in resource.url for site in video_sites) else 'paper'
                        
                        entity_id = self.graph_accessor.add_source(resource.url, entity_type, resource.title)
                    
                    # Link the task to the new or existing entity
                    if entity_id and task_id:
                        self.graph_accessor.link_entity_to_task(task_id, entity_id, 9.0)

                self.graph_accessor.add_user_history(self.user_id, self.project_id, original_prompt, markdown_answer)
                
                # Update the project task info!
                return (markdown_answer, 1)
            elif classification.query_class == "papers_reports_or_prior_work":

                pass # through
            elif classification.query_class == "molecules_algorithms_solutions_strategies_or_plans":#"molecules_algorithms_solutions_sources_and_justifications":
                # Generate a structured plan from the user's prompt
                solution_plan = PlanningPrompts.generate_solution_plan(original_prompt)

                markdown_response = "I have generated a plan to address your request. Here are the proposed tasks:\n\n"
                
                if not solution_plan or not solution_plan.tasks:
                    answer = await search_basic(
                        user_prompt,
                        "You are an expert data engineer who understands data resources, data modeling, schemas and types, MCP servers, and related elements. Please suggest a complete set of fields (i.e., a schema) for possible solutions to the question, including citations to sources, evidence, expected properties and features with their expected modalities or datatypes, factors useful for decision-making, and justifications.\n\nIf you don't know the answer, just say you don't know. Do not make up an answer."
                    )
                    self.graph_accessor.add_user_history(self.user_id, self.project_id, original_prompt, answer)
                    return (answer, 0)
                
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
                    task_descriptions_to_ids[f"task_{i}"] = task_id

                    # Append a summary of the created task to the user-facing response
                    markdown_response += f"\n### {task_name}\n\n"
                    markdown_response += f"**Goal:** {task.description_and_goals}\n\n"
                    if task.needs_user_clarification:
                        markdown_response += "**Action Required:** This task needs further clarification from you.\n\n"
                    markdown_response += "**Outputs:** " + schema_string + "\n\n"
                    for output in task.outputs:
                        markdown_response += f"- **{output.name}** (`{output.datatype}`): {output.description}\n\n"
                    markdown_response += "\n\n"
                    
                
                # After creating all tasks, determine and create their dependencies
                dependency_list = PlanningPrompts.determine_task_dependencies(solution_plan)
                if dependency_list and dependency_list.dependencies:
                    for dep in dependency_list.dependencies:
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


                self.graph_accessor.add_user_history(self.user_id, self.project_id, original_prompt, markdown_response)
                
                # Return 1 to indicate that the project was modified and should be refreshed
                return (markdown_response, 1)

            
            # if not is_search_over_papers(user_prompt):
            #     answer = search_basic(user_prompt)
            #     self.write({
            #         "data": {
            #             "message": answer
            #         }})
            #     return

            questions = search_over_criteria(user_prompt, self.graph_accessor.get_assessment_criteria(None))
            logging.info('Expanded into subquestions: ' + questions)
            
            relevant_docs = search_multiple_criteria(questions)
            main = self.graph_accessor.find_related_entity_ids_by_tag(user_prompt, "summary", 50)

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
                paper_info = self.graph_accessor.get_entities_with_summaries(list(docs_in_order))
                answer = generate_rag_answer(paper_info, user_prompt)

                self.graph_accessor.add_user_history(self.user_id, self.project_id, questions, answer)
                if answer is None or len(answer) == 0 or "i am sorry" in answer.lower() or not is_relevant_answer_with_data(user_prompt, answer):
                    questions = None
                    answer = await search_basic(user_prompt)
                
                if questions:
                    question_str = ''
                    question_map = json.loads(questions)
                    for q in question_map.keys():
                        question_str += f' * {q}: {question_map[q]}\n'

                    return (answer + '\n\nWe additionally looked for assessment criteria: \n\n' + question_str, 1)
                else:
                    return (answer, 0)
            else:
                return (None, 0)
        except Exception as e:
            logging.error(f"Error during expansion: {e}")
            raise e
        return None
