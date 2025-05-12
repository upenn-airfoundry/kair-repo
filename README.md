# KAIR-Repo

![AIRFoundry logo](https://airfoundry.upenn.edu/wp-content/themes/penn-airfoundry/img/airfoundry.svg)

These are the building blocks for the [KAIR project](https://airfoundry.seas.upenn.edu) for the AIRFoundry.  Our key objective is to support *discovery queries* for science, driven by but not limited to RNA and LNP technologies.


## Database

You will need to update `.env` (copy from `sample.env`) to match your configuration.

We expect a PostgreSQL / TimescaleDB engine accessible via port 5432, with pgvectorscale.  With Docker installed, you can run `source timescaledb.sh` to install the Docker container.  Then the SQL in [create_db.sql](create_db.sql) generates a sample user and creates basic relations.  Some options:

Linux:
```bash
sudo apt install postgresql
psql -d "postgres://postgres:${DB_PASSWORD}@localhost/postgres" -f create_db.sql
```

Mac:
```bash
brew install postgresql
psql -d "postgres://postgres:${DB_PASSWORD}@localhost/postgres" -f create_db.sql
```

The KAIR repository is intended to support LLM reasoning that goes beyond RAG: rather than retrieving raw data segments, we can instead match questions / tasks against *enriched* knowledge: commentary, assessment, extraction, annotation, and interpretation *added* to the raw data.  We provide a very general model of *entities* and *tags* that have associated embeddings and types: any RAG-style search can match against *raw or enriched data* and reason about relationships back to sources, papers, paragraphs, etc.

## Getting Started

Install as per above. (You may wish to use VSCode and the VSCode MySQL extension [which also supports PostgreSQL] to connect directly to the DB instance.)

### Backend

From a terminal, run the following to build the Python / Flask backend:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip3 install uv
uv pip install -r requirements.txt 
```

This should install dependencies.  Make sure your `.env` is updated with an OpenAI API key for access to the GPT APIs.  Now:

```bash
python3 server.py
```

### React Frontend

From another Terminal, set up the Node.js infrastructure.

Linux:

```bash
sudo apt install nodejs
sudo npm install -g npm@latest
npm install
npm run dev
```

Mac:
```bash
brew install nodejs
npm install
npm run dev
```

Now navigate your browser to `localhost:5173`.

### Functionality

The console includes a variety of different capabilities on one screen.

**Crawling.**
At the bottom, you can find **Crawler / Indexer Controls**, which control the *crawl queue* for KAIR.  You can add URLs to the Crawl Queue.  Then hit "Start Crawling" to fetch documents.  You need to separately select "Parse and Index" to parse the resulting PDFs and index them in our repository.

**Low-Level Retrieval.** If you want to see what matches there are between a query and various *entities* or *tag values* (linked to entities), you can leverage the low-level retrieval functions.  

- "Retrieve Related Entities by Tag" does an embedding top-k match with the Query, among all entities with the specified tag.
- "Directly Retrieve Entities" does an embedding top-k match with the Query, among all entities. You can restrict the Entity Type (paragraph, author, paper, etc.) and also restrict the results to require matches to specified Keywords. (Keywords are stemmed.)

#### Assessment Criteria

The core concept behind the MUSE approach is to leverage *utility* and *semantic enrichment* to build out new entities and associations.  As a first step, we have implemented *item-centric* enrichment: an enrichment operator of the form 
$(item,prompt) \mapsto (name, value)$ 
where $item$ can be restricted to a particular *scope*.

The *value* is the result of applying the *prompt* (normally a question, e.g., "if this paper was published in a journal, what is the name of the journal; return 'none' if this paper was not published in a journal.")  The value will be paired with the name of the assessment criterion, as a $(name,value)$ tag.

Currently, running the "Enrich" operation will process, for each assessment criterion, up to 10 papers from the *scope* of each criterion.

#### Pose Your Question

The query answering component of KAIR will take a user question, and:

1. Expand the question --- asking, for each assessment criterion, for any criteria to look for, in the enriched tags.  For instance, should the question be focused on papers with academic authors, or that appeared in reputable journals, or from authors with may citations.

2. Match the question against paragraphs and the summary for various papers.  Create a joint ranking that also takes into account how the papers do against the various assessment criteria, above.

The overall ranking strategy is still under development.
 
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

Details for *data enrichment* can be found [here](enrichment.md).

## Command line

You will probably want to run the web modules as specified above. However, there are additional scriptable sub-modules that may be of interest.

1. `create_db.sql`: Creates the host database in PostgreSQL
2. `cli.py add_crawl_list`: Adds a number of URLs to the table representing the frontier queue for crawling
3. `cli.py crawl`: Fetches the URLs from the frontier queue and pulls the PDF files to a local directory
4. `generate_doc_info.py`: Parses the PDFs in the local directory, chunks them for RAG, and generates a paper descriptor, author info (+ links), a summary.

5. *Not yet inimplemented*: `generate_source_info.py` should **enrich** the corpus with information about authors, organizations, etc. and use these as the basis of **trust**.  In turn, once computed this trust could be propagated as tags to all documents.
6. `generate_detection_info.py` would be used to add tag-value pairs to items (paragraphs, papers, etc.) with particular *detections* of interest.
7. *Not yet implemented*: there is some scaffolding to extract *tables* from documents and to annotate/enrich them, via `generate_table_info.py`.

A set of helper functions is provided in `graph_db.py` for reading / writing authors, papers, paragraphs, etc.  In the database, several views exist to look at all tags relevant to paragraphs, authors and paragraphs, etc.

## Pre-Crawled / Indexed Data

You can supply a list of pre-crawled files under `PDF_PATH/dataset_papers`, and they will be added to the crawled list by `crawler.py`.  If a `.pdf.json` file with Aryn parsed data exists in `PDF_PATH/chunked_files` this will be used in lieu of the LangChain splitter.

## Submodules
You may need to initialize the submodules (see `.gitmodules`) by running the following commands:
```
git submodule init
git submodule update
```

### Parsing documents with `doc2json` & `grobid`
We use [`grobid`](https://grobid.readthedocs.io/en/latest/) to parse papers while maintaining high resolution contextual information with AllenAI's [`doc2json`](https://github.com/allenai/s2orc-doc2json), which converts it to a JSON file for our indexer. 

You can run the following command from root to try it out
```bash
python3 process_pdf.py -i <INPUT_PDF_PATH> -o <OUTPUT_PATH>
```


# Credits

This project is funded by the National Science Foundation under DBI-2400135.

![NSF logo](https://airfoundry.upenn.edu/wp-content/themes/penn-airfoundry/img/logo-NSF.png)

