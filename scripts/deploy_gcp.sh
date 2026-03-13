#!/usr/bin/env bash
# Deploy backend-lite and frontend to Google Cloud Run.
# Usage: ./scripts/deploy_gcp.sh <PROJECT_ID> <BUCKET_NAME> [REGION]
#   e.g. ./scripts/deploy_gcp.sh my-gcp-project my-stock-data asia-east1

set -euo pipefail

PROJECT_ID="${1:?Usage: $0 <PROJECT_ID> <BUCKET_NAME> [REGION]}"
BUCKET="${2:?Usage: $0 <PROJECT_ID> <BUCKET_NAME> [REGION]}"
REGION="${3:-asia-east1}"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Project : ${PROJECT_ID}"
echo "Bucket  : ${BUCKET}"
echo "Region  : ${REGION}"
echo ""

# ── 1. Create GCS bucket (skip if exists) ──────────────────────────────────
echo "=== [1/5] Ensure GCS bucket exists ==="
gsutil ls "gs://${BUCKET}" 2>/dev/null || \
  gsutil mb -p "${PROJECT_ID}" -l "${REGION}" "gs://${BUCKET}"

# ── 2. Upload data files ────────────────────────────────────────────────────
echo ""
echo "=== [2/5] Upload data files to GCS ==="
"${PROJECT_ROOT}/scripts/upload_to_gcs.sh" "${BUCKET}"

# ── 3. Deploy backend-lite ──────────────────────────────────────────────────
echo ""
echo "=== [3/5] Deploy backend-lite to Cloud Run ==="
gcloud run deploy backend-lite \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --source "${PROJECT_ROOT}/backend_lite" \
  --execution-environment gen2 \
  --add-volume "name=data,type=cloud-storage,bucket=${BUCKET}" \
  --add-volume-mount "volume=data,mount-path=/mnt/data" \
  --set-env-vars "DATA_ROOT=/mnt/data" \
  --allow-unauthenticated \
  --port 8080 \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 3

BACKEND_URL=$(gcloud run services describe backend-lite \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --format "value(status.url)")
echo "backend-lite URL: ${BACKEND_URL}"

# ── 4. Deploy frontend ──────────────────────────────────────────────────────
echo ""
echo "=== [4/5] Deploy frontend to Cloud Run ==="
gcloud run deploy frontend \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --source "${PROJECT_ROOT}/frontend" \
  --set-env-vars "BACKEND_URL=${BACKEND_URL}" \
  --allow-unauthenticated \
  --port 8080 \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 3

FRONTEND_URL=$(gcloud run services describe frontend \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --format "value(status.url)")

# ── 5. Done ─────────────────────────────────────────────────────────────────
echo ""
echo "=== [5/5] Done ==="
echo ""
echo "Frontend : ${FRONTEND_URL}"
echo "Backend  : ${BACKEND_URL}"
echo ""
echo "Open ${FRONTEND_URL} in your browser."
