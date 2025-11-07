#!/bin/bash
# Script to create Cloud Scheduler job for scrape-and-index function

set -e

PROJECT_ID="project-orbit123"
REGION="us-central1"

echo "=========================================="
echo "Creating Cloud Scheduler Job for Scrape-and-Index"
echo "=========================================="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Load function URLs
if [ ! -f .functions_config ]; then
    echo "❌ ERROR: .functions_config not found!"
    echo "Run: bash scripts/deploy_functions.sh first"
    exit 1
fi

source .functions_config

if [ -z "$SCRAPE_AND_INDEX_URL" ]; then
    echo "❌ ERROR: SCRAPE_AND_INDEX_URL not found in config"
    echo "Run: bash scripts/deploy_functions.sh first"
    exit 1
fi

# Create Scrape-and-Index Scheduler Job (Weekly - Sunday 4 AM UTC)
echo "Creating scrape-and-index scheduler job..."
echo "Schedule: Weekly (Sunday 4 AM UTC) - 0 4 * * 0"
echo "This will scrape all companies and index them in Pinecone"

gcloud scheduler jobs create http scrape-and-index-job \
    --location=$REGION \
    --schedule="0 4 * * 0" \
    --uri="$SCRAPE_AND_INDEX_URL" \
    --http-method=POST \
    --time-zone="UTC" \
    --description="Scrape Forbes AI 50 companies and index in Pinecone (weekly full refresh)" \
    --project=$PROJECT_ID \
    --attempt-deadline=600s 2>/dev/null || \
    gcloud scheduler jobs update http scrape-and-index-job \
        --location=$REGION \
        --schedule="0 4 * * 0" \
        --uri="$SCRAPE_AND_INDEX_URL" \
        --http-method=POST \
        --time-zone="UTC" \
        --description="Scrape Forbes AI 50 companies and index in Pinecone (weekly full refresh)" \
        --project=$PROJECT_ID \
        --attempt-deadline=600s

if [ $? -eq 0 ]; then
    echo "✅ Scrape-and-index scheduler job created/updated"
else
    echo "⚠️  Warning: Failed to create scrape-and-index scheduler job"
fi

echo ""
echo "=========================================="
echo "Scheduler Job Created!"
echo "=========================================="
echo ""
echo "To manually trigger scrape-and-index:"
echo "  gcloud scheduler jobs run scrape-and-index-job --location=$REGION --project=$PROJECT_ID"
echo ""
echo "Or use the function URL directly:"
echo "  curl -X POST $SCRAPE_AND_INDEX_URL"
echo ""
echo "Note: This function will:"
echo "  1. Scrape all companies from seed file"
echo "  2. Upload HTML + TXT files to GCS"
echo "  3. Download TXT files from GCS"
echo "  4. Chunk text files"
echo "  5. Create embeddings using OpenAI"
echo "  6. Store embeddings in Pinecone"
echo ""
echo "Execution time: ~30-60 minutes for all 50 companies"
echo "=========================================="

