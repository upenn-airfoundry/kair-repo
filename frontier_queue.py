##################
## Simple module to add URLs into the database frontier queue
## for crawling
##
## Copyright (C) Zachary G. Ives, 2025
##################

from datetime import datetime
from graph_db import GraphAccessor

from crawl.crawler_queue import add_local_downloads_to_crawl_queue
from crawl.crawler_queue import add_urls_to_crawl_queue

# List of URLs to process
urls = [
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
]


if __name__ == "__main__":
    count = 0
    count += add_local_downloads_to_crawl_queue(DOWNLOADS_DIR)
    count += add_urls_to_crawl_queue(urls)
    
    print(f"Added {count} URLs to the crawl queue.")