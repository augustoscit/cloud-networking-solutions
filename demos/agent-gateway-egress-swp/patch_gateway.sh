#!/bin/bash
PROJECT=ciandt-dev-6
LOCATION=us-central1
AGENT_GATEWAY_NAME=agent-gateway

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
