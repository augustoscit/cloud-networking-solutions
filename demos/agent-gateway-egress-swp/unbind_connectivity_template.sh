#!/bin/bash
set -e

PROJECT_ID=$1
LOCATION=$2
AGENT_GATEWAY_NAME=$3

if [ -z "$PROJECT_ID" ] || [ -z "$LOCATION" ] || [ -z "$AGENT_GATEWAY_NAME" ]; then
  echo "Usage: ./unbind_connectivity_template.sh <PROJECT_ID> <LOCATION> <AGENT_GATEWAY_NAME>"
  exit 1
fi

TOKEN=$(gcloud auth print-access-token)
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

echo "Unbinding AgentConnectivityTemplate from AgentGateway ${AGENT_GATEWAY_NAME}..."

ETAG=$(curl -s -H "Authorization: Bearer ${TOKEN}" "https://networkservices.googleapis.com/v1/projects/${PROJECT_NUMBER}/locations/${LOCATION}/agentGateways/${AGENT_GATEWAY_NAME}" | jq -r .etag)

curl -s -X PATCH \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "https://networkservices.googleapis.com/v1/projects/${PROJECT_NUMBER}/locations/${LOCATION}/agentGateways/${AGENT_GATEWAY_NAME}?updateMask=agentConnectivityTemplate" \
  -d "{
    \"agentConnectivityTemplate\": null,
    \"etag\": \"${ETAG}\"
  }"

echo ""
echo "Done unbinding."
