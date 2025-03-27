# kair-repo

These are the building blocks for the KAIR project.  You will need to update `.env` to match your configuration and we expect a PostgreSQL / TimescaleDB engine accessible via port 5432, with pgvectorscale.

1. `create_db.sql`: Creates the host database in PostgreSQL
2. `frontier_queue.py`: Adds a number of URLs to the table representing the frontier queue for crawling
3. `crawler.py`: Fetches the URLs from the frontier queue
4. `generate_doc_info.py`: Parses the PDFs, chunks them for RAG, and generates a paper descriptor, author info (+ links), a summary.

Key tables for reasoning about relationships:
* authors (can use for provenance)
* paper_authors
* papers
* paper_tags (link to papers; tag + content; tag indexed, content embedded)
  - Pre-analysis of papers yields a _summary_ and a _field_ or topic
* paragraphs (link to papers; content embedded)
* paragraph_tags
