##################
## Simple module to add URLs into the database frontier queue
## for crawling
##
## Copyright (C) Zachary G. Ives, 2025
##################

import argparse
from datetime import datetime
from graph_db import GraphAccessor
from dblp_parser.dblp_parser import DBLP


from crawl.crawler_queue import add_to_crawled
from crawl.web_fetch import fetch_and_crawl_frontier

from crawl.crawler_queue import add_local_downloads_to_crawl_queue
from crawl.crawler_queue import add_urls_to_crawl_queue

graph_db = GraphAccessor()


def add_urls_to_frontier():
    """Main function to add URLs to the crawl queue."""
    count = 0
    count += add_urls_to_crawl_queue([
        "https://onlinelibrary.wiley.com/doi/pdf/10.1111/pbi.13913",
        "https://onlinelibrary.wiley.com/doi/pdfdirect/10.1111/pbi.12657",
        "https://onlinelibrary.wiley.com/doi/epdf/10.1111/pbi.14591",
        "https://arxiv.org/pdf/2503.11248",
        "https://arxiv.org/pdf/2503.14929",
        "https://arxiv.org/pdf/2503.06902",
        "https://arxiv.org/pdf/2503.01642",
        "https://arxiv.org/pdf/2407.11418",
        "https://arxiv.org/pdf/2405.14696",
        "https://arxiv.org/pdf/2502.03368",
        "https://arxiv.org/pdf/2410.12189",
        "https://arxiv.org/pdf/2501.05006",
        "https://vldb.org/cidrdb/papers/2025/p32-wang.pdf",
        "https://arxiv.org/pdf/2311.09818",
        "https://arxiv.org/pdf/2410.01837",
        "https://arxiv.org/pdf/2412.18022",
        "https://arxiv.org/pdf/2407.09522",
        "https://arxiv.org/pdf/2409.00847",
        "https://dl.acm.org/doi/pdf/10.14778/2732951.2732962",
        "https://arxiv.org/pdf/2502.07132",
        "https://dl.acm.org/doi/pdf/10.1145/2882903.2915212"
    ])
    
    print(f"Added {count} URLs to the crawl queue.")
    
def crawl_local_files():
    count += add_local_downloads_to_crawl_queue()
    print(f"Added {count} URLs to the crawl queue.")
    
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
        add_urls_to_frontier()
    elif args.command == "add_local_files":
        crawl_local_files()
    elif args.command == "crawl":
        fetch_and_crawl_frontier()
    elif args.command == "dblp":
        split_dblp()
    else:
        print("Usage:")
        print("  python cli.py add_crawl_list   # Add URLs to the crawl queue")
        print("  python cli.py add_local_files  # Add local files to the crawl queue")
        print("  python cli.py crawl            # Fetch and crawl documents")
        print("  python cli.py dblp             # Fetch and crawl documents")
        print("  python cli.py --help           # Show this help message")

if __name__ == "__main__":
    main()