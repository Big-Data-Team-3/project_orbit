#!/bin/bash
# Script to create Cloud Scheduler jobs

set -e

PROJECT_ID="project-orbit123"
REGION="us-central1"

echo "=========================================="
echo "Creating Cloud Scheduler Jobs"
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

if [ -z "$FULL_INGEST_URL" ] || [ -z "$DAILY_REFRESH_URL" ]; then
    echo "❌ ERROR: Function URLs not found in config"
    echo "Run: bash scripts/deploy_functions.sh first"
    exit 1
fi

# Create Full-Load Scheduler Job (manual trigger)
echo "Creating full-load scheduler job..."
gcloud scheduler jobs create http full-ingest-job \
    --location=$REGION \
    --schedule="0 0 * * 0" \
    --uri="$FULL_INGEST_URL" \
    --http-method=POST \
    --time-zone="UTC" \
    --description="Full-load scraping for Forbes AI 50 (can be triggered manually)" \
    --project=$PROJECT_ID \
    --attempt-deadline=600s 2>/dev/null || \
    gcloud scheduler jobs update http full-ingest-job \
        --location=$REGION \
        --schedule="0 0 * * 0" \
        --uri="$FULL_INGEST_URL" \
        --http-method=POST \
        --time-zone="UTC" \
        --description="Full-load scraping for Forbes AI 50 (can be triggered manually)" \
        --project=$PROJECT_ID \
        --attempt-deadline=600s

if [ $? -eq 0 ]; then
    echo "✅ Full-load scheduler job created/updated"
else
    echo "⚠️  Warning: Failed to create full-load scheduler job"
fi

echo ""

# Create Daily Refresh Scheduler Job (3 AM daily)
echo "Creating daily refresh scheduler job..."
gcloud scheduler jobs create http daily-refresh-job \
    --location=$REGION \
    --schedule="0 3 * * *" \
    --uri="$DAILY_REFRESH_URL" \
    --http-method=POST \
    --time-zone="UTC" \
    --description="Daily refresh of key pages for Forbes AI 50" \
    --project=$PROJECT_ID \
    --attempt-deadline=600s 2>/dev/null || \
    gcloud scheduler jobs update http daily-refresh-job \
        --location=$REGION \
        --schedule="0 3 * * *" \
        --uri="$DAILY_REFRESH_URL" \
        --http-method=POST \
        --time-zone="UTC" \
        --description="Daily refresh of key pages for Forbes AI 50" \
        --project=$PROJECT_ID \
        --attempt-deadline=600s

if [ $? -eq 0 ]; then
    echo "✅ Daily refresh scheduler job created/updated"
else
    echo "⚠️  Warning: Failed to create daily refresh scheduler job"
fi

echo ""
echo "=========================================="
echo "Scheduler Jobs Created!"
echo "=========================================="
echo ""
echo "To manually trigger full-load:"
echo "  gcloud scheduler jobs run full-ingest-job --location=$REGION --project=$PROJECT_ID"
echo ""
echo "To manually trigger daily refresh:"
echo "  gcloud scheduler jobs run daily-refresh-job --location=$REGION --project=$PROJECT_ID"
echo ""
echo "Or use the function URLs directly:"
echo "  curl -X POST $FULL_INGEST_URL"
echo "  curl -X POST $DAILY_REFRESH_URL"
echo "=========================================="

