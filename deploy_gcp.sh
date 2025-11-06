#!/bin/bash
set -e
start_time=$(date +%s)
if [ -f .env ]; then
    echo "📋 Loading environment variables from .env file..."
    # Export all variables from .env file
    # This handles comments and empty lines
    export $(grep -v '^#' .env | grep -v '^$' | xargs)
else
    echo "⚠️  Warning: .env file not found. Using environment variables from shell."
fi

# Validate required variables
if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ Error: OPENAI_API_KEY is not set"
    exit 1
fi

if [ -z "$PINECONE_API_KEY" ]; then
    echo "❌ Error: PINECONE_API_KEY is not set"
    exit 1
fi

if [ -z "$PINECONE_INDEX" ]; then
    echo "❌ Error: PINECONE_INDEX is not set"
    exit 1
fi

if [ -z "$EMBEDDING_MODEL" ]; then
    echo "❌ Error: EMBEDDING_MODEL is not set"
    exit 1
fi

if [ -z "$EMBEDDING_DIMENSION" ]; then
    echo "❌ Error: EMBEDDING_DIMENSION is not set"
    exit 1
fi

if [ -z "$GCS_BUCKET_NAME" ]; then
    echo "❌ Error: GCS_BUCKET_NAME is not set"
    exit 1
fi

# Service account details
SERVICE_ACCOUNT_NAME="project-orbit-sa"
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Verify or create service account
echo "🔍 Checking if service account ${SERVICE_ACCOUNT_NAME} exists..."
if gcloud iam service-accounts describe ${SERVICE_ACCOUNT_EMAIL} --project=${PROJECT_ID} &>/dev/null; then
    echo "✅ Service account ${SERVICE_ACCOUNT_NAME} already exists"
else
    echo "📝 Creating service account ${SERVICE_ACCOUNT_NAME}..."
    gcloud iam service-accounts create ${SERVICE_ACCOUNT_NAME} \
        --display-name="Project Orbit Service Account" \
        --description="Service account for Project Orbit Client Connection" \
        --project=${PROJECT_ID}
    echo "✅ Service account ${SERVICE_ACCOUNT_NAME} created"
fi

echo "🔨 Verifying and adding IAM policy binding for GCS..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/storage.objectViewer"

echo "🔨 Verifying and adding IAM policy binding for Cloud Run..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/run.invoker"

echo "🔨 Building Docker image with Cloud Build (avoids cross-platform issues)..."
gcloud builds submit --tag gcr.io/$PROJECT_ID/project-orbit:latest

echo "🚀 Redeploying API service..."
gcloud run deploy project-orbit-api \
    --image gcr.io/$PROJECT_ID/project-orbit:latest \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --service-account=${SERVICE_ACCOUNT_EMAIL} \
    --port 8000 \
    --memory 1Gi \
    --cpu 1 \
    --timeout 300 \
    --max-instances 5 \
    --set-env-vars="PYTHONPATH=/app/src:/app,OPENAI_API_KEY=$OPENAI_API_KEY,PINECONE_API_KEY=$PINECONE_API_KEY,PINECONE_INDEX=$PINECONE_INDEX,EMBEDDING_MODEL=$EMBEDDING_MODEL,EMBEDDING_DIMENSION=$EMBEDDING_DIMENSION,GCS_BUCKET_NAME=$GCS_BUCKET_NAME,PROJECT_ID=$PROJECT_ID,GCS_SEED_FILE_PATH=$GCS_SEED_FILE_PATH"

echo "✅ API service redeployed!"
echo "🌐 Service URL: $(gcloud run services describe project-orbit-api --region $REGION --format='value(status.url)')"
echo "🚀 Redeploying Streamlit service..."
gcloud run deploy project-orbit-streamlit \
    --image gcr.io/$PROJECT_ID/project-orbit:latest \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --service-account=${SERVICE_ACCOUNT_EMAIL} \
    --port 8501 \
    --memory 1Gi \
    --cpu 1 \
    --timeout 300 \
    --max-instances 5 \
    --set-env-vars="PYTHONPATH=/app/src:/app,API_BASE=$API_URL" \
    --command streamlit \
    --args "run,src/streamlit_app.py,--server.port,8501,--server.address,0.0.0.0"

echo "✅ Streamlit service redeployed!"
echo "🌐 Service URL: $(gcloud run services describe project-orbit-streamlit --region $REGION --format='value(status.url)')"
end_time=$(date +%s)
duration=$((end_time - start_time))
echo "🕒 Deployment completed in $((duration / 60))m $((duration % 60))s"