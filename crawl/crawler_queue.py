from backend.graph_db import GraphAccessor
from typing import List, Dict

import logging
import asyncio

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
from entities.generate_doc_info import handle_file

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
            try:
                # Insert the URL into the crawl_queue table
                graph_db.execute(
                    "INSERT INTO crawl_queue (create_time, url, comment) VALUES (%s, %s, %s);",
                    (datetime.now().date(), url, None)
                )
                added_count += 1
            except Exception as e:
                logging.warning(f"Could not add URL {url}, probably already exists: {e}")
                # graph_db.rollback()


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
    def get_urls_to_crawl(cls, max: int = None) -> List[Dict[str, str]]: # type: ignore
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

    @classmethod
    async def extract_from_urls(cls, items, task_id: int, task_description: str, task_schema: str) -> int:
        """
        Given a set of URLs (list[str] or dict with 'urls'/'items'), ensure they are in the crawl_queue,
        download into DOWNLOADS_DIR (matching web_fetch.py), generate TEI via fetch_and_crawl_items,
        and index newly crawled PDFs via handle_file.
        """
        # Normalize to a list of URLs
        urls: List[str] = []
        if not items:
            return 0
        if isinstance(items, dict):
            if isinstance(items.get("urls"), list):
                urls = [u for u in items["urls"] if isinstance(u, str)]
            elif isinstance(items.get("items"), list):
                for it in items["items"]:
                    if isinstance(it, str):
                        urls.append(it)
                    elif isinstance(it, dict) and isinstance(it.get("url"), str):
                        urls.append(it["url"])
        elif isinstance(items, list):
            for it in items:
                if isinstance(it, str):
                    urls.append(it)
                elif isinstance(it, dict) and isinstance(it.get("url"), str):
                    urls.append(it["url"])
        elif isinstance(items, str):
            urls = [items]

        if not urls:
            logging.info("extract_from_urls: no URLs provided")
            return 0

        # Ensure each URL is present in crawl_queue; collect (id,url) rows
        rows: List[Dict[str, str]] = []
        for url in urls:
            try:
                found = graph_db.exec_sql("SELECT id FROM crawl_queue WHERE url = %s LIMIT 1;", (url,))
                if found:
                    cid = int(found[0][0])
                else:
                    inserted = graph_db.exec_sql(
                        "INSERT INTO crawl_queue (create_time, url, comment) VALUES (%s, %s, %s) RETURNING id;",
                        (datetime.now().date(), url, f"task:{task_id}" if task_id else None)
                    )
                    cid = int(inserted[0][0])
                rows.append({"id": cid, "url": url})
            except Exception as e:
                logging.warning(f"extract_from_urls: failed to queue URL {url}: {e}")
        try:
            graph_db.commit()
        except Exception as e:
            logging.debug(f"extract_from_urls: commit warning (ignored): {e}")

        if not rows:
            return 0

        # Ensure download dir exists and crawl (downloads + TEI)
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
        from crawl.web_fetch import fetch_and_crawl_items
        try:
            await asyncio.to_thread(fetch_and_crawl_items, rows, DOWNLOADS_DIR)
        except Exception as e:
            logging.error(f"extract_from_urls: fetch_and_crawl_items failed: {e}")
            return 0

        # Index newly crawled documents for these IDs
        try:
            id_list = [int(r["id"]) for r in rows]
            docs = graph_db.exec_sql(
                "SELECT c.id, c.path, cq.url "
                "FROM crawled c LEFT JOIN crawl_queue cq ON c.id = cq.id "
                "WHERE c.id = ANY(%s);",
                (id_list,)
            )
            tasks = []
            for _cid, path, url in docs:
                # Skip if already indexed
                try:
                    if graph_db.exists_document(url):
                        continue
                except Exception:
                    # If exists check fails, try to index anyway
                    pass
                # Skip external file:// paths (not under DOWNLOADS_DIR)
                if isinstance(path, str) and path.startswith("file://"):
                    logging.debug(f"extract_from_urls: skipping external local file {path}")
                    continue
                # handle_file expects path relative to DOWNLOAD_DIR
                tasks.append(asyncio.to_thread(handle_file, path, url, False))
            if tasks:
                await asyncio.gather(*tasks)
        except Exception as e:
            logging.error(f"extract_from_urls: indexing failed: {e}")

        return len(rows)
