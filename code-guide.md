# Coding Guide for KAIR Platform

The KAIR platform has several core components.

## Storage / Persistence

The **Graph DB Store** provides an API over a vector+graph database (currently TimescaleDB, could easily be standard PostgreSQL) with management of entities, associations, and entity_tags --- each with embeddings.

* An *entity* can be a person, a table, a document, etc.

* An *association* links entities.

* An *entity_tag*  is a named annotation on an entity, normally produced via *enrichment*.

The `backend.graph_db.py` file defines the `GraphAccessor` class, which provides a comprehensive interface for interacting with a PostgreSQL (TimescaleDB) database that stores a hybrid graph/relational representation of research entities, documents, and their relationships. Here’s a summary of its main components and functionality:

### Database Connection and Utilities

Initialization: Connects to the database using credentials from environment variables.

SQL Execution: Provides methods (exec_sql, execute, commit) for executing SQL queries and managing transactions.

### Entity and Document Management

Papers and Tables: Methods to add, update, and fetch papers and tables, including their summaries and tags.

Sources: Methods to add sources and link them to papers.

Authors: Methods to add authors (with optional email and organization), link authors to papers, and handle disambiguation.
Paragraphs: Methods to add, update, and tag paragraphs, and fetch paragraphs for a paper.

### Tagging and Annotation

Entity and Paragraph Tags: Methods to add, update, and fetch tags for entities and paragraphs.
Find by Tag: Methods to find paragraphs or entities by tag.

### Relationships and Linking

Entity Linking: Methods to link authors and sources to papers, and to link entities to documents.

Similarity Search: Methods to find related entities or paragraphs using vector embeddings (for semantic similarity).

### Embeddings

Embedding Generation: Uses OpenAI embeddings (via LangChain) to generate vector representations for content, which are used for similarity search and semantic matching.

### Crawl Queue Management

Crawl Queue: Methods to add URLs to the crawl queue, fetch the next URL, and remove processed URLs.

### Task Queue Management

Task Queue: Methods to add tasks, fetch the next task, and delete tasks from the queue.

### Assessment and Association Criteria

Assessment Criteria: Methods to add and fetch assessment criteria for evaluating entities.
Association Criteria: (If implemented) Similar methods for relationships between entities.

### Advanced Search and Retrieval
Semantic Search: Methods to find related entities, papers, or tags using vector similarity and optional keyword filtering.
Field-based Search: Methods to find papers by field or fetch untagged papers/entities.
DataFrame and Table Indexing
Indexing DataFrames: Methods to create new SQL tables from Pandas DataFrames and register them in the database.

### Error Handling and Logging
All methods include error handling, transaction rollback, and logging for robustness.

### In summary:
graph_db.py is the core database abstraction layer for the project, supporting entity/document storage, annotation, semantic search, crawling, and task management, all with robust error handling and extensibility for research data enrichment workflows.

### The Database

Here’s a summary of the tables and enumerated types defined in create_db.sql:

#### Enumerated Types

- entity_types

  An ENUM type for classifying entities.

  Values:
'synopsis', 'fact', 'new_concept', 'claim', 'author', 'organization', 'tag', 'paper', 'section', 'paragraph', 'table', 'hypothesis', 'source', 'method', 'event', 'result'

#### Tables

- crawl_queue

  Stores URLs to be crawled.

   Columns: id, create_time, url, comment

- crawled

   Tracks which items from crawl_queue have been crawled and their file paths.

   Columns: id, crawl_time, path

- strategies

   Stores enrichment or crawling strategies/prompts.

   Columns: strategy_id, strategy_name, strategy_prompt, strategy_promise, strategy_scope, sub_strategies, strategy_json, strategy_embed, description

- entities

   Core table for all entities (papers, authors, paragraphs, etc.), supporting hierarchical and semantic relationships.

   Columns:
entity_id, entity_type (entity_types), entity_name, entity_parent, entity_embed, entity_detail, entity_url, entity_contact, entity_json, supporting_evidence

- entity_link

   Stores relationships between entities (e.g., author-to-paper).

   Columns:
from_id, to_id, entity_strength, entity_support, bidirectional, link_type

- entity_tags

   Tags for entities (e.g., summaries, keywords).

   Columns:
entity_id, tag_name, tag_value, tag_json, tag_embed

- assessment_criteria

   Stores criteria for assessing entities.

   Columns:
criteria_id, criteria_name, criteria_prompt, criteria_promise, criteria_json, criteria_embed, criteria_scope, is_aggregate

- association_criteria

   Stores criteria for assessing associations/relationships between entities.

   Columns:
association_criteria_id, entity1_id, entity2_id, entity1_scope, entity2_scope, association_criteria_name, association_criteria_prompt, association_strength, association_support, is_aggregate

- task_queue

   Queue of enrichment or processing tasks.

   Columns:
task_id, task_name, task_prompt, task_scope, task_description, task_subtasks, task_json, task_embed

- indexed_documents

   Stores metadata about indexed documents (PDFs, etc.).

   Columns:
document_id, document_name, document_url, document_type, document_embed, document_json, entity_id

- indexed_tables

   Stores metadata about indexed tables (tabular data).

   Columns:
table_id, table_name, table_url, table_type, table_embed, table_json, entity_id

- indexed_figures

   Stores metadata about indexed figures (images, plots, etc.).

   Columns:
figure_id, figure_name, figure_url, figure_type, figure_embed, figure_json, entity_id

**Views** are also defined for convenient access to authors, papers, paragraphs, and their relationships, but the above are the main tables and types.

## Crawling and External Resources

The **Crawler** fetches external data resources, e.g., from the Web or Pennsieve.

* The `crawler_queue.py` module manages the crawl queue and crawled files for KAIR. Here’s a summary of its main functionality:

  - add_local_downloads_to_crawl_queue: Scans a local directory for PDF files and adds their file URLs to the crawl queue in the database, avoiding duplicates.

  - add_urls_to_crawl_queue: Adds a list of URLs to the crawl queue, checking for duplicates before insertion.

  - add_to_crawled: Marks a file as crawled by adding its path (and optionally its crawl queue ID) to the crawled table, avoiding duplicates.

  - get_urls_to_crawl: Retrieves all URLs from the crawl queue that have not yet been crawled, ordered by their ID. Optionally limits the number of results.

  - get_crawled_paths: Retrieves all file paths from the crawled table, along with their crawl queue IDs and original URLs.

  - get_crawled_paths_by_date: Retrieves all crawled file paths for a specific date.

Other key source modules include:

* `semscholar.py`: `fetch_author_from_semantic_scholar` queries the Semantic Scholar API for a given author by name. 

* `web-fetch.py`: the main method, `fetch_and_crawl_frontier`, pulls items from the crawler queue table and fetches them to the specified data directory.

## Parsing and Extraction

We incorporate several methods for extracting semantic information.

* We include the `dblp_parser` as a submodule, to parse DBLP jsonl files.

* We include the `grobid` submodule or optionally call to an external grobid server (`.env` `GROBID_SERVER` setting) to parse fetched PDF documents into GROBID XML.  We further leverage the `doc2json` submodule to parse the XML file into a JSON object suitable for indexing.

>[!NOTE]
The file `generate_people_info` fetches the homepages of all *people* in the entities table. It should be incorporated into the enrichment loop.

The main enrichment task in the current version of KAIR is in `generate_doc_info.py`.

This module handles the parsing, semantic extraction, and enrichment of PDF documents and tabular files (CSV, JSON, JSONL, MAT, XML) for research data workflows. It processes files listed in the crawl queue, parses their content (using LangChain, Aryn SDK, or custom logic), and indexes the extracted information (such as paragraphs or tables) into a database via the GraphAccessor. The module ensures that documents are not indexed multiple times and logs or handles errors during processing.

### API Calls / Main Functions:

- handle_file(path: str, url: str, use_aryn: bool = False):

  Determines the file type and parses it accordingly:

  - For PDFs: Uses either Aryn SDK or (optionally) LangChain to split and process the document.
  - For tabular files (CSV, JSON, JSONL, MAT, XML): Reads the file into a DataFrame and creates a table entity in the database.
  - For other files: Attempts to use a pre-split Aryn file and indexes paragraphs if available.
Commits changes to the database after processing.

- parse_files_and_index(use_aryn: bool = False):

  - Iterates over all files in the crawl queue (via get_crawled_paths()).

  - Checks if each document is already indexed (via GraphAccessor().exists_document(url)).

  - If not indexed, calls handle_file() to process and index the file.

  - Handles and logs any exceptions during processing.

### Key External/API Calls:

- get_crawled_paths(): Retrieves the list of files to process from the crawl queue.

- handle_file(path, url, use_aryn): Main entry point for processing a single file.

- split_pdf_with_langchain(pdf_path), chunk_and_partition_pdf_file(pdf_path),  get_presplit_aryn_file(pdf_path): Utilities for splitting/parsing PDFs.

- read_csv, read_json, read_jsonl, read_mat, read_xml: Functions for reading tabular data files.

- create_table_entity(path, df, graph_db): Indexes a DataFrame as a table entity in the database.

- index_split_paragraphs(split_docs, url, path, the_date): Indexes split paragraphs from a document.

## Enrichment of Items

This module orchestrates the enrichment of entities (such as papers) in the database using assessment criteria and strategies. It provides functions to select, queue, and process enrichment tasks, leveraging LangChain-based operations for semantic enrichment.

Main Functionality:

- add_strategy / get_current_best_strategy:
Placeholders for adding and selecting enrichment strategies (not implemented).

- enrich_entities:
For a given task (assessment criterion), retrieves the relevant criteria and entities, applies the enrichment operation (via AssessmentOps), and tags entities in the database with the results.

- entity_enrichment:
Runs enrichment for all criteria over a given set of entities.

- pairwise_enrichment:
Placeholder for enriching relationships between pairs of entities.

- iterative_enrichment:
Enqueues the most promising enrichment tasks for the next round by adding them to the task queue.

- process_next_task:
Fetches the next task from the task queue, processes it using enrich_entities, and removes it from the queue.

Key API Calls / Interactions:

- graph_accessor.get_assessment_criteria(task):
Retrieves assessment criteria from the database.

- graph_accessor.get_untagged_papers_by_field(scope, name, batch_size):
Gets a batch of untagged papers/entities for a given scope and criterion.

- graph_accessor.get_untagged_entities_as_json(entity_id, name):
Fetches untagged entities as JSON for enrichment.

AssessmentOps(prompt, name, max_tokens).

- enrich_data([data]):
Applies a LangChain-based enrichment operation to the data.

- graph_accessor.add_tag_to_entity(entity_id, name, value):
Tags an entity with the enrichment result.

- graph_accessor.add_task_to_queue(name, scope, prompt, description):
Adds an enrichment task to the task queue.

- graph_accessor.fetch_next_task():
Retrieves the next task from the task queue.

- graph_accessor.delete_task(task_id):
Removes a completed task from the task queue.

