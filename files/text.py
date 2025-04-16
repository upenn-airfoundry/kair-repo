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
from graph_db import GraphAccessor

from dotenv import load_dotenv, find_dotenv

_ = load_dotenv(find_dotenv())

DOWNLOAD_DIR = os.getenv("PDF_PATH", os.path.expanduser("~/Downloads"))

graph_db = GraphAccessor()

def index_split_paragraphs(split_docs, path, the_date) -> int:
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
    llm = ChatOpenAI(model="gpt-4o-mini")  # Use ChatOpenAI for chat models
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
        paper_id = graph_db.add_paper(url=path, crawl_time=str(the_date), title=title, summary=summary)
        
        print ("Added paper " + str(paper_id) + " with title " + title)
        
        graph_db.add_tag_to_paper(paper_id, "field", field)
        
        print ("Added summary " + summary)

        # Add authors to the database
        authors = extracted_info.get("authors", [])
        for author in authors:
            name = author.get("name", "Unknown Author")
            email = author.get("email", None)
            affiliation = author.get("affiliation", None)
            author_id = graph_db.add_author(name=name, email=email, organization=affiliation)
            graph_db.link_author_to_paper(author_id, paper_id)
            print(f"Added author: {name} (ID: {author_id})")

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

def chunk_and_partition_pdf_file(filename, dir:str = DOWNLOAD_DIR) -> dict:
  data = None
  with open(dir + filename, "rb") as f:
    data = partition_file(f,
        chunking_options={
          "strategy": "context_rich",
          "tokenizer": "openai_tokenizer",
          "tokenizer_options": {
              "model_name": "text-embedding-3-small"
          },
          "merge_across_pages": True,
          "max_tokens": 512,
        }, aryn_api_key="eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJzdWIiOnsiZW1sIjoianZhcnVuQHNlYXMudXBlbm4uZWR1IiwiYWN0IjoiNDE4NTQ2Njk5NDEzIn0sImlhdCI6MTcyNjcxMzYwNS43NzYyMDAzfQ.ugaWkJqMQkzGUVz8c7KnU7DHxlP_JehUJF1NY74w30whYK-BCVPfJCZv0DVXG1n2vL7TLKl135bv4eTXlwPACA")
   
    return data

        
def split_with_langchain(pdf_path: str) -> list:
    loader = PyPDFLoader(pdf_path)
    documents = loader.load()
    
    # Use the most common splitter: RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    split_docs = splitter.split_documents(documents)
    
    return split_docs

def get_presplit_file(filename: str) -> list:
    """
    Load a pre-split JSON file that was created by the chunk_and_partition_pdf_file function.
    :param
    filename: The name of the JSON file to load.
    :return: A list of split documents.
    """
    json_path = os.path.join(DOWNLOAD_DIR, filename)
    
    if os.path.exists(json_path):
        with open(json_path, 'r') as f:
            data = json.load(f)
            # Convert the data into a format that can be used as documents
            split_docs = []
            for item in data['elements']:
                if item['type'] == 'Text' and item['text_representation']:
                    # Replace null characters and split by new lines
                    for seg in item['text_representation'].replace("\x00", "fi").replace("\\n", "\n").split('\n\n'):
                        split_docs.append(Document(page_content = seg.strip()))
                        
            return split_docs
    else:
        print(f"File {json_path} does not exist.")
        return []

