from backend.graph_db import GraphAccessor
from typing import List, Dict

import logging

##################
## Simple module to add URLs into the database frontier queue
## for crawling
##
## Copyright (C) Zachary G. Ives, 2025
##################

from datetime import datetime

from dotenv import load_dotenv, find_dotenv
_ = load_dotenv(find_dotenv())

import os

graph_db = GraphAccessor()

# Directory to save downloaded PDFs
DOWNLOADS_DIR = os.getenv("PDF_PATH", os.path.expanduser("~/Downloads") + '/pdfs')

class CrawlQueue:
    '''
    Class to manage the crawl queue.
    '''

    @classmethod
    def add_local_downloads_to_crawl_queue(cls, download_dir: str = DOWNLOADS_DIR) -> int:
        """Add local files to the crawl queue.
        This function scans a specified directory for PDF files and adds their URLs to the crawl queue in the database.
        It checks if the URL already exists in the crawl queue to avoid duplicates.
        The URLs are constructed based on the local file path, assuming a specific format.
        The function returns the number of URLs added to the crawl queue.

        Args:
            download_dir (str, optional): Directory with files, defaults to DOWNLOADS_DIR.

        Returns:
            int: Number of URLs added to the crawl queue.
        """
        added_count = 0
        
        # For all pdfs in DOWNLOAD_DIR, add to the crawl queue if not already present
        for filename in os.listdir(download_dir):
            # Construct the full path to the file
            file_path = os.path.join(download_dir, filename)
            
            # Check if the file is valid
            if os.path.isfile(file_path):
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
                    logging.debug(f"Added URL to crawl queue: {filename}")
        
        # Commit the transaction
        graph_db.commit()

        # Print the number of URLs added
        logging.info(f"Done with {added_count} URLs")
        return added_count

    @classmethod
    def add_urls_to_crawl_queue(cls, url_list: List[str]) -> int:
        """Add a list of URLs to the crawl queue.
        This function checks if each URL already exists in the crawl queue to avoid duplicates.
        If a URL does not exist, it is added to the crawl queue with the current date and a comment of None.
        The function returns the number of URLs added to the crawl queue.

        Args:
            url_list (List[str]): List of URLs to be added to the crawl queue.

        Returns:
            int: Number of URLs added to the crawl queue.
        """
        added_count = 0
        
        # Iterate through the list of URLs      
        for url in url_list:
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
        return added_count


    @classmethod
    def add_to_crawled(cls, crawl_id: int, path: str) -> bool:
        # Verify the path isn't already in the crawled table
        existing_crawl = graph_db.exec_sql(
            "SELECT 1 FROM crawled WHERE path = %s;",
            (path,)
        )
        if existing_crawl:
            logging.debug(f"File {path} already exists in the crawled table. Skipping.")
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
            
        logging.info(f"Added {path} to crawled table with ID {crawl_id}.")
        graph_db.commit()
        return True

    @classmethod
    def get_urls_to_crawl(cls, max: int = None) -> List[Dict[str, str]]:
        """Fetch all URLs from the crawl queue.
        This function retrieves all URLs from the crawl queue in the database,
        ordered by their ID in ascending order.

        Returns:
            List[Dict[str, str]]: A list of dictionaries containing the crawl ID and URL.
        """
        
        if max is not None:
            rows = graph_db.exec_sql("SELECT id, url FROM crawl_queue c WHERE NOT EXISTS(SELECT * FROM crawled WHERE id=c.id) ORDER BY id ASC LIMIT %s;", (max,))
        else:
            rows = graph_db.exec_sql("SELECT id, url FROM crawl_queue c WHERE NOT EXISTS(SELECT * FROM crawled WHERE id=c.id) ORDER BY id ASC;")
        
        return [{"id": row[0], "url": row[1]} for row in rows]

    @classmethod
    def get_crawled_paths(cls) -> List[Dict[str, str]]:
        """Fetch all files/paths from the crawled table.
        This function retrieves all paths from the crawled table in the database,
        ordered by their ID in ascending order.

        Returns:
            List[Dict[str, str]]: A list of dictionaries containing the crawl ID and file path.
        """
        
        rows = graph_db.exec_sql("SELECT c.id, path, url FROM crawled c LEFT JOIN crawl_queue ON c.id = crawl_queue.id ORDER BY id ASC;")
        
        return [{"id": row[0], "path": row[1], "url": row[2]} for row in rows]

    @classmethod
    def get_crawled_paths_by_date(cls, date: str) -> List[Dict[str, str]]:
        """Fetch all files/paths from the crawled table by date.
        This function retrieves all URLs from the crawled table in the database
        for a specific date, ordered by their ID in ascending order.

        Args:
            date (str): The date to filter the crawled URLs.

        Returns:
            List[Dict[str, str]]: A list of dictionaries containing the crawl ID and file path.
        """
        
        rows = graph_db.exec_sql("SELECT id, path FROM crawled WHERE crawl_time = %s ORDER BY id ASC;", (date,))
        
        return [{"id": row[0], "path": row[1]} for row in rows]
