#!/usr/bin/env bash
set -euo pipefail

BACKEND_URL="${BACKEND_URL:-}"
COMMUNITY_ID="${COMMUNITY_ID:-1}"
IMAGE_PATH="${IMAGE_PATH:-captures/latest.jpg}"
OUTPUT_JSON="${OUTPUT_JSON:-captures/latest-analysis.json}"
BENCHMARK_RUNS="${BENCHMARK_RUNS:-3}"

if [[ ! -f "$IMAGE_PATH" ]]; then
  python src/analyze_sample.py \
    --capture \
    --output "$IMAGE_PATH" \
    --community-id "$COMMUNITY_ID" \
    --save-json "$OUTPUT_JSON" \
    --benchmark-runs "$BENCHMARK_RUNS" \
    ${BACKEND_URL:+--backend-url "$BACKEND_URL"}
else
  python src/analyze_sample.py \
    --image "$IMAGE_PATH" \
    --community-id "$COMMUNITY_ID" \
    --save-json "$OUTPUT_JSON" \
    --benchmark-runs "$BENCHMARK_RUNS" \
    ${BACKEND_URL:+--backend-url "$BACKEND_URL"}
fi
