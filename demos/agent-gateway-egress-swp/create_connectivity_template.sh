#!/bin/bash
set -e

PROJECT_ID=$1
LOCATION=$2
TEMPLATE_NAME=$3
NETWORK_ATTACHMENT_URI=$4

if [ -z "$PROJECT_ID" ] || [ -z "$LOCATION" ] || [ -z "$TEMPLATE_NAME" ] || [ -z "$NETWORK_ATTACHMENT_URI" ]; then
  echo "Usage: ./create_connectivity_template.sh <PROJECT_ID> <LOCATION> <TEMPLATE_NAME> <NETWORK_ATTACHMENT_URI>"
  echo "Example: ./create_connectivity_template.sh my-project us-central1 my-template projects/my-project/regions/us-central1/networkAttachments/my-attachment"
  exit 1
fi

TOKEN=$(gcloud auth print-access-token)
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

echo "Creating AgentConnectivityTemplate ${TEMPLATE_NAME} in ${LOCATION}..."

curl -s -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "https://networkservices.googleapis.com/v1/projects/${PROJECT_NUMBER}/locations/${LOCATION}/agentConnectivityTemplates?agentConnectivityTemplateId=${TEMPLATE_NAME}" \
  -d "{
    \"accessPath\": \"AGENT_TO_ANYWHERE\",
    \"deploymentModel\": \"CENTRALIZED\",
    \"egressNetworkConfig\": {
      \"networkAttachment\": \"${NETWORK_ATTACHMENT_URI}\",
      \"vpcEgress\": \"ALL_TRAFFIC\"
    }
  }"

echo ""
echo "Note: The AgentGateway configuration in Terraform needs to reference this template's name."
