# kair-repo

These are the building blocks for the KAIR project.  You will need to update `.env` to match your configuration and we expect a PostgreSQL / TimescaleDB engine accessible via port 5432, with pgvectorscale.  You can do this with the following [Docker container](https://github.com/timescale/pgvectorscale?tab=readme-ov-file#using-a-pre-built-docker-container).

The SQL in [create_db.sql](create_db.sql) generates a sample user and creates basic relations.

## Conceptual Framework

The main backbone of the project is a simple graph representation of **entities** (nodes) and **associations** (edges). Entities include various properties and come from a closed set of types (enum). They are expected to have an *embedding*.

Edges can be explicitly encoded (with support, including *negative support* saying they should not exist); but implicitly one could have an edge between any two entities -- by looking at the distance between the entities' *embeddings*. Explicit edges can be labeled from an open set of types (arbitrary strings).

## Key Objectives

This is a data platform for going beyond RAG to (1) allow arbitrary annotations, (2) reason about relationships.  The goal is to support *data enrichment* and *data annotation*.  A few examples include:

1. Reason about provenance and trust, by knowing about sources
2. Pre-process papers or paragraphs (splits) and annotate with tag-values
3. Fetch related tag-values as we process a paragraph/chunk
4. Reason about tables or chunks relative to their papers
5. Query for papers in a domain
6. Apply link analysis algorithms

And more.

## Stages

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
