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
from langchain_community.document_loaders.blob_loaders import FileSystemBlobLoader
from langchain_core.document_loaders import Blob
from langchain_community.document_loaders.generic import GenericLoader
from langchain_community.document_loaders.parsers import GrobidParser
from langchain_core.documents import Document

from crawl.web_fetch import parse_tei_xml
from doc2json.grobid2json.tei_to_json import convert_tei_xml_file_to_s2orc_json

from typing import Tuple

from aryn_sdk.partition import partition_file

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from files.text import get_metadata_from_docs

from dotenv import load_dotenv, find_dotenv

_ = load_dotenv(find_dotenv())

DOWNLOAD_DIR = os.getenv("PDF_PATH", os.path.expanduser("~/Downloads"))
GROBID_SERVER = os.getenv("GROBID_SERVER", "http://localhost:8070")

grobid_parser = None


def get_grobid_parser() -> GrobidParser:
    """
    Get the Grobid parser instance.
    :return: GrobidParser instance.
    """
    global grobid_parser
    if grobid_parser is None:
        grobid_parser = GrobidParser(segment_sentences=True, grobid_server=GROBID_SERVER)
    return grobid_parser

def get_pdf_splits(pdf_path: str, method: int, dir: str = DOWNLOAD_DIR) -> Tuple[dict, list]:
    """
    Load a PDF file and split it into smaller chunks.
    :param pdf_path: The path to the PDF file.
    :return: A list of split documents.
    """
    
    metadata = {}
    
    # Aryn partitioning
    if method == 0:
        data = chunk_and_partition_pdf_file(pdf_path, '')
        split_docs = []
        for item in data['elements']:
            if item['type'] == 'Text' and item['text_representation']:
                # Replace null characters and split by new lines
                for seg in item['text_representation'].replace("\x00", "fi").replace("\\n", "\n").split('\n\n'):
                    split_docs.append(Document(page_content = seg.strip()))
                    
        return get_metadata_from_docs(split_docs), split_docs
    
    # Grobid
    elif method == 1 and os.path.exists(os.path.dirname(pdf_path) + '/tei_xml/' + os.path.basename(pdf_path) + '.xml'):
        # Split the PDF directory from the PDF filename
        pdf_dir = os.path.dirname(pdf_path)
        pdf_filename = os.path.basename(pdf_path)
        if os.path.exists(pdf_dir + '/tei_xml/' + pdf_filename + '.xml'):
            
            paper = convert_tei_xml_file_to_s2orc_json(pdf_dir + '/tei_xml/' + pdf_filename + '.xml')
            print (paper.metadata.title)
            split_docs = [Document(para.text) for para in paper.body_text]
            md2 = get_metadata_from_docs(split_docs)
            return ({"title": paper.metadata.title, "authors": paper.metadata.authors, "summary": md2['summary'], "year": paper.metadata.year},
                split_docs)
            
    # Fallback to Langchain if no grobid
    else:
        if pdf_path.startswith('file://'):
            pdf_path = pdf_path[7:]
        split_docs = split_pdf_with_langchain(pdf_path)
        return get_metadata_from_docs(split_docs), split_docs
        
    # Else use Grobid
    # else:
        # loader = FileSystemBlobLoader(path=pdf_path)
        # blob = loader.load()[0]
        # return (metadata, list(get_grobid_parser().lazy_parse(blob)))
        raise ValueError("Invalid method. Use 0 for Aryn partitioning or 1 for Grobid.")
        


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

        
def split_pdf_with_langchain(pdf_path: str, chunk_overlap: int=200) -> list:
    loader = PyPDFLoader(pdf_path)
    documents = loader.load()
    
    # Use the most common splitter: RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=chunk_overlap)
    split_docs = splitter.split_documents(documents)
    
    return split_docs

def get_presplit_aryn_file(filename: str) -> list:
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

