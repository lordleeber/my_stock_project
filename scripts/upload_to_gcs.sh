#!/usr/bin/env bash
# Upload model files and dataset_strategy.csv files to GCS bucket.
# Usage: ./scripts/upload_to_gcs.sh <BUCKET_NAME>
#   e.g. ./scripts/upload_to_gcs.sh my-stock-data

set -euo pipefail

BUCKET="${1:?Usage: $0 <BUCKET_NAME>}"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Uploading models_selection/ ==="
gsutil -m rsync -r -d \
  "${PROJECT_ROOT}/models_selection" \
  "gs://${BUCKET}/models_selection"

echo ""
echo "=== Uploading dataset_strategy.csv files ==="
# Only upload dataset_strategy.csv (not every CSV in strategies/output)
find "${PROJECT_ROOT}/strategies/output" -name "dataset_strategy.csv" | while read -r f; do
  rel="${f#${PROJECT_ROOT}/}"
  gsutil cp "$f" "gs://${BUCKET}/${rel}"
done

echo ""
echo "Done. Files uploaded to gs://${BUCKET}/"
