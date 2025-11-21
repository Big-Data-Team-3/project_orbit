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

if [ -z "$LLM_MODEL" ]; then
    echo "⚠️  Warning: LLM_MODEL not set, using default: gpt-4o-mini"
    export LLM_MODEL="gpt-4o-mini"
fi

if [ -z "$OPENAI_MODEL" ]; then
    echo "⚠️  Warning: OPENAI_MODEL not set, using default: gpt-4o-mini"
    export OPENAI_MODEL="gpt-4o-mini"
fi

if [ -z "$GCS_BUCKET_NAME" ]; then
    echo "❌ Error: GCS_BUCKET_NAME is not set"
    exit 1
fi

# Set V2_MASTER_FOLDER for version2 bucket structure
if [ -z "$V2_MASTER_FOLDER" ]; then
    echo "⚠️  Warning: V2_MASTER_FOLDER not set, using default: version2"
    export V2_MASTER_FOLDER="version2"
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
# Create temporary cloudbuild config for main API
cat > /tmp/cloudbuild-api.yaml << EOF
steps:
- name: 'gcr.io/cloud-builders/docker'
  args: ['build', '-f', 'Dockerfile.api', '-t', 'gcr.io/$PROJECT_ID/project-orbit:latest', '.']
images:
- 'gcr.io/$PROJECT_ID/project-orbit:latest'
EOF
gcloud builds submit --config=/tmp/cloudbuild-api.yaml
rm /tmp/cloudbuild-api.yaml

echo "🚀 Building MCP Server image..."
# Create temporary cloudbuild config for MCP
cat > /tmp/cloudbuild-mcp.yaml << EOF
steps:
- name: 'gcr.io/cloud-builders/docker'
  args: ['build', '--no-cache', '-f', 'Dockerfile.mcp', '-t', 'gcr.io/$PROJECT_ID/project-orbit-mcp:latest', '.']
images:
- 'gcr.io/$PROJECT_ID/project-orbit-mcp:latest'
EOF
gcloud builds submit --config=/tmp/cloudbuild-mcp.yaml
rm /tmp/cloudbuild-mcp.yaml

echo "🚀 Building Agent Service image..."
# Create temporary cloudbuild config for Agent
cat > /tmp/cloudbuild-agent.yaml << EOF
steps:
- name: 'gcr.io/cloud-builders/docker'
  args: ['build', '-f', 'Dockerfile.agent', '-t', 'gcr.io/$PROJECT_ID/project-orbit-agent:latest', '.']
images:
- 'gcr.io/$PROJECT_ID/project-orbit-agent:latest'
EOF
gcloud builds submit --config=/tmp/cloudbuild-agent.yaml
rm /tmp/cloudbuild-agent.yaml

echo "🚀 Deploying MCP Server..."
gcloud run deploy project-orbit-mcp \
  --image gcr.io/$PROJECT_ID/project-orbit-mcp:latest \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --service-account=${SERVICE_ACCOUNT_EMAIL} \
  --port 8001 \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 5 \
  --set-env-vars="PYTHONPATH=/app/src:/app,OPENAI_API_KEY=$OPENAI_API_KEY,PINECONE_API_KEY=$PINECONE_API_KEY,PINECONE_INDEX=$PINECONE_INDEX,EMBEDDING_MODEL=$EMBEDDING_MODEL,EMBEDDING_DIMENSION=$EMBEDDING_DIMENSION,GCS_BUCKET_NAME=$GCS_BUCKET_NAME,PROJECT_ID=$PROJECT_ID,GCS_SEED_FILE_PATH=$GCS_SEED_FILE_PATH,V2_MASTER_FOLDER=$V2_MASTER_FOLDER"

echo "✅ MCP Server deployed!"
MCP_URL=$(gcloud run services describe project-orbit-mcp --region "$REGION" --format="value(status.url)")
echo "🌐 MCP Server URL: $MCP_URL"

echo "🚀 Deploying Agent Service..."
gcloud run deploy project-orbit-agent \
    --image gcr.io/$PROJECT_ID/project-orbit-agent:latest \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --service-account=${SERVICE_ACCOUNT_EMAIL} \
    --port 8002 \
    --memory 2Gi \
    --cpu 2 \
    --timeout 600 \
    --max-instances 5 \
    --set-env-vars="PYTHONPATH=/app/src:/app,OPENAI_API_KEY=$OPENAI_API_KEY,PINECONE_API_KEY=$PINECONE_API_KEY,PINECONE_INDEX=$PINECONE_INDEX,EMBEDDING_MODEL=$EMBEDDING_MODEL,EMBEDDING_DIMENSION=$EMBEDDING_DIMENSION,GCS_BUCKET_NAME=$GCS_BUCKET_NAME,PROJECT_ID=$PROJECT_ID,GCS_SEED_FILE_PATH=$GCS_SEED_FILE_PATH,LLM_MODEL=$LLM_MODEL,OPENAI_MODEL=$OPENAI_MODEL,MCP_BASE=$MCP_URL,V2_MASTER_FOLDER=$V2_MASTER_FOLDER"

echo "✅ Agent Service deployed!"
AGENT_URL=$(gcloud run services describe project-orbit-agent --region "$REGION" --format="value(status.url)")
echo "🌐 Agent Service URL: $AGENT_URL"

echo "🚀 Deploying API service..."
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
    --min-instances 0 \
    --max-instances 5 \
    --set-env-vars="PYTHONPATH=/app/src:/app,OPENAI_API_KEY=$OPENAI_API_KEY,PINECONE_API_KEY=$PINECONE_API_KEY,PINECONE_INDEX=$PINECONE_INDEX,EMBEDDING_MODEL=$EMBEDDING_MODEL,EMBEDDING_DIMENSION=$EMBEDDING_DIMENSION,GCS_BUCKET_NAME=$GCS_BUCKET_NAME,PROJECT_ID=$PROJECT_ID,GCS_SEED_FILE_PATH=$GCS_SEED_FILE_PATH,LLM_MODEL=$LLM_MODEL,OPENAI_MODEL=$OPENAI_MODEL,MCP_BASE=$MCP_URL,AGENT_BASE=$AGENT_URL,V2_MASTER_FOLDER=$V2_MASTER_FOLDER"

echo "✅ API service redeployed!"
API_URL=$(gcloud run services describe project-orbit-api --region "$REGION" --format="value(status.url)")
echo "🌐 API Service URL: $API_URL"

echo "🚀 Deploying Streamlit service..."
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
STREAMLIT_URL=$(gcloud run services describe project-orbit-streamlit --region "$REGION" --format="value(status.url)")
echo "🌐 Streamlit Service URL: $STREAMLIT_URL"

echo "🚀 Deploying HITL Dashboard..."
gcloud run deploy project-orbit-hitl \
  --image gcr.io/$PROJECT_ID/project-orbit:latest \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --service-account=${SERVICE_ACCOUNT_EMAIL} \
  --port 8502 \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 5 \
  --set-env-vars="PYTHONPATH=/app/src:/app,API_BASE=$API_URL" \
  --command streamlit \
  --args "run,src/hitl_dashboard.py,--server.port,8502,--server.address,0.0.0.0"

echo "✅ HITL Dashboard deployed!"
HITL_URL=$(gcloud run services describe project-orbit-hitl --region "$REGION" --format="value(status.url)")
echo "🌐 HITL Dashboard URL: $HITL_URL"

end_time=$(date +%s)
duration=$((end_time - start_time))
echo ""
echo "=========================================="
echo "🎉 All services deployed successfully!"
echo "=========================================="
echo "📊 Deployment Summary:"
echo "  • API Service:      $API_URL"
echo "  • Agent Service:     $AGENT_URL"
echo "  • Streamlit UI:      $STREAMLIT_URL"
echo "  • MCP Server:       $MCP_URL"
echo "  • HITL Dashboard:   $HITL_URL"
echo "🕒 Total deployment time: $((duration / 60))m $((duration % 60))s"