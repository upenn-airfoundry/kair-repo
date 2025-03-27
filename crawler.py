#########
## Trivial web crawl
##
## Iterate over database table, fetch PDFs, and mark as crawled

import requests
import os
from datetime import datetime
from graph_db import GraphAccessor

from dotenv import load_dotenv, find_dotenv
_ = load_dotenv(find_dotenv())

graph_db = GraphAccessor()

# Directory to save downloaded PDFs
DOWNLOADS_DIR = os.getenv("PDF_PATH", os.path.expanduser("~/Downloads"))

def fetch_and_crawl():
    # Ensure the downloads directory exists
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)

    rows = graph_db.exec_sql("SELECT id, url FROM crawl_queue ORDER BY id ASC;")

    for row in rows:
        crawl_id, url = row
        try:
            # Fetch the PDF from the URL
            response = requests.get(url, timeout=10)
            response.raise_for_status()  # Raise an error for HTTP errors

            # Save the PDF locally
            pdf_base = f"{crawl_id}.pdf"
            pdf_filename = os.path.join(DOWNLOADS_DIR, pdf_base)
            with open(pdf_filename, "wb") as pdf_file:
                pdf_file.write(response.content)

            # Add the crawled ID to the crawled table
            graph_db.execute(
                "INSERT INTO crawled (id, crawl_time, path) VALUES (%s, %s, %s);",
                (crawl_id, datetime.now().date(), pdf_base)
            )

            # Commit the transaction
            graph_db.commit()

            print(f"Successfully crawled and saved: {url}")

        except requests.RequestException as e:
            print(f"Failed to fetch URL {url}: {e}")
        except Exception as e:
            print(f"Error processing crawl ID {crawl_id}: {e}")

if __name__ == "__main__":
    fetch_and_crawl()