#########
## Simple, single-threaded web crawler
##
## Iterate over database table, fetch PDFs, and mark as crawled
##
## Copyright (C) Zachary G. Ives, 2025
##################

import requests
import os
from datetime import datetime
from graph_db import GraphAccessor

from dotenv import load_dotenv, find_dotenv
_ = load_dotenv(find_dotenv())

graph_db = GraphAccessor()

# Directory to save downloaded PDFs
DOWNLOADS_DIR = os.getenv("PDF_PATH", os.path.expanduser("~/Downloads"))

def add_to_crawled(crawl_id: int, path: str) -> bool:
    # Verify the path isn't already in the crawled table
    existing_crawl = graph_db.exec_sql(
        "SELECT 1 FROM crawled WHERE path = %s;",
        (path,)
    )
    if existing_crawl:
        print(f"File {path} already exists in the crawled table. Skipping.")
        return False

    # Add the crawled ID to the crawled table
    if crawl_id >= 1:
        graph_db.execute(
            "INSERT INTO crawled (id, crawl_time, path) VALUES (%s, %s, %s);",
            (crawl_id, datetime.now().date(), path)
        )
    else:
        graph_db.execute(
            "INSERT INTO crawled (crawl_time, path) VALUES (%s, %s);",
            (datetime.now().date(), path)
        )
    return True

def fetch_and_crawl():
    # Ensure the downloads directory exists
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)

    rows = graph_db.exec_sql("SELECT id, url FROM crawl_queue ORDER BY id ASC;")

    for row in rows:
        crawl_id, url = row
        try:
            if url.startswith('file://'):
                pdf_base = url.split('/')[-1]  # Extract the filename from the URL
                pdf_filename = os.path.join(DOWNLOADS_DIR + "/dataset_papers/" + pdf_base)  # Construct the local file path
                if os.path.exists(DOWNLOADS_DIR + "/chunked_files/" + pdf_base + ".json"):
                    if add_to_crawled(crawl_id, "chunked_files/" + pdf_base + ".json"):  # Mark this PDF as crawled in the database
                        print(f"Registered pre-chunked file: {pdf_filename}")
                else:
                    if add_to_crawled(crawl_id, "dataset_papers/" + pdf_base):  # Mark this PDF as crawled in the database
                        print(f"Registered pre-crawled file: {pdf_filename}")
            else:
                # Save the PDF locally
                pdf_base = f"{crawl_id}.pdf"
                pdf_filename = os.path.join(DOWNLOADS_DIR, pdf_base)
                
                if os.path.exists(pdf_filename):
                    print(f"File {pdf_filename} already exists. Skipping download.")
                    add_to_crawled(crawl_id, pdf_base)
                    continue

                # Fetch the PDF from the URL
                response = requests.get(url, timeout=10)
                response.raise_for_status()  # Raise an error for HTTP errors

                with open(pdf_filename, "wb") as pdf_file:
                    pdf_file.write(response.content)
                    
                if add_to_crawled(crawl_id, pdf_base):  # Mark this PDF as crawled in the database
                    print(f"Successfully crawled and saved: {url}")

        except requests.RequestException as e:
            print(f"Failed to fetch URL {url}: {e}")
        except Exception as e:
            print(f"Error processing crawl ID {crawl_id}: {e}")

    graph_db.commit()
    
if __name__ == "__main__":
    fetch_and_crawl()