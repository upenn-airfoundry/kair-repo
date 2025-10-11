##################
## PDF document parsing, semantic extraction,
## and simple enrichment
##
## Copyright (C) Zachary G. Ives, 2025
##################

# Crawls the PDFs listed in the frontier queue

import traceback
import os
import json

from datetime import datetime
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document

from aryn_sdk.partition import partition_file

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from backend.graph_db import GraphAccessor

from enrichment.llms import get_analysis_llm

from dotenv import load_dotenv, find_dotenv

_ = load_dotenv(find_dotenv())

DOWNLOAD_DIR = os.getenv("PDF_PATH", os.path.expanduser("~/Downloads"))

graph_db = GraphAccessor()

def index_split_paragraphs(split_docs: list, path: str, url: str, the_date) -> int:
    """
    Indexes the paragraphs from the split documents into the graph database.
    This function takes the split documents, concatenates the first two splits,
    and uses a language model to extract the title, research field, summary,
    and authors from the concatenated text. It then stores this information in
    the graph database.
    :param split_docs: List of split documents from the PDF.
    :return: Paper ID
    """
    # Take the first 2 splits and concatenate them
    n = 0
    length = 0
    for i in range(len(split_docs)):
        length += len(split_docs[i].page_content.split())
        n += 1
        if length > 100:
            break
    
    concatenated_text = " ".join(doc.page_content for doc in split_docs[:n])

    # Use GPT-4o-mini to extract summary and authors
    llm = get_analysis_llm()
    prompt_template = ChatPromptTemplate.from_template(
        """Extract the title, research field, summary and authors from the following text. 
        If available, include authors' email addresses and affiliations in JSON format. 
        Text:
        {text}

        Output format:
        {{
        "title": "...",
        "field": "...",
        "summary": "...",
        "authors": [
            {{"name": "...", "email": "...", "affiliation": "..."}},
            ...
        ]
        }}
        """
    )

    prompt = prompt_template.format_messages(text=concatenated_text)

    response = llm.invoke(prompt)
    response_text = response.content
    
    if '```' in response_text:
        response_text = response_text.split('```')[1]
        if response_text.startswith('json'):
            response_text = response_text.split('json')[1]
        response_text = response_text.strip()
    
    paper_id = 0
    try:
        extracted_info = json.loads(response_text)

        # Print the extracted JSON
        # print(f"Extracted Info: {json.dumps(extracted_info, indent=2)}")
        
                        # Add the paper to the database
        title = extracted_info.get("title", "Unknown Title")
        field = extracted_info.get("field", "Unknown Field")
        summary = extracted_info.get("summary", "No Summary Available")
        paper_id = graph_db.add_paper(url=path, title=title, summary=summary)
        
        # Store the link to the actual document
        graph_db.link_entity_to_document(paper_id, url, path, 'pdf', extracted_info)
        
        print ("Added paper " + str(paper_id) + " with title " + title)
        
        graph_db.add_or_update_tag(paper_id, "field", field)
        
        print ("Added summary " + summary)

        # Add authors to the database
        authors = extracted_info.get("authors", [])
        for author in authors:
            name = author.get("name", "Unknown Author")
            email = author.get("email", None)
            affiliation = author.get("affiliation", None)
            author_id = graph_db.add_author_tag(paper_id, name, email, affiliation)
            #graph_db.link_author_to_paper(author_id, paper_id)
            print(f"Added author: {name} ({author_id})")

        # Index the paragraphs
        for doc in split_docs:
            content = doc.page_content
            print(f"Indexing paragraph: {content}")
            (para_id, embedding) = graph_db.add_paragraph(paper_id, content)
        graph_db.commit()
        return paper_id
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        print("Raw response text:")
        print(response_text)

        return 0    
