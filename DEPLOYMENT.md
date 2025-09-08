# Kair Deployment Guide (GCP / Cloud Run)

This document describes the production deployment of the Next.js client (`kair-client`) and the Tornado server (`kair-server`) to Google Cloud Run, the architecture, the exact steps performed (in chronological order), issues encountered and fixes applied, environment/secret management, and useful commands.

## Architecture

- **Services**
  - `kair-server` (Tornado, Python): Deployed to Cloud Run. Exposes health and API endpoints (e.g., `/health`, `/api/login`, `/api/create`, `/api/chat`).
  - `kair-client` (Next.js, Node): Deployed to Cloud Run. Reads its server base URL from `NEXT_PUBLIC_API_BASE_URL`.
- **Container Registry**
  - Artifact Registry (region: `us-central1`)
    - Docker repos: `api` (server), `web` (client)
- **Identity & Access**
  - Runtime service account: `kair-runner@air-foundry-seas-8645.iam.gserviceaccount.com` (Cloud Run services run as this SA)
  - Permissions granted: Run Invoker/Admin (via deploy), Artifact Registry read, logging write; GitHub WIF not reconfigured in this pass.
- **Secrets**
  - Secret Manager (region: `us-central1` due to org policy)
    - `DB_PASSWORD` (version 1)
- **Networking**
  - Public HTTPS endpoints via Cloud Run-managed domain (`run.app`).
  - Server logs show successful bind on `0.0.0.0:${PORT}`.
  - Database access currently via direct TCP (public IP), not via Cloud SQL connector (recommended for hardening).
- **Config**
  - Client → Server URL: `NEXT_PUBLIC_API_BASE_URL` (e.g., `https://kair-server-341415787605.us-central1.run.app`).
  - Server DB config: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` (secret), `PYTHONUNBUFFERED=1`.

## Repositories & Paths

- Client app: `kair-client/`
  - Dockerfile: `kair-client/Dockerfile.frontend`
  - Local deploy script: `scripts/local-deploy-client.sh`
  - Workflows: `.github/workflows/deploy-client.yml`
- Server app: `server/app/server.py`, Dockerfile: `server/Dockerfile.server`
  - Local deploy script: `scripts/local-deploy-server.sh`
  - Workflows: `.github/workflows/deploy-server.yml`
- Shared modules updated to enable Cloud Run startup: `graph_db.py`, `search.py`, `enrichment/llms.py`, `enrichment/langchain_ops.py`, `enrichment/core_ops.py`

## Chronological Steps & Fixes

1) Target platform and registries
- Chosen target: Cloud Run for both client and server; Artifact Registry for images, Secret Manager for secrets.
- Created Artifact Registry repos `api` and `web` in `us-central1`.

2) Server container build and run adjustments
- `server/Dockerfile.server`:
  - `ENV PORT=8080` and `EXPOSE 8080` (Cloud Run expects `$PORT`).
  - Fixed copy context to use repo root paths. Example snippet:
    ```Dockerfile
    COPY server/requirements.txt ./requirements.txt
    RUN pip install --no-cache-dir -r requirements.txt
    COPY server /app/server/
    COPY graph_db.py /app/
    COPY search.py /app/
    COPY enrichment /app/enrichment/
    COPY entities /app/entities/
    COPY crawl /app/crawl/
    ```
- `server/app/server.py`:
  - Bind to `0.0.0.0` and `PORT`:
    ```python
    port = int(os.getenv("PORT", os.getenv("BACKEND_PORT", 8080)))
    app.listen(port, address="0.0.0.0")
    ```
  - Added `SKIP_ENRICHMENT` feature flag to allow startup without LLM/`prompts` dependencies and DB.
  - Guarded enrichment imports (e.g., `iterative_enrichment`, `seed_lists`, `AssessmentOps`) and moved heavy imports behind flags.
  - Relaxed `BaseHandler.prepare` to allow all endpoints during `SKIP_ENRICHMENT` so `/health` and basic routes succeed.
  - Moved `crawl.web_fetch` import (depends on `prompts`) into `CrawlFilesHandler.post` to avoid import-time failures.
  - Added early startup prints for debugging (`Initializing Tornado app...`, `About to listen...`).

3) Client container build and run adjustments
- `kair-client/Dockerfile.frontend`:
  - Switch to `$PORT` 8080, and run `next start -p $PORT`.
  - Ensure `pnpm` exists in both builder and runner stages:
    ```Dockerfile
    FROM node:20-alpine AS builder
    RUN npm install -g pnpm
    ...
    FROM node:20-alpine AS runner
    RUN npm install -g pnpm
    ...
    CMD ["sh", "-c", "pnpm start -p ${PORT}"]
    ```
  - Added `.dockerignore` in `kair-client/` to avoid copying local `node_modules` and build artifacts.

4) IAM & deploy SA
- Created runtime SA: `kair-runner@air-foundry-seas-8645.iam.gserviceaccount.com`.
- Granted roles: Cloud Run deploy/run, Artifact Registry read, logs write, etc.
- Granted `iam.serviceAccountUser` to `jvarun@seas.upenn.edu` on the runtime SA to allow `gcloud run deploy`.

5) Build and deployment issues (server)
- OCI manifest error (multi-arch index): rebuilt with `--platform=linux/amd64` in local script.
- Container startup failures:
  - Missing `google.generativeai` / `langchain_google_genai` / `OPENAI_API_KEY` → added lazy imports and fallbacks in `enrichment/llms.py`.
  - `prompts` import failing in multiple modules → moved or guarded imports; lazy import in `CrawlFilesHandler`.
  - DB connect attempts during import (`search.py`, `core_ops.py`) → guarded initializations to avoid connect at import or added safe fallbacks.
  - Final resolution allowed server to print `About to listen on 0.0.0.0:8080` and respond to `/health`.

6) Build and deployment issues (client)
- `pnpm: not found` in runner → installed `pnpm` in runner stage.
- `COPY` collision with `node_modules` → added `.dockerignore`.
- Successful deploy with `NEXT_PUBLIC_API_BASE_URL` set to the server.

7) Secrets & DB envs
- Organization policy blocked global secrets; created region-scoped secret:
  - Created `DB_PASSWORD` in Secret Manager with `--replication-policy=user-managed --locations=us-central1`.
- Deployed server with env vars:
  - `DB_HOST=34.86.169.170`
  - `DB_PORT=5432`
  - `DB_NAME=postgres`
  - `DB_USER=kair`
  - `DB_PASSWORD` via Secret Manager: `--set-secrets DB_PASSWORD=DB_PASSWORD:1`
  - `PYTHONUNBUFFERED=1`
- Server logs confirm healthy startup and `/health` 200. Enrichment logs show guarded/disabled until `prompts` added and credentials provided.

8) Final service URLs
- Server: `https://kair-server-341415787605.us-central1.run.app`
- Client: `https://kair-client-341415787605.us-central1.run.app`

## Current Temporary Logic (to revisit)

- `SKIP_ENRICHMENT` flag: used to allow startup without enrichment LLMs and `prompts`. Enrichment routes are guarded and return 503 (or are simply not exercised) until dependencies are configured.
- Lazy imports and fallbacks in `enrichment/llms.py`, `graph_db.py`, `search.py` prevent startup failures when credentials or libraries are absent.
- DB connectivity is via direct TCP to `34.86.169.170`. For production, strongly consider the Cloud SQL connector and private networking.
- CORS is permissive (`*`) in `BaseHandler.set_default_headers`. Tighten to your domain in production.

## Environment Variables & Secrets

- Client:
  - `NEXT_PUBLIC_API_BASE_URL`: `https://kair-server-...run.app`
- Server:
  - `PORT`: set by Cloud Run to 8080 and passed through; we bind to it.
  - `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` (via Secret Manager)
  - `PYTHONUNBUFFERED=1`
  - `SKIP_ENRICHMENT` (optional flag; recommended to remove once all deps present)

## Scripts & Workflows

- Local deploy scripts
  - `scripts/local-deploy-server.sh`:
    ```bash
    ./scripts/local-deploy-server.sh <PROJECT_ID> <REGION> [SERVICE_NAME]
    # Builds, pushes to Artifact Registry, deploys to Cloud Run as kair-server
    ```
  - `scripts/local-deploy-client.sh`:
    ```bash
    NEXT_PUBLIC_API_BASE_URL=<server-url> ./scripts/local-deploy-client.sh <PROJECT_ID> <REGION> [SERVICE_NAME]
    # Builds, pushes, deploys kair-client
    ```
- GitHub Actions (CI/CD, WIF placeholders)
  - `.github/workflows/deploy-server.yml`
  - `.github/workflows/deploy-client.yml`
  - These build images, push to Artifact Registry, and deploy to Cloud Run using Workload Identity Federation (requires repo secrets: `GCP_PROJECT_ID`, `GCP_REGION`, `WORKLOAD_IDENTITY_PROVIDER`, `SERVICE_ACCOUNT_EMAIL`, `NEXT_PUBLIC_API_BASE_URL`).

## Useful Commands

- Configure project/region
  ```bash
  gcloud config set project air-foundry-seas-8645
  gcloud config set run/region us-central1
  ```

- Create Artifact Registry repos
  ```bash
  gcloud artifacts repositories create api --repository-format=docker --location=us-central1
  gcloud artifacts repositories create web --repository-format=docker --location=us-central1
  ```

- Deploy server (with secrets)
  ```bash
  gcloud run deploy kair-server \
    --image us-central1-docker.pkg.dev/air-foundry-seas-8645/api/kair-server:YOUR_TAG \
    --region us-central1 --platform managed --allow-unauthenticated --port 8080 \
    --service-account kair-runner@air-foundry-seas-8645.iam.gserviceaccount.com \
    --set-env-vars DB_HOST=34.86.169.170,DB_PORT=5432,DB_NAME=postgres,DB_USER=kair,PYTHONUNBUFFERED=1 \
    --set-secrets DB_PASSWORD=DB_PASSWORD:1
  ```

- Deploy client
  ```bash
  gcloud run deploy kair-client \
    --image us-central1-docker.pkg.dev/air-foundry-seas-8645/web/kair-client:YOUR_TAG \
    --region us-central1 --platform managed --allow-unauthenticated --port 8080 \
    --service-account kair-runner@air-foundry-seas-8645.iam.gserviceaccount.com \
    --set-env-vars NEXT_PUBLIC_API_BASE_URL=https://kair-server-341415787605.us-central1.run.app
  ```

- Describe services and URLs
  ```bash
  gcloud run services describe kair-server --region us-central1 --format='value(status.url)'
  gcloud run services describe kair-client --region us-central1 --format='value(status.url)'
  ```

- Tail logs
  ```bash
  gcloud run services logs read kair-server --region us-central1 --limit=200
  gcloud run services logs read kair-client --region us-central1 --limit=200
  ```

- Health check
  ```bash
  curl -sS https://kair-server-341415787605.us-central1.run.app/health
  ```

- Create Secret Manager secret (region-constrained)
  ```bash
  printf "%s" "<PASSWORD>" | gcloud secrets create DB_PASSWORD \
    --replication-policy=user-managed --locations=us-central1 --data-file=-
  ```

- Build and Deploy (last used)
```bash
# client
IMAGE=us-central1-docker.pkg.dev/air-foundry-seas-8645/web/kair-client:$(git rev-parse --short HEAD)
cd kair-client
docker build --platform=linux/amd64 \
  --build-arg NEXT_PUBLIC_API_BASE_URL=https://kair-server-341415787605.us-central1.run.app \
  -t "$IMAGE" -f Dockerfile.frontend .
cd ..
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet
docker push "$IMAGE"
gcloud run deploy kair-client \
  --image "$IMAGE" \
  --region us-central1 --platform managed --allow-unauthenticated --port 8080 \
  --set-env-vars NEXT_PUBLIC_API_BASE_URL=https://kair-server-341415787605.us-central1.run.app

# server
IMAGE=us-central1-docker.pkg.dev/air-foundry-seas-8645/api/kair-server:$(git rev-parse --short HEAD)
docker build --platform=linux/amd64 -t "$IMAGE" -f server/Dockerfile.server .
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet
docker push "$IMAGE"
gcloud run deploy kair-server \
  --image "$IMAGE" \
  --region us-central1 --platform managed --allow-unauthenticated --port 8080 \
  --service-account kair-runner@air-foundry-seas-8645.iam.gserviceaccount.com \
  --set-env-vars CLOUD_SQL_CONNECTION_NAME=air-foundry-seas-8645:us-east4:airfoundry-dev-1,DB_NAME=postgres,DB_USER=kair,PYTHONUNBUFFERED=1,SKIP_ENRICHMENT=1 \
  --set-secrets DB_PASSWORD=DB_PASSWORD:1  
```
## Production Hardening & Next Steps

- Attach Cloud SQL connector (if the DB is a Cloud SQL instance) and remove direct public IP access; configure VPC connector and authorized networks if applicable.
- Remove `SKIP_ENRICHMENT`; install missing `prompts` module and configure LLM credentials (e.g., `OPENAI_API_KEY` in Secret Manager).
- Tighten CORS from `*` to your client domain.
- Map custom domains to Cloud Run services and enable HTTPS.
- Lock down IAM further (principle of least privilege); finalize GitHub Actions WIF and secrets.

---

Deployed services are working:
- Client: `https://kair-client-341415787605.us-central1.run.app`
- Server: `https://kair-server-341415787605.us-central1.run.app` (health: `/health`)

This document reflects the exact changes and commands used to reach a healthy deployment. Updates should be tracked here as changes are made to networking, secrets, and enrichment enablement.
