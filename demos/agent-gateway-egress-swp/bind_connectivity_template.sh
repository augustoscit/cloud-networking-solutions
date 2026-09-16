#!/bin/bash
set -e

PROJECT_ID=$1
LOCATION=$2
AGENT_GATEWAY_NAME=$3
TEMPLATE_NAME=$4

if [ -z "$PROJECT_ID" ] || [ -z "$LOCATION" ] || [ -z "$AGENT_GATEWAY_NAME" ] || [ -z "$TEMPLATE_NAME" ]; then
  echo "Usage: ./bind_connectivity_template.sh <PROJECT_ID> <LOCATION> <AGENT_GATEWAY_NAME> <TEMPLATE_NAME>"
  exit 1
fi

TOKEN=$(gcloud auth print-access-token)
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

echo "Clearing networkConfig from AgentGateway ${AGENT_GATEWAY_NAME} before binding template..."
ETAG=$(curl -s -H "Authorization: Bearer ${TOKEN}" "https://networkservices.googleapis.com/v1/projects/${PROJECT_NUMBER}/locations/${LOCATION}/agentGateways/${AGENT_GATEWAY_NAME}" | jq -r .etag)

curl -s -X PATCH \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "https://networkservices.googleapis.com/v1/projects/${PROJECT_NUMBER}/locations/${LOCATION}/agentGateways/${AGENT_GATEWAY_NAME}?updateMask=networkConfig" \
  -d "{
    \"networkConfig\": null,
    \"etag\": \"${ETAG}\"
  }" > /dev/null

echo "Binding AgentConnectivityTemplate ${TEMPLATE_NAME} to AgentGateway ${AGENT_GATEWAY_NAME}..."
ETAG=$(curl -s -H "Authorization: Bearer ${TOKEN}" "https://networkservices.googleapis.com/v1/projects/${PROJECT_NUMBER}/locations/${LOCATION}/agentGateways/${AGENT_GATEWAY_NAME}" | jq -r .etag)

curl -s -X PATCH \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "https://networkservices.googleapis.com/v1/projects/${PROJECT_NUMBER}/locations/${LOCATION}/agentGateways/${AGENT_GATEWAY_NAME}?updateMask=agentConnectivityTemplate" \
  -d "{
    \"agentConnectivityTemplate\": \"projects/${PROJECT_NUMBER}/locations/${LOCATION}/agentConnectivityTemplates/${TEMPLATE_NAME}\",
    \"etag\": \"${ETAG}\"
  }"

echo "Done."
