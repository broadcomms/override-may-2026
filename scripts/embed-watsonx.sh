#!/usr/bin/env bash
#
# Simple Reusable CLI script for texting watsonx.ai embeddings generation.
# chmod +x scripts/embed-watsonx.sh
# ./scripts/embed-watsonx.sh "Your text to embed" 
##


set -euo pipefail

source .env

MODEL="${WATSONX_EMBEDDING:-ibm/granite-embedding-278m-multilingual}"
TEXT="${1:-BroadComms builds AI-powered solutions for businesses.}"

TOKEN=$(curl -s -X POST \
  "https://iam.cloud.ibm.com/identity/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=urn:ibm:params:oauth:grant-type:apikey&apikey=${WATSONX_API_KEY}" \
  | jq -r '.access_token')

curl -s -X POST \
  "${WATSONX_URL}/ml/v1/text/embeddings?version=2023-05-29" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"model_id\": \"${MODEL}\",
    \"project_id\": \"${WATSONX_PROJECT_ID}\",
    \"inputs\": [\"${TEXT}\"]
  }" | jq
