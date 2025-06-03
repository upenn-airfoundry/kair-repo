# KAIR Tornado Server

This is the Tornado-based server implementation for the KAIR project.

## Setup

1. Create a virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip3 install uv
uv pip install -r requirements.txt
```

2. Create a `.env` file with necessary environment variables (copy from `sample.env` in the root directory):
```bash
BACKEND_PORT=8081
```

## Running the Server

To start the server:
```bash
python3 app/server.py
```

The server will start on port 8081 by default (or the port specified in your .env file).

## Available Endpoints

### Health Check
- `GET /health` - Health check endpoint

### Entity Search
- `GET /find_related_entities_by_tag` - Find entities by tag
  - Query parameters:
    - `tag_name` (required): Name of the tag
    - `query` (required): Search query
    - `k` (optional, default=10): Number of results

- `GET /find_related_entities` - Find related entities
  - Query parameters:
    - `query` (required): Search query
    - `k` (optional, default=10): Number of results
    - `entity_type` (optional): Filter by entity type
    - `keywords` (optional): Comma-separated keywords

### Crawling and Indexing
- `POST /add_to_crawl_queue` - Add URL to crawl queue
  - Body: `{"url": "https://example.com", "comment": "Optional comment"}`

- `POST /crawl_files` - Start crawling files from queue

- `POST /parse_pdfs_and_index` - Parse PDFs and index them

- `GET /uncrawled_entries` - Get list of uncrawled entries

### Assessment Criteria
- `GET /get_assessment_criteria` - Get assessment criteria
  - Query parameters:
    - `name` (optional): Filter by criterion name

- `POST /add_assessment_criterion` - Add new assessment criterion
  - Body: `{"name": "criterion_name", "scope": "scope", "prompt": "prompt", "promise": 1.0}`

- `POST /add_enrichment` - Queue enrichment tasks

### Search and Expansion
- `POST /expand` - Expand search query
  - Body: `{"prompt": "your search query"}`

### Scheduler Control
- `POST /start_scheduler` - Start the scheduler
- `POST /stop_scheduler` - Stop the scheduler

## Testing with curl

Health check:
```bash
curl http://localhost:8081/health
```

Find related entities:
```bash
curl "http://localhost:8081/find_related_entities?query=your_query&k=10"
```

Add to crawl queue:
```bash
curl -X POST http://localhost:8081/add_to_crawl_queue \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "comment": "Test"}'
```

Get assessment criteria:
```bash
curl "http://localhost:8081/get_assessment_criteria?name=example"
```

Expand search:
```bash
curl -X POST http://localhost:8081/expand \
  -H "Content-Type: application/json" \
  -d '{"prompt": "your search query"}'
``` 