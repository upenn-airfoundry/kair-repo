# kair-repo

These are the building blocks for the KAIR project.  You will need to update `.env` (copy from `sample.env`) to match your configuration.

## Database

We expect a PostgreSQL / TimescaleDB engine accessible via port 5432, with pgvectorscale.  With Docker installed, you can run `source timescaledb.sh` to install the Docker container.  Then the SQL in [create_db.sql](create_db.sql) generates a sample user and creates basic relations.  Some options:

Linux:
```bash
apt install postgresql
psql -d "postgres://postgres:${DB_PASSWORD}@localhost/postgres" -f create_db.sql
```

Mac:
```bash
brew install postgresql
psql -d "postgres://postgres:${DB_PASSWORD}@localhost/postgres" -f create_db.sql
```

The KAIR repository is intended to support LLM reasoning that goes beyond RAG: rather than retrieving raw data segments, we can instead match questions / tasks against *enriched* knowledge: commentary, assessment, extraction, annotation, and interpretation *added* to the raw data.  We provide a very general model of *entities* and *tags* that have associated embeddings and types: any RAG-style search can match against *raw or enriched data* and reason about relationships back to sources, papers, paragraphs, etc.

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
3. `crawler.py`: Fetches the URLs from the frontier queue and pulls the PDF files to a local directory
4. `generate_doc_info.py`: Parses the PDFs in the local directory, chunks them for RAG, and generates a paper descriptor, author info (+ links), a summary.

5. *Not yet inimplemented*: `generate_source_info.py` should **enrich** the corpus with information about authors, organizations, etc. and use these as the basis of **trust**.  In turn, once computed this trust could be propagated as tags to all documents.
6. *Not yet implemented*: `generate_detection_info.py` would be used to add tag-value pairs to items (paragraphs, papers, etc.) with particular *detections* of interest.
7. *Not yet implemented*: there is some scaffolding to extract *tables* from documents and to annotate/enrich them, via `generate_table_info.py`.

A set of helper functions is provided in `graph_db.py` for reading / writing authors, papers, paragraphs, etc.  In the database, several views exist to look at all tags relevant to paragraphs, authors and paragraphs, etc.

## Pre-Crawled / Indexed Data

You can supply a list of pre-crawled files under `PDF_PATH/dataset_papers`, and they will be added to the crawled list by `crawler.py`.  If a `.pdf.json` file with Aryn parsed data exists in `PDF_PATH/chunked_files` this will be used in lieu of the LangChain splitter.