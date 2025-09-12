#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/local-deploy-server.sh <PROJECT_ID> <REGION> [SERVICE_NAME]

PROJECT_ID=${1:?"PROJECT_ID required"}
REGION=${2:?"REGION required"}
SERVICE=${3:-kair-server}
IMAGE_PATH="${REGION}-docker.pkg.dev/${PROJECT_ID}/api/${SERVICE}:local-$(git rev-parse --short HEAD)"

docker build --platform=linux/amd64 -t "$IMAGE_PATH" -f server/Dockerfile.server .

gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet
docker push "$IMAGE_PATH"

gcloud run deploy "$SERVICE" \
  --image "$IMAGE_PATH" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --service-account ${SERVICE_ACCOUNT_EMAIL:-kair-runner@air-foundry-seas-8645.iam.gserviceaccount.com} \
  --set-env-vars PYTHONUNBUFFERED=1,SKIP_ENRICHMENT=${SKIP_ENRICHMENT:-1},DB_NAME=${DB_NAME:-postgres},DB_USER=${DB_USER:-kair},DB_PORT=${DB_PORT:-5432},DB_HOST=${DB_HOST:-},CLOUD_SQL_CONNECTION_NAME=${CLOUD_SQL_CONNECTION_NAME:-} \
  ${DB_PASSWORD_SECRET_VERSION:+--set-secrets DB_PASSWORD=${DB_PASSWORD_SECRET_VERSION}} \
  --set-secrets OPENAI_API_KEY=OPENAI_API_KEY:1

