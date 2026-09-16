#!/bin/bash
set -e

PROJECT=$1
LOCATION=$2
AGENT_GATEWAY_NAME=$3

if [ -z "$PROJECT" ] || [ -z "$LOCATION" ] || [ -z "$AGENT_GATEWAY_NAME" ]; then
  echo "Usage: ./patch_gateway.sh <PROJECT_ID> <LOCATION> <AGENT_GATEWAY_NAME>"
  exit 1
fi

PROJECT_NUMBER=`gcloud projects describe $PROJECT --format="value(projectNumber)"`
TOKEN=`gcloud auth print-access-token`

ETAG=$(curl -s -H "Authorization: Bearer ${TOKEN}" "https://networkservices.googleapis.com/v1/projects/${PROJECT_NUMBER}/locations/${LOCATION}/agentGateways/${AGENT_GATEWAY_NAME}" | jq -r .etag)

curl -s -X PATCH \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "https://networkservices.googleapis.com/v1/projects/${PROJECT_NUMBER}/locations/${LOCATION}/agentGateways/${AGENT_GATEWAY_NAME}?updateMask=networkConfig" \
  -d "{
    \"networkConfig\": null,
    \"etag\": \"${ETAG}\"
  }" | jq .

