
import datetime
from typing import Any, List, Optional
import os
import pandas as pd
import contextlib

import json
from langchain_core.documents import Document

import requests
from io import StringIO, BytesIO

from backend.graph_db import GraphAccessor
from files.tables import read_csv, read_json, read_jsonl, read_mat, read_xml
from files.pdfs import chunk_and_partition_pdf_file, split_pdf_with_langchain

#from langchain_community.document_loaders.blob_loaders import FileSystemBlobLoader
from langchain_community.document_loaders.generic import GenericLoader
from langchain_community.document_loaders.parsers import GrobidParser

from files.text import index_split_paragraphs_new


DOWNLOAD_DIR = os.getenv("PDF_PATH", os.path.expanduser("~/Downloads"))
parser = None
try:
    parser = GrobidParser(segment_sentences=False,
                            grobid_server=os.getenv("GROBID_SERVER", "http://localhost:8070"))
except Exception as e:
    print("GrobidParser is not available. Defaulting to Langchain parser.")
    parser = None        

class ParsedObject:
    def __init__(self):
        self.splits = 1
        self.objects = []
        self.parents = []
        self.sub_objects = []
        self.metadata = {}
        the_date = datetime.datetime.now().date()
        self.metadata["date_retrieved"] = the_date

    def set_metadata(self, metadata: dict):
        self.metadata.update(metadata)
    
    def get_metadata(self) -> dict:
        return self.metadata
    
    def get_sub_objects(self) -> list['ParsedObject']: # type: ignore
        return self.sub_objects
    
    def set_sub_objects(self, objs: list):
        self.sub_objects = objs
    
    def get_number_of_splits(self) -> int:
        return self.splits
    
    def set_number_of_splits(self, splits: int):
        self.splits = splits
        
    def set_split_objects(self, objects: list):
        self.objects = objects
        self.splits = len(objects)
        
    def get_split_objects(self) -> list:
        return self.objects
    
    def get_composite_object(self) -> Any:
        return ''.join([str(o) for o in self.objects])
    
    def get_entity_type(self) -> str:
        return 'json_data'
    
    def write_to_entity(self, graph_db: GraphAccessor):
        graph_db.add_json(
            self.metadata.get('name', ''), 
            self.get_metadata().get('description',''),
            self.get_composite_object(),
            self.metadata.get('url', ''))
    
class FileParser:
    def __init__(self) -> None:
        pass

    async def parse(self, local_file: str, url: str) -> Optional[ParsedObject]:
        return None
    
    @classmethod
    def get_parser(cls, local_file: str, url: str, content_type: str, use_aryn: bool = False) -> 'FileParser':
        """
        Get the appropriate parser for the given file URL. Specifically looks
        at the extension in the URL, which isn't 100% foolproof. If it isn't a
        known extension, it tries request.headers to get the mime type.

        Args:
            url (str): The URL of the file to parse.

        Returns:
            FileParser: An instance of the appropriate parser class.
        """
        
        if content_type == 'application/pdf' or content_type == 'application/json' or content_type == 'text/plain' or content_type == 'text/markdown' or content_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' or content_type == 'application/msword' \
            or content_type == 'text/html' or content_type == 'text/htm' or content_type == 'application/vnd.openxmlformats-officedocument.presentationml.presentation' or content_type == 'application/vnd.ms-powerpoint' or content_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' or content_type == 'application/vnd.ms-excel' or \
            url.endswith('.pdf') or url.endswith('.pdf.json') or url.endswith('.txt') or url.endswith('.md') or url.endswith('.docx') or url.endswith('.doc') \
            or url.endswith('.html') or url.endswith('.htm') or url.endswith('.pptx') or url.endswith('.ppt') or url.endswith('.xlsx') or url.endswith('.xls'):
            if parser:
                return DocumentParser(GrobidExtractorFactory())
            else:
                return DocumentParser(LangchainExtractorFactory())
        elif content_type == 'application/jsonl' or content_type == 'application/json' or content_type == 'application/csv' or content_type == 'application/xml' or content_type == 'application/x-matlab' or content_type == 'application/x-matlab'  or \
            url.endswith('.jsonl') or url.endswith('.json') or url.endswith('.csv') or url.endswith('.xml') or url.endswith('.mat') or url.endswith('.tsv'):
            return TableParser()
        else:
            # if url.startswith("http://") or url.startswith("https://"):
            #     with contextlib.suppress(requests.exceptions.RequestException):
            #         response = requests.head(url, allow_redirects=True)
            #         if response.status_code == 200:
            #             content_type = response.headers.get('Content-Type', '').split(';')[0].strip()
                        
            table_mime_types = [
                "application/jsonl",
                "application/tsv",
                "text/tab-separated-values",
                "application/csv",
                "text/csv",
                "application/xml",
                "text/xml",
                "application/json",
                "application/matlab",
            ]
            
            if content_type in table_mime_types:
                return TableParser()

            return DocumentParser(LangchainExtractorFactory())
    
class TableObject(ParsedObject):
    def set_url(self, filename: str):
        self.metadata['url'] = filename
        
    def set_schema(self, schema: pd.Series):
        self.schema = schema
        
    def get_schema(self) -> pd.Series:
        return self.schema

    def get_entity_type(self) -> str:
        return 'table'
    
    def write_to_entity(self, graph_db: GraphAccessor):
        return super().write_to_entity(graph_db)
    
class TableParser(FileParser):
    def __init__(self) -> None:
        super().__init__()
        self.df = None
        
    async def parse(self, local_file: str, url: str) -> Optional[TableObject]:
        obj = TableObject()
        
        mime_type = ''
        # if (url.startswith("file://")):
        #     filename = url[7:]
            
        #     while '..' in filename:
        #         filename.replace('..', '.')
                
        #     file = DOWNLOAD_DIR + filename
        
        file = local_file
            
        if file.endswith('.jsonl'):
            mime_type = "application/jsonl"
        elif file.endswith('.tsv'):
            mime_type= "application/tsv"
        elif file.endswith('.csv'):
            mime_type = "application/csv"
        elif file.endswith('.xml'):
            mime_type = "application/xml"
        elif file.endswith('.html'):
            mime_type = "text/html"
        elif file.endswith('.mat'):
            mime_type = "application/matlab"
            
        try:
            if mime_type == 'application/matlab':
                with open(file, "rb") as f:
                    contents = f.read()
                    buffer = BytesIO(contents)
            else:
                with open(file, "r", encoding='utf-8') as f:
                    contents = f.read()
                    buffer = StringIO(contents)
        except:
            raise IOError(f"Unable to read file {file}")

        # elif url.startswith("http://") or url.startswith("https://"):
        #     # fetch with requests, figure out mime type
        #     response = requests.get(url)
        #     if response.status_code != 200:
        #         raise IOError(f"Unable to request from {url}")
        #     try:
        #         mime_type_header = response.headers['Content-Type']
        #         mime_type = mime_type_header.split(';')[0].strip()
        #     except KeyError:
        #         mime_type = 'application/octet-stream'
            
        #     if mime_type == 'application/matlab':
        #         buffer = BytesIO(response.content)
        #     else:
        #         buffer = StringIO(response.text)
        # else:
        #     raise IOError(f"Unable to get mime type of {url}")
            
        if mime_type == "application/jsonl":
            content = read_jsonl(buffer) # type: ignore
        elif mime_type == 'application/tsv':
            content = read_csv(buffer, delimiter='\t') # type: ignore
        elif mime_type == 'application/csv':
            content = read_csv(buffer) # type: ignore
        elif mime_type == 'application/xml':
            content = read_xml(buffer) # type: ignore
        elif mime_type == 'application/json':
            content = read_json(buffer) # type: ignore
        elif mime_type == 'application/matlab':
            content = read_mat(buffer) # type: ignore
        else:
            raise ValueError(f'Unable to properly parse {url}')

        self.df = content
        # Single object in JSON
        obj.set_split_objects([content.to_json()])
        obj.set_schema(content.dtypes)
        
        return obj
    
    
class DocumentObject(ParsedObject):
    def __init__(self, chunk_token_overlap: int = 0):
        super().__init__()
        self.chunk_token_overlap = chunk_token_overlap
        
    def _get_token_overlap(self) -> int:
        return self.chunk_token_overlap
        
    def get_composite_object(self) -> Any:
        if self._get_token_overlap() == 0:
            return super().get_composite_object()
        else:
            raise ValueError("Need to eliminate chunk token overlap, not implemented")

    def get_entity_type(self) -> str:
        return 'paper'
    
    def write_to_entity(self, graph_db: GraphAccessor):
        # return super().write_to_entity(graph_db)
        index_split_paragraphs_new(
            self.get_composite_object(),
            self.get_split_objects(),
            self.get_metadata()['url'],
            self.get_metadata()['date_retrieved']
        )

class DocumentExtractor:
    def __init__(self, local_file: str, url: str):
        self.local_file = local_file
        self.url = url
    
    async def parse(self):
        pass
    
    def get_object(self) -> DocumentObject:
        return DocumentObject()
    
class ArynExtractor(DocumentExtractor):
    def __init__(self, local_file: str, url: str):
        super().__init__(local_file, url)
        
    async def parse(self):
        self.data = chunk_and_partition_pdf_file(self.local_file, '')
        
    def get_object(self) -> DocumentObject:
        obj = DocumentObject()
        split_docs = []
        for item in self.data['elements']:
            if item['type'] == 'Text' and item['text_representation']:
                # Replace null characters and split by new lines
                for seg in item['text_representation'].replace("\x00", "fi").replace("\\n", "\n").split('\n\n'):
                    split_docs.append(seg.strip())
        
        obj.set_metadata({'url': self.url})
        obj.set_split_objects(split_docs)
        return obj

class LangchainExtractor(DocumentExtractor):
    def __init__(self, local_file: str, url: str, chunk_size: int = 1000, chunk_overlap: int = 200):
        super().__init__(local_file, url)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
    async def parse(self):
        self.doc_list = split_pdf_with_langchain(self.local_file, self.chunk_size, self.chunk_overlap)

        
    def get_object(self) -> DocumentObject:
        obj = DocumentObject()

        obj.set_metadata({'url': self.url})
        obj.set_split_objects([doc.page_content for doc in self.doc_list])

        return obj

class GrobidExtractor(DocumentExtractor):
    def __init__(self, local_file: str, url: str, chunk_size: int = 1000, chunk_overlap: int = 200):
        super().__init__(local_file, url)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
    async def parse(self):
        loader = GenericLoader.from_filesystem(
            path=DOWNLOAD_DIR, 
            glob=self.url.split('/')[-1],
            suffixes=[".pdf"],
            parser=parser)
        self.doc_list = loader.load()


    def get_object(self) -> DocumentObject:
        obj = DocumentObject()

        if len(self.doc_list):
            obj.set_metadata(self.doc_list[0].metadata)
        obj.get_metadata()['url'] = self.url
        obj.set_split_objects([doc.page_content for doc in self.doc_list])

        return obj


class ExtractorFactory:
    def get_extractor(self, local_file: str, url: str) -> DocumentExtractor:
        return DocumentExtractor(local_file, url)
    
class ArynExtractorFactory(ExtractorFactory):
    def get_extractor(self, local_file: str, url: str) -> ArynExtractor:
        return ArynExtractor(local_file, url)
    
class GrobidExtractorFactory(ExtractorFactory):
    def get_extractor(self, local_file: str, url: str) -> GrobidExtractor:
        return GrobidExtractor(local_file, url)

class LangchainExtractorFactory(ExtractorFactory):
    def get_extractor(self, local_file: str, url: str) -> LangchainExtractor:
        return LangchainExtractor(local_file, url)


class DocumentParser(FileParser):
    def __init__(self, extractor: ExtractorFactory) -> None:
        super().__init__()
        self.extractor_factory = extractor

    async def parse(self, local_file: str, url: str) -> Optional[DocumentObject]:
        extractor = self.extractor_factory.get_extractor(local_file, url)

        await extractor.parse()
        
        return extractor.get_object()
