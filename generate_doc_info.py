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

from files.text import split_with_langchain, get_presplit_file, chunk_and_partition_pdf_file
from files.text import index_split_paragraphs
from crawl.crawler_queue import get_crawled_paths

from datetime import datetime
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document

from aryn_sdk.partition import partition_file
# from aryn_sdk.config import ArynConfig

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from graph_db import GraphAccessor

from dotenv import load_dotenv, find_dotenv

_ = load_dotenv(find_dotenv())

DOWNLOAD_DIR = os.getenv("PDF_PATH", os.path.expanduser("~/Downloads"))

graph_db = GraphAccessor()

        
def handle_file(path: str, use_aryn: bool = False):
    pdf_path = os.path.join(DOWNLOAD_DIR, path)
    # Get today's date
    the_date = datetime.now().date()
    
    if path.endswith('.pdf.json'):
        path = path.replace('.json', '')
        
    if path.endswith('.pdf'):                    
        if use_aryn:
            split_docs = chunk_and_partition_pdf_file(pdf_path)
        else:               
            # Parse the PDF using Langchain PDF parser
            split_docs = split_with_langchain(pdf_path)  # Use the Langchain splitter to split the documents
    else:
        print(f"Non-PDF file: {pdf_path}")
        split_docs = get_presplit_file(pdf_path)
    
    if len(split_docs):
        index_split_paragraphs(split_docs, path, the_date)
        
    graph_db.commit()
    
def parse_pdfs_and_index(use_aryn: bool = False):
    # Fetch all papers
    #papers = graph_db.exec_sql("SELECT id, path FROM crawled;")
    papers = get_crawled_paths()

    for paper in papers:
        paper_id = paper['id']
        path = paper['path']
        try:
            if not GraphAccessor().paper_exists(path):
                handle_file(path, use_aryn)
            else:
                print(f"Paper {path} is already indexed with ID {paper_id}.")

        except Exception as e:
            print(f"Error processing PDF {path}: {e}")
            traceback.print_exc()
            
if __name__ == "__main__":
    parse_pdfs_and_index()