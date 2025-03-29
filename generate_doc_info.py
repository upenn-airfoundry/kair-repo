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

from aryn_sdk.partition import partition_file
# from aryn_sdk.config import ArynConfig

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
    concatenated_text = " ".join(doc.page_content for doc in split_docs[:2])

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

    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        print("Raw response text:")
        print(response_text)
    
    # Index the paragraphs
    for doc in split_docs:
        content = doc.page_content
        print(f"Indexing paragraph: {content}")
        (para_id, embedding) = graph_db.add_paragraph(paper_id, content)
    graph_db.commit()
    return paper_id


def chunk_and_partition_pdf_file(filename):
  data = None
  with open(DOWNLOAD_DIR + filename, "rb") as f:
    #  data = partition_file(f, aryn_api_key="eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJzdWIiOnsiZW1sIjoianZhcnVuQHNlYXMudXBlbm4uZWR1IiwiYWN0IjoiNDE4NTQ2Njk5NDEzIn0sImlhdCI6MTcyNjcxMzYwNS43NzYyMDAzfQ.ugaWkJqMQkzGUVz8c7KnU7DHxlP_JehUJF1NY74w30whYK-BCVPfJCZv0DVXG1n2vL7TLKl135bv4eTXlwPACA")
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
    with open(f'/content/chunked_files/{filename}.json', 'w') as f:
        json.dump(data, f)

        
def split_with_langchain(pdf_path: str) -> list:
    loader = PyPDFLoader(pdf_path)
    documents = loader.load()
    
    # Use the most common splitter: RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    split_docs = splitter.split_documents(documents)
    
    return split_docs
    
def parse_pdfs_and_index(use_aryn: bool = False):
    # Fetch all papers
    papers = graph_db.exec_sql("SELECT id, path FROM crawled;")

    for paper_id, path in papers:
        # Parse the PDF using Langchain PDF parser
        pdf_path = os.path.join(DOWNLOAD_DIR, path)
        
        print(f"Parsing PDF: {path}")
        
        # Get today's date
        the_date = datetime.now().date()
        
        try:
            if not GraphAccessor().paper_exists(path):
                if use_aryn:
                    split_docs = chunk_and_partition_pdf_file(pdf_path)
                else:               
                    split_docs = split_with_langchain(pdf_path)  # Use the Langchain splitter to split the documents

                if len(split_docs):
                    index_split_paragraphs(split_docs, pdf_path, the_date)
            else:
                print(f"Paper ID {paper_id} already exists in the database. Skipping parsing for {path}.")

        except Exception as e:
            print(f"Error processing PDF {pdf_path}: {e}")
            traceback.print_exc()
            
if __name__ == "__main__":
    parse_pdfs_and_index()