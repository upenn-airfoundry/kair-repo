##################
## Search
##
## Copyright (C) Zachary G. Ives, 2025
##################

import requests
from typing import List
import json
import os

# Lazy imports / guards to prevent startup failures
try:
    from backend.graph_db import GraphAccessor
    graph_db = GraphAccessor()
    graph_accessor = GraphAccessor()
except Exception:
    graph_db = None
    graph_accessor = None

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None  # type: ignore

try:
    from langchain_openai import ChatOpenAI
    from langchain.prompts import ChatPromptTemplate
    from langchain.schema.output_parser import StrOutputParser
    from langchain.output_parsers import PydanticOutputParser
    from langchain.prompts import ChatPromptTemplate
    from langchain.output_parsers import PydanticOutputParser
    from pydantic import BaseModel, Field
except Exception:
    ChatOpenAI = None  # type: ignore
    ChatPromptTemplate = None  # type: ignore
    StrOutputParser = None  # type: ignore
    PydanticOutputParser = None  # type: ignore
    BaseModel = object  # type: ignore
    Field = lambda *args, **kwargs: None  # type: ignore

try:
    from enrichment.llms import get_analysis_llm, get_better_llm
    analysis_llm = get_analysis_llm()
    better_llm = get_better_llm()
except Exception:
    analysis_llm = None
    better_llm = None

from urllib.parse import unquote


def get_line_items_as_str(criteria: List) -> str:
    """
    Converts a list of criteria into a formatted string.

    Args:
        criteria (List): The list of criteria to format.

    Returns:
        str: The formatted string representation of the criteria.
    """
    ret = ""
    for i in range(len(criteria)):
        if criteria[i]['prompt'].lower() != 'none':
            ret += "- " + criteria[i]['name'] + ': ' + criteria[i]['prompt'] + "\n"
        
    return ret


def get_json_fragment(criteria: List) -> str:
    """
    Converts a list of criteria into a JSON fragment.

    Args:
        criteria (List): The list of criteria to convert.

    Returns:
        str: The JSON fragment representation of the criteria.
    """
    ret = "{"
    for i in range(len(criteria)):
        ret += '"' + criteria[i]['name'] + '": "..."'
        if i > 0:
            ret += ", "
        
    return ret + "}"




def is_search_over_papers(question: str) -> bool:
    """
    Determines if the question is about searching over papers.
    """
    keywords = ["paper", "research", "study", "publication", "article", "journal"]
    try:
        if better_llm is None or ChatPromptTemplate is None or StrOutputParser is None:
            # Fallback heuristic
            return any(k in question.lower() for k in keywords)
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an expert at understanding what kinds of answers are merited for a question."),
            ("user", "We want to know whether the kinds of answers expected for the question are related to papers. projects, people, or data. Please strictly answer \"yes\" or \"no.\" Question: {question}\n\nAnswer:"),
        ])
        chain = prompt | better_llm | StrOutputParser()
        answer = chain.invoke({"question": question}).lower().strip()
        if answer.startswith('yes'):
            return True
        if answer.startswith('no'):
            return False
        return any(k in question.lower() for k in keywords)
    except Exception:
        return any(k in question.lower() for k in keywords)


def search_basic(question: str) -> str:
    """Simple fallback answer if LLM unavailable."""
    try:
        if better_llm is None or ChatPromptTemplate is None or StrOutputParser is None:
            return "Unable to reach LLM right now."
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an expert in answering questions about science, targeting educational or scientific users."),
            ("user", "{question}\n\nAnswer:")
        ])
        chain = prompt | better_llm | StrOutputParser()
        return chain.invoke({"question": question})
    except Exception as e:
        return f"An error occurred: {e}"


def search_over_criteria(question: str, criteria: List) -> str:
    try:
        if better_llm is None or ChatPromptTemplate is None or StrOutputParser is None:
            return "{}"
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an expert at taking a question and breaking it into criterion-specific subquestions."),
            ("user", """We are looking for promising papers, datasets, and resources related to the question. 
                        Given a list of answers to the following questions with papers, datasets, and resources:\n\n{bulleted_list}\n\n
                        For each of the target items, provide a specific search phrase for what answers we expect to the question, 
                        in the structured JSON fragment below, replacing the '...'. Omit the item is irrelevant. 
                        Question: {question}\n\nAnswer:"""),
        ])
        bulleted_list = get_line_items_as_str(criteria)
        json_fragment = get_json_fragment(criteria)
        chain = prompt | better_llm | StrOutputParser()
        answer = chain.invoke({"title": 'answers', "question": question, "json_fragment": json_fragment, "bulleted_list": bulleted_list})
        if answer.startswith('```'):
            answer = answer.split('```')[1]
            if answer.startswith('json'):
                answer = answer.split('json')[1]
            answer = answer.strip()
        return answer
    except Exception as e:
        return f"An error occurred: {e}"


def search_multiple_criteria(criteria: str) -> List:
    try:
        items = json.loads(criteria)
        if graph_accessor is None:
            return []
        candidates = {}
        for criterion in items.keys():
            sub_prompt = items[criterion]
            results = graph_accessor.find_related_entity_ids_by_tag(sub_prompt, criterion, 50)
            if results:
                candidates[criterion] = results
        intersected_candidates = set()
        for criterion in items.keys():
            if intersected_candidates == set():
                intersected_candidates = set(candidates.get(criterion, []))
            else:
                if criterion not in candidates:
                    continue
                intersected_candidates.intersection_update(set(candidates[criterion]))
        intersected_candidates = list(intersected_candidates)
        return intersected_candidates if intersected_candidates else "No candidates found matching all criteria."
    except Exception as e:
        return f"An error occurred parsing {criteria}: {e}"


def generate_rag_answer(paper_titles_and_summaries: List, question: str) -> str:
    try:
        context = "\n".join([f"Paper Title: {p['name']}\nURL: {p['url']}\nSummary: {p['summary']}" for p in paper_titles_and_summaries])
        if better_llm is None or ChatPromptTemplate is None or StrOutputParser is None:
            return ""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert assistant that answers questions based on provided research paper, dataset, or resource summaries.  
                          For each paper or resource, please return markdown with the title, in boldface and italics; embed the title within a hyperlink
                          to the resource. Also include for each item a brief summary of the resource, and an
                          explanation of why it is included. Boldface the headings for the summary and explanation.
                          If the resource is not relevant to the question, do not include it in the answer."""),
            ("user", "Here are the titles and summaries of some research papers:\n\n{context}\n\nQuestion: {question}\n\nAnswer:")
        ])
        chain = prompt | better_llm | StrOutputParser()
        response = chain.invoke({"context": context, "question": question})
        return response
    except Exception as e:
        return f"An error occurred: {e}"


def is_relevant_answer_with_data(question: str, answer: str) -> bool:
    try:
        if analysis_llm is None or ChatPromptTemplate is None:
            return False
        class RelevanceResponse(BaseModel):
            relevant: str = Field(description="Answer 'yes' if the answer responds to the question with a list of resources, otherwise 'no'.")
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an expert at evaluating whether an answer to a question provides a list of resources (such as papers, datasets, or links). Respond strictly with 'yes' or 'no'."),
            ("user", "Question: {question}\n\nAnswer: {answer}\n\nDoes the answer respond to the question with a list of resources? Respond strictly with 'yes' or 'no'.")
        ])
        structured_llm = analysis_llm.with_structured_output(RelevanceResponse)
        extraction_chain = prompt | structured_llm
        result = extraction_chain.invoke({"question": question, "answer": answer})
        return result.relevant.strip().lower() == "yes"
    except Exception:
        return False