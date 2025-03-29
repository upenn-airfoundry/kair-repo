##################
## Simple module to add URLs into the database frontier queue
## for crawling
##
## Copyright (C) Zachary G. Ives, 2025
##################

from datetime import datetime
from graph_db import GraphAccessor

from dotenv import load_dotenv, find_dotenv
_ = load_dotenv(find_dotenv())

import os

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

graph_db = GraphAccessor()

# Directory to save downloaded PDFs
DOWNLOADS_DIR = os.getenv("PDF_PATH", os.path.expanduser("~/Downloads")) + '/dataset_papers'

def process_urls():
    added_count = 0
    
    # For all pdfs in DOWNLOAD_DIR, add to the crawl queue if not already present
    for filename in os.listdir(DOWNLOADS_DIR):
        # Construct the full path to the file
        file_path = os.path.join(DOWNLOADS_DIR, filename)
        
        # Check if the file is a PDF
        if os.path.isfile(file_path) and filename.endswith(".pdf"):
            # Create the URL based on the filename (assuming a specific format)
            url = f"file://{file_path}"
            
            # Check if the URL already exists in the crawl_queue table
            exists = graph_db.exec_sql("SELECT 1 FROM crawl_queue WHERE url = %s;", (url,))
            
            if len(exists) == 0:
                # Insert the URL into the crawl_queue table
                graph_db.execute(
                    "INSERT INTO crawl_queue (create_time, url, comment) VALUES (%s, %s, %s);",
                    (datetime.now().date(), url, filename)
                )
                added_count += 1
                print(f"Added URL to crawl queue: {filename}")
    
    # Iterate through the list of URLs      
    for url in urls:
        # Check if the URL already exists in the crawl_queue table
        exists = graph_db.exec_sql("SELECT 1 FROM crawl_queue WHERE url = %s;", (url,))

        if len(exists) == 0:
            # Insert the URL into the crawl_queue table
            graph_db.execute(
                "INSERT INTO crawl_queue (create_time, url, comment) VALUES (%s, %s, %s);",
                (datetime.now().date(), url, None)
            )
            added_count += 1

    # Commit the transaction
    graph_db.commit()

    # Print the number of URLs added
    print(f"Done with {added_count} URLs")

if __name__ == "__main__":
    process_urls()