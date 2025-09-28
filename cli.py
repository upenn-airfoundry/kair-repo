##################
## Simple module to add URLs into the database frontier queue
## for crawling
##
## Copyright (C) Zachary G. Ives, 2025
##################

import argparse
import os
from datetime import datetime
from backend.graph_db import GraphAccessor
from dblp_parser.dblp_parser import DBLP
from dotenv import load_dotenv, find_dotenv

from crawl.crawler_queue import CrawlQueue
from crawl.web_fetch import fetch_and_crawl_frontier

from entities.generate_doc_info import parse_files_and_index

from files.arxiv import load_arxiv_abstracts, classify_arxiv_categories
import yaml

graph_db = GraphAccessor()

find_dotenv()
_ = load_dotenv()

PDFS_DIR = os.getenv("PDF_PATH", os.path.expanduser("~/Downloads") + '/pdfs')
DATA_DIR = os.getenv("DATA_PATH", os.path.expanduser("~/Downloads") + '/data')

def add_urls_to_frontier(url_list: list[str]):
    """Main function to add URLs to the crawl queue."""
    count = add_urls_to_crawl_queue(url_list) # type: ignore
    
    print(f"Added {count} URLs to the crawl queue.")
    
def add_urls_to_frontier_from_file(file_path: str = "starting_points/papers.yaml"):
    """Add URLs from a specified file to the crawl queue."""
    with open(file_path, "r") as f:
        urls = yaml.safe_load(f)

    if not isinstance(urls, list):
        raise ValueError("File must contain a list of URLs.")

    count = add_urls_to_crawl_queue(urls) # type: ignore
    print(f"Added {count} URLs from {file_path} to the crawl queue.")
    
def crawl_local_files(directory: str = PDFS_DIR):
    count = CrawlQueue.add_local_downloads_to_crawl_queue(directory)
    print(f"Added {count} local files to the crawl queue.")
    
def split_dblp():
    dblp = DBLP()
    dblp.download_latest_dump()
    dblp.parse_all('dblp.xml', "dblp.jsonl")

def main():
    """Main function to handle command-line arguments."""
    parser = argparse.ArgumentParser(description="CLI for managing the crawl queue and fetching documents.")
    parser.add_argument(
        "command",
        nargs="?",
        help="Command to execute. Options: 'add_crawl_list' to add URLs to the crawl queue, 'crawl' to fetch and crawl documents.",
    )
    args = parser.parse_args()

    if args.command == "add_crawl_list":
        print("Adding URLs to the crawl queue...")
        add_urls_to_frontier_from_file()
        print("Starting crawl...")
        fetch_and_crawl_frontier()
    elif args.command == "re_embed":
        print("Re-embedding all documents...")
        graph_db.re_embed_all_documents()
        graph_db.re_embed_all_tags()
    elif args.command == "arxiv":
        print("Starting arxiv load...")
        load_arxiv_abstracts()
    elif args.command == "arxiv_categories":
        classify_arxiv_categories()
    elif args.command == "add_local_files":
        crawl_local_files(PDFS_DIR)
        crawl_local_files(DATA_DIR)
        fetch_and_crawl_frontier()
    elif args.command == "process":
        parse_files_and_index()
    elif args.command == "dblp":
        if not os.path.exists('dblp.jsonl'):
            print("DBLP file not found. Downloading and parsing...")
            split_dblp()
        crawl_local_files(DATA_DIR)
    else:
        print("Usage:")
        print("  python cli.py dblp             # Generate DBLP JSONL file")
        print("  python cli.py add_crawl_list   # Add URLs to the crawl queue, fetch")
        print("  python cli.py add_local_files  # Add local files to the crawl queue, fetch")
        print("  python cli.py process          # Parse and index documents")
        print("  python cli.py --help           # Show this help message")

if __name__ == "__main__":
    main()