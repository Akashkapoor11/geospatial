#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "Uploading sample KML..."
RESPONSE=$(curl -sS -X POST "${BASE_URL}/api/files/" \
  -H "accept: application/json" \
  -F "file=@sample_data/demo.kml")

echo "${RESPONSE}"

FILE_ID=$(python -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<< "${RESPONSE}")

echo
echo "File status:"
curl -sS "${BASE_URL}/api/files/${FILE_ID}/" | python -m json.tool

echo
echo "Measurements:"
curl -sS "${BASE_URL}/api/files/${FILE_ID}/measurements/" | python -m json.tool
