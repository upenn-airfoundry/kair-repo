from typing import Any, List, Dict, Optional
import logging
from datetime import datetime

from flask import json
from backend.graph_db import GraphAccessor
from prompts.llm_prompts import QueryPrompts
from search import search_over_criteria, search_multiple_criteria, generate_rag_answer, search_basic, is_relevant_answer_with_data


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
    
    def answer_question(self, user_prompt: str):
        try:
            if self.project_id is None:
                # Create a new project and associate it with the user
                new_project_id = self.graph_accessor.exec_sql(
                    "INSERT INTO projects (project_name, project_description, created_at) VALUES (%s, %s, %s) RETURNING project_id;",
                    (f"{session.get('username', 'User')}'s Project", "New project created", datetime.now())
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
                answer = search_basic(user_prompt, "You are an expert assistant. Please answer the following general knowledge question concisely and accurately.\n\nIf you don't know the answer, just say you don't know. Do not make up an answer.")
                self.graph_accessor.add_user_history(self.user_id, self.project_id, original_prompt, answer)
                return answer
            elif classification.query_class == "technical_training":
                answer = search_basic(user_prompt, "You are an expert technical trainer. Please provide a clear and concise explanation, or a list of resources for further learning.\n\nIf you don't know the answer, just say you don't know. Do not make up an answer.")
                self.graph_accessor.add_user_history(self.user_id, self.project_id, original_prompt, answer)
                return answer
            elif classification.query_class == "papers_reports_or_prior_work":

                pass # through
            elif classification.query_class == "molecules_algorithms_solutions_sources_and_justifications":
                # user_prompt = f"You are an expert consultant. Please provide potential solutions, sources, and justifications for the following problem or question:\n\n{user_prompt}\n\nIf you don't know the answer, just say you don't know. Do not make up an answer."
                answer = search_basic(user_prompt, "You are an expert data engineer who understands data resources, data modeling, schemas and types, MCP servers, and related elements. Please suggest a complete set of fields (i.e., a schema) for possible solutions to the question, including citations to sources, evidence, expected properties and features with their expected modalities or datatypes, factors useful for decision-making, and justifications.\n\nIf you don't know the answer, just say you don't know. Do not make up an answer.")
                self.graph_accessor.add_user_history(self.user_id, self.project_id, original_prompt, answer)
                return answer

            
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
                    answer = search_basic(user_prompt)
                
                if questions:
                    question_str = ''
                    question_map = json.loads(questions)
                    for q in question_map.keys():
                        question_str += f' * {q}: {question_map[q]}\n'
                        
                    return answer + '\n\nWe additionally looked for assessment criteria: \n\n' + question_str
                else:
                    return answer
            else:
                return None
        except Exception as e:
            logging.error(f"Error during expansion: {e}")
            raise e
        return None
