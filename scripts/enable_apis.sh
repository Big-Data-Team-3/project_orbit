#!/bin/bash
# Script to enable required GCP APIs for Cloud Functions

set -e

PROJECT_ID="project-orbit123"

echo "=========================================="
echo "Enabling Required GCP APIs"
echo "=========================================="
echo "Project: $PROJECT_ID"
echo ""

# Required APIs
APIS=(
    "cloudfunctions.googleapis.com"
    "cloudscheduler.googleapis.com"
    "cloudtasks.googleapis.com"
    "run.googleapis.com"
    "artifactregistry.googleapis.com"
)

echo "Enabling APIs..."
for API in "${APIS[@]}"; do
    echo -n "Enabling $API... "
    gcloud services enable "$API" --project="$PROJECT_ID" > /dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        echo "✅ Enabled"
    else
        # Check if already enabled
        STATUS=$(gcloud services list --enabled --project="$PROJECT_ID" --filter="name:$API" --format="get(name)" 2>/dev/null)
        if [ ! -z "$STATUS" ]; then
            echo "✅ Already enabled"
        else
            echo "⚠️  Failed (may need permissions)"
        fi
    fi
done

echo ""
echo "Verifying enabled APIs..."
ENABLED_COUNT=$(gcloud services list --enabled --project="$PROJECT_ID" --filter="name:cloudfunctions.googleapis.com OR name:cloudscheduler.googleapis.com OR name:cloudtasks.googleapis.com" --format="value(name)" | wc -l)

if [ "$ENABLED_COUNT" -ge 3 ]; then
    echo "✅ All required APIs are enabled"
else
    echo "⚠️  Some APIs may not be enabled. Check manually:"
    echo "   gcloud services list --enabled --project=$PROJECT_ID"
fi

echo ""
echo "=========================================="
echo "API Setup Complete!"
echo "=========================================="
echo ""
echo "Next Steps:"
echo "1. Run: bash scripts/setup_functions.sh"
echo "=========================================="

