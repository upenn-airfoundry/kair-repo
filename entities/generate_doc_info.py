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
import pandas as pd
import logging

from files.pdfs import split_pdf_with_langchain, get_presplit_aryn_file, chunk_and_partition_pdf_file, get_pdf_splits
from files.text import index_split_paragraphs

from files.parser import FileParser

from files.tables import read_csv, read_json, read_jsonl, read_mat, read_xml, sample_rows_to_string
from files.tables import create_table_entity

from datetime import datetime
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document

from aryn_sdk.partition import partition_file
# from aryn_sdk.config import ArynConfig

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from backend.graph_db import GraphAccessor

from dotenv import load_dotenv, find_dotenv

_ = load_dotenv(find_dotenv())

DOWNLOAD_DIR = os.getenv("PDF_PATH", os.path.expanduser("~/Downloads"))

graph_db = GraphAccessor()

        
async def handle_file(path: str, url: str, content_type: str, use_aryn: bool = False):
    # pdf_path = os.path.join(DOWNLOAD_DIR, path)

    parser = FileParser.get_parser(path, url, content_type, use_aryn)    
    
    parsed_object = await parser.parse(path, url)

    # # Get today's date
    the_date = datetime.now().date()
    
    # if path.endswith('.pdf.json'):
    #     path = path.replace('.json', '')
        
    # if path.endswith('.pdf'):
    #     if use_aryn:
    #         split_docs = get_pdf_splits(pdf_path, 0)
    #     else:               
    #         # Parse the PDF using Langchain PDF parser
    #         split_docs = get_pdf_splits(pdf_path, 1)  # Use the Langchain splitter to split the documents
    # elif path.endswith('.jsonl') or path.endswith('.json') or path.endswith('.csv') or path.endswith('.mat') or path.endswith('.xml'):
    #     path = path[7:] # Remove file://
    #     if path.endswith('.jsonl'):
    #         df = read_jsonl(path)
    #     elif path.endswith('.json'):
    #         df = read_json(path)
    #     elif path.endswith('.csv'):
    #         df = read_csv(path)
    #     elif path.endswith('.mat'):
    #         df = read_mat(path)
    #     elif path.endswith('.xml'):
    #         df = read_xml(path)

    #     create_table_entity(path, df, graph_db)        
    # else:
    #     logging.info(f"Non-PDF file: {pdf_path}")
    #     split_docs = get_presplit_aryn_file(pdf_path)
    
    if parsed_object is not None:
        split_docs = parsed_object.get_split_objects()

        if split_docs is not None and len(split_docs) == 0:
            parsed_object.write_to_entity(graph_db)

    # graph_db.commit()
    
async def parse_files_and_index(use_aryn: bool = False):
    """
    Parse files and index them in the database.  These could be PDFs or tables.
    This function will check if the document is already indexed in the database.
    If it is, it will skip the indexing process.
    If it is not, it will parse the document and index it.
    This function will also handle any errors that occur during the parsing and indexing process.

    Args:
        use_aryn (bool, optional): Uses the Aryn parser. Defaults to False.
    """
    from crawl.crawler_queue import CrawlQueue
    files = CrawlQueue.get_crawled_paths()

    for doc in files:
        doc_id = doc['id']
        path = doc['path']
        url = doc['url']
        try:
            if not GraphAccessor().exists_document(url):
                await handle_file(path, url, use_aryn)
            else:
                logging.info(f"Document {path} is already indexed with ID {doc_id}.")

        except Exception as e:
            logging.error(f"Error processing PDF {path}: {e}")
            traceback.print_exc()
            
