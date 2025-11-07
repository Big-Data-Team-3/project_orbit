#!/bin/bash
# Script to clean up Cloud Composer environment

set -e

PROJECT_ID="project-orbit123"
ENV_NAME="project-orbit-composer"
LOCATION="us-central1"

echo "=========================================="
echo "Cleaning Up Cloud Composer"
echo "=========================================="
echo "Project: $PROJECT_ID"
echo "Environment: $ENV_NAME"
echo "Location: $LOCATION"
echo ""

# Check if Composer environment exists
echo "Checking if Composer environment exists..."
STATE=$(gcloud composer environments describe $ENV_NAME \
    --location=$LOCATION \
    --project=$PROJECT_ID \
    --format="get(state)" 2>/dev/null || echo "NOT_FOUND")

if [ "$STATE" = "NOT_FOUND" ]; then
    echo "✅ Composer environment not found (already deleted or never existed)"
else
    echo "Found Composer environment in state: $STATE"
    echo ""
    read -p "Delete Composer environment '$ENV_NAME'? This cannot be undone! (y/n): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo ""
        echo "Deleting Composer environment..."
        echo "This will take 5-10 minutes..."
        
        gcloud composer environments delete $ENV_NAME \
            --location=$LOCATION \
            --project=$PROJECT_ID \
            --quiet
        
        if [ $? -eq 0 ]; then
            echo "✅ Composer environment deleted successfully"
        else
            echo "❌ Failed to delete Composer environment"
            echo "You may need to delete it manually from GCP Console"
            exit 1
        fi
    else
        echo "Skipping deletion. You can delete it later manually."
    fi
fi

# Clean up config files
echo ""
echo "Cleaning up config files..."
if [ -f .composer_config ]; then
    rm .composer_config
    echo "✅ Removed .composer_config"
fi

# Keep .gcs_config (we still need the bucket info)
if [ -f .gcs_config ]; then
    echo "ℹ️  Keeping .gcs_config (needed for Cloud Functions)"
fi

echo ""
echo "=========================================="
echo "Cleanup Complete!"
echo "=========================================="
echo ""
echo "Next Steps:"
echo "1. Run: bash scripts/enable_apis.sh"
echo "2. Run: bash scripts/setup_functions.sh"
echo "=========================================="

