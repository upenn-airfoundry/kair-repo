from datetime import datetime
from graph_db import GraphAccessor

# List of URLs to process
urls = [
    "https://onlinelibrary.wiley.com/doi/pdf/10.1111/pbi.13913",
    "https://onlinelibrary.wiley.com/doi/pdfdirect/10.1111/pbi.12657",
    "https://onlinelibrary.wiley.com/doi/epdf/10.1111/pbi.14591",
    "https://arxiv.org/pdf/2503.11248",
    "https://arxiv.org/pdf/2503.14929",
    "https://arxiv.org/pdf/2503.06902",
    "https://arxiv.org/pdf/2503.01642"
]

graph_db = GraphAccessor()

def process_urls():
    added_count = 0

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