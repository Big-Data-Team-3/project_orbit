#!/bin/bash
# Script to deploy Cloud Functions

set -e

PROJECT_ID="project-orbit123"
REGION="us-central1"
BUCKET_NAME="project-orbit-data-12345"

# Get script and project directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load .env file if it exists
if [ -f "$PROJECT_ROOT/.env" ]; then
    echo "Loading environment variables from .env file..."
    # Export variables from .env file (handles KEY=VALUE format)
    # set -a makes all variables automatically exported
    set -a
    # Source .env file, ignoring errors from comments or empty lines
    source "$PROJECT_ROOT/.env" 2>/dev/null || true
    set +a
    echo "✅ Loaded .env file"
fi

echo "=========================================="
echo "Deploying Cloud Functions"
echo "=========================================="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Project Root: $PROJECT_ROOT"
echo ""

# Check if bucket config exists
if [ -f "$PROJECT_ROOT/.gcs_config" ]; then
    source "$PROJECT_ROOT/.gcs_config"
    if [ ! -z "$BUCKET_NAME" ]; then
        echo "Using bucket from config: $BUCKET_NAME"
    fi
fi

# Change to cloud_functions directory for deployment
cd "$PROJECT_ROOT/cloud_functions"
CLOUD_FUNCTIONS_DIR="$PROJECT_ROOT/cloud_functions"

if [ ! -f "main.py" ]; then
    echo "❌ ERROR: main.py not found in cloud_functions directory"
    echo "   Current directory: $(pwd)"
    exit 1
fi

if [ ! -d "src" ]; then
    echo "⚠️  WARNING: src/ directory not found"
    echo "   Please run: cp -r ../src cloud_functions/src"
    read -p "Continue anyway? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Deploy Full-Load Function
echo "Deploying full_ingest function..."
gcloud functions deploy full_ingest \
    --gen2 \
    --runtime=python311 \
    --region=$REGION \
    --source="$CLOUD_FUNCTIONS_DIR" \
    --entry-point=main_full_ingest \
    --trigger-http \
    --allow-unauthenticated \
    --memory=512MB \
    --timeout=540s \
    --max-instances=10 \
    --set-env-vars="GCP_PROJECT=$PROJECT_ID,GCS_BUCKET_NAME=$BUCKET_NAME,REGION=$REGION" \
    --project=$PROJECT_ID

if [ $? -eq 0 ]; then
    echo "✅ Full-load function deployed"
else
    echo "❌ Failed to deploy full-load function"
    exit 1
fi

echo ""

# Deploy Daily Refresh Function
echo "Deploying daily_refresh function..."
gcloud functions deploy daily_refresh \
    --gen2 \
    --runtime=python311 \
    --region=$REGION \
    --source="$CLOUD_FUNCTIONS_DIR" \
    --entry-point=main_daily_refresh \
    --trigger-http \
    --allow-unauthenticated \
    --memory=512MB \
    --timeout=540s \
    --max-instances=10 \
    --set-env-vars="GCP_PROJECT=$PROJECT_ID,GCS_BUCKET_NAME=$BUCKET_NAME,REGION=$REGION" \
    --project=$PROJECT_ID

if [ $? -eq 0 ]; then
    echo "✅ Daily refresh function deployed"
else
    echo "❌ Failed to deploy daily refresh function"
    exit 1
fi

echo ""

# Deploy Scrape and Index Function
echo "Deploying scrape_and_index function..."
echo "⚠️  Note: This function requires OPENAI_API_KEY, PINECONE_API_KEY, and PINECONE_INDEX"

# Check for required environment variables (from .env or environment)
if [ -z "$OPENAI_API_KEY" ] || [ -z "$PINECONE_API_KEY" ] || [ -z "$PINECONE_INDEX" ]; then
    echo "❌ ERROR: Required environment variables not found!"
    echo ""
    echo "Missing variables:"
    [ -z "$OPENAI_API_KEY" ] && echo "  - OPENAI_API_KEY"
    [ -z "$PINECONE_API_KEY" ] && echo "  - PINECONE_API_KEY"
    [ -z "$PINECONE_INDEX" ] && echo "  - PINECONE_INDEX"
    echo ""
    echo "Please ensure these are set in:"
    echo "  1. .env file in project root, OR"
    echo "  2. Shell environment variables"
    echo ""
    echo "Expected .env format:"
    echo "  OPENAI_API_KEY=your-key"
    echo "  PINECONE_API_KEY=your-key"
    echo "  PINECONE_INDEX=your-index-name"
    exit 1
fi

echo "✅ Found required environment variables"
echo "  OPENAI_API_KEY: ${OPENAI_API_KEY:0:10}... (hidden)"
echo "  PINECONE_API_KEY: ${PINECONE_API_KEY:0:10}... (hidden)"
echo "  PINECONE_INDEX: $PINECONE_INDEX"
echo ""

# Build environment variables string
ENV_VARS="GCP_PROJECT=$PROJECT_ID,GCS_BUCKET_NAME=$BUCKET_NAME,REGION=$REGION"

if [ ! -z "$OPENAI_API_KEY" ]; then
    ENV_VARS="$ENV_VARS,OPENAI_API_KEY=$OPENAI_API_KEY"
fi

if [ ! -z "$PINECONE_API_KEY" ]; then
    ENV_VARS="$ENV_VARS,PINECONE_API_KEY=$PINECONE_API_KEY"
fi

if [ ! -z "$PINECONE_INDEX" ]; then
    ENV_VARS="$ENV_VARS,PINECONE_INDEX=$PINECONE_INDEX"
fi

if [ ! -z "$EMBEDDING_MODEL" ]; then
    ENV_VARS="$ENV_VARS,EMBEDDING_MODEL=$EMBEDDING_MODEL"
fi

gcloud functions deploy scrape_and_index \
    --gen2 \
    --runtime=python311 \
    --region=$REGION \
    --source="$CLOUD_FUNCTIONS_DIR" \
    --entry-point=main_scrape_and_index \
    --trigger-http \
    --allow-unauthenticated \
    --memory=1GB \
    --timeout=540s \
    --max-instances=10 \
    --set-env-vars="$ENV_VARS" \
    --project=$PROJECT_ID

if [ $? -eq 0 ]; then
    echo "✅ Scrape and index function deployed"
else
    echo "❌ Failed to deploy scrape and index function"
    exit 1
fi

echo ""

# Deploy Structured Extraction Function
echo "Deploying structured_extraction function..."
gcloud functions deploy structured_extraction \
    --gen2 \
    --runtime=python311 \
    --region=$REGION \
    --source="$CLOUD_FUNCTIONS_DIR" \
    --entry-point=main_structured_extraction \
    --trigger-http \
    --allow-unauthenticated \
    --memory=2GB \
    --timeout=540s \
    --max-instances=5 \
    --set-env-vars="$ENV_VARS,OPENAI_MODEL=${OPENAI_MODEL:-gpt-4o-mini},GCS_SEED_FILE_PATH=seed/forbes_ai50_seed.json" \
    --project=$PROJECT_ID

if [ $? -eq 0 ]; then
    echo "✅ Structured extraction function deployed"
else
    echo "❌ Failed to deploy structured extraction function"
    exit 1
fi

echo ""
echo "=========================================="
echo "Getting function URLs..."
echo "=========================================="

FULL_INGEST_URL=$(gcloud functions describe full_ingest \
    --gen2 \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="get(serviceConfig.uri)" 2>/dev/null || echo "")

DAILY_REFRESH_URL=$(gcloud functions describe daily_refresh \
    --gen2 \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="get(serviceConfig.uri)" 2>/dev/null || echo "")

SCRAPE_AND_INDEX_URL=$(gcloud functions describe scrape_and_index \
    --gen2 \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="get(serviceConfig.uri)" 2>/dev/null || echo "")

STRUCTURED_EXTRACTION_URL=$(gcloud functions describe structured_extraction \
    --gen2 \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="get(serviceConfig.uri)" 2>/dev/null || echo "")

echo "Full-Load Function URL: $FULL_INGEST_URL"
echo "Daily Refresh Function URL: $DAILY_REFRESH_URL"
echo "Scrape and Index Function URL: $SCRAPE_AND_INDEX_URL"
echo "Structured Extraction Function URL: $STRUCTURED_EXTRACTION_URL"
echo ""

# Return to project root
cd "$PROJECT_ROOT"

# Save function URLs
cat > "$PROJECT_ROOT/.functions_config" << EOF
# Cloud Functions Configuration
# Generated on $(date)

PROJECT_ID=$PROJECT_ID
REGION=$REGION
BUCKET_NAME=$BUCKET_NAME
FULL_INGEST_URL=$FULL_INGEST_URL
DAILY_REFRESH_URL=$DAILY_REFRESH_URL
SCRAPE_AND_INDEX_URL=$SCRAPE_AND_INDEX_URL
STRUCTURED_EXTRACTION_URL=$STRUCTURED_EXTRACTION_URL
EOF

echo "✅ Configuration saved to $PROJECT_ROOT/.functions_config"
echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "Next Steps:"
echo "1. Test full-load function:"
echo "   curl -X POST $FULL_INGEST_URL"
echo ""
echo "2. Test scrape-and-index function:"
echo "   curl -X POST $SCRAPE_AND_INDEX_URL"
echo ""
echo "3. Test structured-extraction function:"
echo "   curl -X POST \"$STRUCTURED_EXTRACTION_URL?start=0&batch_size=1\""
echo ""
echo "4. Set up Cloud Scheduler:"
echo "   bash $SCRIPT_DIR/create_schedulers.sh"
echo "   bash $SCRIPT_DIR/create_scheduler_scrape_index.sh"
echo "=========================================="

