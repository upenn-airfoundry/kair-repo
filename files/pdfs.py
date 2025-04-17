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

from dotenv import load_dotenv, find_dotenv

_ = load_dotenv(find_dotenv())

DOWNLOAD_DIR = os.getenv("PDF_PATH", os.path.expanduser("~/Downloads"))

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

        
def split_pdf_with_langchain(pdf_path: str) -> list:
    loader = PyPDFLoader(pdf_path)
    documents = loader.load()
    
    # Use the most common splitter: RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
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

