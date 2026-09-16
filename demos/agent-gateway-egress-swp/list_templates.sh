#!/bin/bash
PROJECT=ciandt-dev-6
LOCATION=us-central1
PROJECT_NUMBER=`gcloud projects describe $PROJECT --format="value(projectNumber)"`
TOKEN=`gcloud auth print-access-token`

curl -s -H "Authorization: Bearer $TOKEN" "https://networkservices.googleapis.com/v1/projects/${PROJECT_NUMBER}/locations/${LOCATION}/agentConnectivityTemplates" | jq .
