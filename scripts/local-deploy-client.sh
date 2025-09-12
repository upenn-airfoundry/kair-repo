#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/local-deploy-client.sh <PROJECT_ID> <REGION> [SERVICE_NAME]

PROJECT_ID=${1:?"PROJECT_ID required"}
REGION=${2:?"REGION required"}
SERVICE=${3:-kair-client}
IMAGE_PATH="${REGION}-docker.pkg.dev/${PROJECT_ID}/web/${SERVICE}:local-$(git rev-parse --short HEAD)"

pushd kair-client >/dev/null
docker build --platform=linux/amd64 \
  --build-arg NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL:-} \
  -t "$IMAGE_PATH" -f Dockerfile.frontend .
popd >/dev/null

gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet
docker push "$IMAGE_PATH"

gcloud run deploy "$SERVICE" \
  --image "$IMAGE_PATH" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --set-env-vars NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL:-}

