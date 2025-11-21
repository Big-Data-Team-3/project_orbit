# Project Orbit Deployment Strategy v2.0

## Overview

This document provides a comprehensive guide for deploying Project Orbit with the new multi-service Docker architecture. The project now consists of 6 independent services, each with its own Docker image:

1. **Streamlit Frontend** (port 8501)
2. **HITL Dashboard** (port 8502)
3. **FastAPI Backend** (port 8000)
4. **MCP Server** (port 8001)
5. **Agent Service** (port 8002)
6. **Airflow** (port 8080)

## Architecture

```
┌─────────────────┐
│  Streamlit UI   │ (8501)
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────┐
│   FastAPI API   │ (8000)
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────┐
│  Agent Service  │ (8002)
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────┐
│   MCP Server    │ (8001)
└─────────────────┘

┌─────────────────┐
│  HITL Dashboard │ (8502)
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────┐
│   FastAPI API   │ (8000)
└─────────────────┘

┌─────────────────┐
│     Airflow     │ (8080)
└─────────────────┘
```

## Prerequisites

### System Requirements
- Docker 20.10+
- Docker Compose 2.0+
- Python 3.11+ (for local development)
- Google Cloud SDK (`gcloud` CLI) - for GCP deployment
- Git

### GCP Prerequisites
- GCP Project with billing enabled
- Service account with appropriate permissions
- Container Registry API enabled
- Cloud Run API enabled

### Required Environment Variables

Create a `.env` file in the project root with the following variables:

```bash
# GCP Configuration
PROJECT_ID=your-gcp-project-id
REGION=us-central1
GCS_BUCKET_NAME=your-bucket-name
GCS_SEED_FILE_PATH=seed/forbes_ai50_seed.json

# OpenAI Configuration
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
OPENAI_MODEL=gpt-4o-mini

# Pinecone Configuration
PINECONE_API_KEY=your-pinecone-key
PINECONE_INDEX=your-index-name
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSION=1536

# MCP Server Configuration
MCP_API_KEY=your-mcp-api-key
MCP_BASE=http://localhost:8001  # For local, use Cloud Run URL for GCP

# Agent Service Configuration
AGENT_BASE=http://localhost:8002  # For local, use Cloud Run URL for GCP

# API Configuration
API_BASE=http://localhost:8000  # For local, use Cloud Run URL for GCP
```

## Local Deployment

### Option 1: Docker Compose (Recommended)

The easiest way to run all services locally:

```bash
# Start all services
docker-compose up --build

# Start in detached mode
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop all services
docker-compose down
```

**Service URLs:**
- FastAPI: http://localhost:8000/docs
- Streamlit: http://localhost:8501
- HITL Dashboard: http://localhost:8502
- MCP Server: http://localhost:8001/docs
- Agent Service: http://localhost:8002/docs

### Option 2: Individual Docker Builds

Build and run services individually:

```bash
# Build a specific service
docker build -f Dockerfile.streamlit -t project-orbit-streamlit:latest .
docker build -f Dockerfile.hitl -t project-orbit-hitl:latest .
docker build -f Dockerfile.api -t project-orbit-api:latest .
docker build -f Dockerfile.mcp -t project-orbit-mcp:latest .
docker build -f Dockerfile.agent -t project-orbit-agent:latest .

# Run a service
docker run -p 8501:8501 \
  -e API_BASE=http://host.docker.internal:8000 \
  project-orbit-streamlit:latest
```

### Option 3: Using Build Script

Use the provided build script for convenience:

```bash
# Build all images locally
./scripts/build_images.sh all

# Build a specific service
./scripts/build_images.sh streamlit
./scripts/build_images.sh api
./scripts/build_images.sh agent
./scripts/build_images.sh mcp
./scripts/build_images.sh hitl
./scripts/build_images.sh airflow
```

## GCP Cloud Deployment

### Step 1: Initial GCP Setup

```bash
# Set your project
export PROJECT_ID=your-project-id
gcloud config set project $PROJECT_ID

# Enable required APIs
gcloud services enable \
  run.googleapis.com \
  containerregistry.googleapis.com \
  cloudbuild.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com

# Create service account (if not exists)
SERVICE_ACCOUNT_NAME="project-orbit-sa"
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts create ${SERVICE_ACCOUNT_NAME} \
  --display-name="Project Orbit Service Account" \
  --description="Service account for Project Orbit services" \
  --project=${PROJECT_ID}

# Grant necessary permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --role="roles/storage.objectViewer"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --role="roles/run.invoker"
```

### Step 2: Build and Push Images

#### Option A: Using Build Script (Recommended)

```bash
# Build and push all images to GCR
./scripts/build_images.sh all --push

# Build and push with specific tag
./scripts/build_images.sh all --push --tag v1.0.0

# Build and push individual service
./scripts/build_images.sh api --push
```

#### Option B: Manual Build

```bash
# Build using Cloud Build (recommended for GCP)
gcloud builds submit --tag gcr.io/$PROJECT_ID/project-orbit-api:latest --file Dockerfile.api
gcloud builds submit --tag gcr.io/$PROJECT_ID/project-orbit-streamlit:latest --file Dockerfile.streamlit
gcloud builds submit --tag gcr.io/$PROJECT_ID/project-orbit-hitl:latest --file Dockerfile.hitl
gcloud builds submit --tag gcr.io/$PROJECT_ID/project-orbit-mcp:latest --file Dockerfile.mcp
gcloud builds submit --tag gcr.io/$PROJECT_ID/project-orbit-agent:latest --file Dockerfile.agent
```

### Step 3: Deploy Services to Cloud Run

#### Deploy MCP Server (Deploy First - Other services depend on it)

```bash
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
  --set-env-vars="MCP_API_KEY=${MCP_API_KEY},OPENAI_API_KEY=${OPENAI_API_KEY},PINECONE_API_KEY=${PINECONE_API_KEY},PINECONE_INDEX=${PINECONE_INDEX},EMBEDDING_MODEL=${EMBEDDING_MODEL},EMBEDDING_DIMENSION=${EMBEDDING_DIMENSION},GCS_BUCKET_NAME=${GCS_BUCKET_NAME},PROJECT_ID=${PROJECT_ID},GCS_SEED_FILE_PATH=${GCS_SEED_FILE_PATH},PYTHONPATH=/app/src:/app"

# Get MCP service URL
MCP_URL=$(gcloud run services describe project-orbit-mcp --region $REGION --format='value(status.url)')
echo "MCP Service URL: $MCP_URL"
```

#### Deploy Agent Service

```bash
gcloud run deploy project-orbit-agent \
  --image gcr.io/$PROJECT_ID/project-orbit-agent:latest \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --service-account=${SERVICE_ACCOUNT_EMAIL} \
  --port 8002 \
  --memory 2Gi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 5 \
  --set-env-vars="OPENAI_API_KEY=${OPENAI_API_KEY},MCP_BASE=${MCP_URL},MCP_API_KEY=${MCP_API_KEY},LLM_MODEL=${LLM_MODEL},PYTHONPATH=/app/src:/app"

# Get Agent service URL
AGENT_URL=$(gcloud run services describe project-orbit-agent --region $REGION --format='value(status.url)')
echo "Agent Service URL: $AGENT_URL"
```

#### Deploy FastAPI Backend

```bash
gcloud run deploy project-orbit-api \
  --image gcr.io/$PROJECT_ID/project-orbit-api:latest \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --service-account=${SERVICE_ACCOUNT_EMAIL} \
  --port 8000 \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --max-instances 10 \
  --set-env-vars="OPENAI_API_KEY=${OPENAI_API_KEY},PINECONE_API_KEY=${PINECONE_API_KEY},PINECONE_INDEX=${PINECONE_INDEX},EMBEDDING_MODEL=${EMBEDDING_MODEL},EMBEDDING_DIMENSION=${EMBEDDING_DIMENSION},GCS_BUCKET_NAME=${GCS_BUCKET_NAME},PROJECT_ID=${PROJECT_ID},GCS_SEED_FILE_PATH=${GCS_SEED_FILE_PATH},AGENT_BASE=${AGENT_URL},PYTHONPATH=/app/src:/app"

# Get API service URL
API_URL=$(gcloud run services describe project-orbit-api --region $REGION --format='value(status.url)')
echo "API Service URL: $API_URL"
```

#### Deploy Streamlit Frontend

```bash
gcloud run deploy project-orbit-streamlit \
  --image gcr.io/$PROJECT_ID/project-orbit-streamlit:latest \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --service-account=${SERVICE_ACCOUNT_EMAIL} \
  --port 8501 \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 5 \
  --set-env-vars="API_BASE=${API_URL},MCP_BASE=${MCP_URL},PYTHONPATH=/app/src:/app"
```

#### Deploy HITL Dashboard

```bash
gcloud run deploy project-orbit-hitl \
  --image gcr.io/$PROJECT_ID/project-orbit-hitl:latest \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --service-account=${SERVICE_ACCOUNT_EMAIL} \
  --port 8502 \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 5 \
  --set-env-vars="API_BASE=${API_URL},PYTHONPATH=/app/src:/app"
```

### Step 4: Deploy Airflow (Optional)

Airflow can be deployed to:
- **GKE (Google Kubernetes Engine)** - Recommended for production
- **Cloud Composer** - Managed Airflow service
- **Cloud Run** - Not recommended (Airflow requires persistent storage)

For GKE deployment, refer to Airflow's official GKE deployment documentation.

## Service Dependencies

The services have the following dependency order:

1. **MCP Server** - No dependencies (deploy first)
2. **Agent Service** - Depends on MCP Server
3. **FastAPI** - Depends on Agent Service
4. **Streamlit** - Depends on FastAPI and MCP Server
5. **HITL Dashboard** - Depends on FastAPI

## Environment Variables by Service

### MCP Server
- `MCP_API_KEY` (required)
- `OPENAI_API_KEY` (required)
- `PINECONE_API_KEY` (required)
- `PINECONE_INDEX` (required)
- `EMBEDDING_MODEL` (required)
- `EMBEDDING_DIMENSION` (required)
- `GCS_BUCKET_NAME` (optional, for GCS resources)
- `PROJECT_ID` (optional, for GCS access)
- `GCS_SEED_FILE_PATH` (optional)

### Agent Service
- `OPENAI_API_KEY` (required)
- `MCP_BASE` (required) - URL of MCP Server
- `MCP_API_KEY` (required)
- `LLM_MODEL` (optional, default: gpt-4o-mini)

### FastAPI
- `OPENAI_API_KEY` (required)
- `PINECONE_API_KEY` (required)
- `PINECONE_INDEX` (required)
- `EMBEDDING_MODEL` (required)
- `EMBEDDING_DIMENSION` (required)
- `GCS_BUCKET_NAME` (required)
- `PROJECT_ID` (required)
- `GCS_SEED_FILE_PATH` (optional)
- `AGENT_BASE` (required) - URL of Agent Service

### Streamlit
- `API_BASE` (required) - URL of FastAPI
- `MCP_BASE` (optional) - URL of MCP Server

### HITL Dashboard
- `API_BASE` (required) - URL of FastAPI

## Verification

After deployment, verify all services are running:

```bash
# Check Cloud Run services
gcloud run services list --region $REGION

# Check service health
curl https://your-api-url/health
curl https://your-mcp-url/health
curl https://your-agent-url/health

# View logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=project-orbit-api" --limit 50
```

## Troubleshooting

### Common Issues

#### 1. Service Cannot Connect to Another Service

**Problem**: Agent service cannot reach MCP server

**Solution**: 
- Verify `MCP_BASE` environment variable is set correctly
- Ensure MCP service is deployed and healthy
- Check Cloud Run service URLs are accessible

#### 2. Image Build Fails

**Problem**: Docker build fails with dependency errors

**Solution**:
- Verify `requirements.txt` is up to date
- Check Dockerfile paths are correct
- Ensure all source files are present

#### 3. Service Timeout

**Problem**: Agent service times out during execution

**Solution**:
- Increase Cloud Run timeout: `--timeout 540` (9 minutes)
- Increase memory allocation: `--memory 4Gi`
- Check agent service logs for errors

#### 4. Environment Variables Not Set

**Problem**: Service fails with missing environment variable errors

**Solution**:
- Verify `.env` file exists and is properly formatted
- Check environment variables are set in Cloud Run deployment
- Use `gcloud run services describe` to verify env vars

### Debugging Commands

```bash
# View service logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=SERVICE_NAME" --limit 100

# Check service configuration
gcloud run services describe SERVICE_NAME --region $REGION

# Test service locally
docker run -p 8000:8000 --env-file .env project-orbit-api:latest

# Check image in GCR
gcloud container images list --repository=gcr.io/$PROJECT_ID
```

## Automated Deployment Script

For convenience, you can create a deployment script that automates the entire process:

```bash
#!/bin/bash
# deploy_all.sh

set -e
source .env

# Build and push all images
./scripts/build_images.sh all --push

# Deploy services in order
# (MCP -> Agent -> API -> Streamlit -> HITL)

# Deploy MCP
# ... (deployment commands)

# Deploy Agent
# ... (deployment commands)

# Deploy API
# ... (deployment commands)

# Deploy Streamlit
# ... (deployment commands)

# Deploy HITL
# ... (deployment commands)

echo "✅ All services deployed!"
```

## Cost Optimization

### Cloud Run Pricing Tips

1. **Set appropriate instance limits**:
   - Use `--min-instances 0` for services that don't need to be always-on
   - Set `--max-instances` based on expected load

2. **Right-size memory**:
   - Start with 1Gi and increase if needed
   - Monitor memory usage in Cloud Console

3. **Use request timeouts**:
   - Set appropriate timeouts to avoid unnecessary charges
   - Agent service may need longer timeouts (300-540s)

4. **Consider Cloud Run Jobs** for batch processing instead of always-on services

## Security Best Practices

1. **Use Secret Manager** for sensitive keys:
   ```bash
   # Store secrets
   echo -n "your-api-key" | gcloud secrets create openai-api-key --data-file=-
   
   # Grant access to service account
   gcloud secrets add-iam-policy-binding openai-api-key \
     --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
     --role="roles/secretmanager.secretAccessor"
   
   # Use in Cloud Run
   --set-secrets="OPENAI_API_KEY=openai-api-key:latest"
   ```

2. **Enable VPC Connector** for private service communication

3. **Use IAM authentication** instead of `--allow-unauthenticated` for internal services

4. **Regularly rotate API keys** and update secrets

## Monitoring

### Cloud Logging

All services log to Cloud Logging. View logs:
```bash
gcloud logging read "resource.type=cloud_run_revision" --limit 50
```

### Cloud Monitoring

Set up alerts for:
- Service availability
- Error rates
- Response times
- Memory usage

## Rollback Strategy

If a deployment fails:

```bash
# List revisions
gcloud run revisions list --service=project-orbit-api --region $REGION

# Rollback to previous revision
gcloud run services update-traffic project-orbit-api \
  --to-revisions=PREVIOUS_REVISION=100 \
  --region $REGION
```

## Next Steps

1. Set up CI/CD pipeline (GitHub Actions, Cloud Build)
2. Configure monitoring and alerting
3. Set up automated backups
4. Implement blue-green deployments
5. Add load testing

---

## Quick Reference

### Service URLs (After Deployment)
- FastAPI: `https://project-orbit-api-{hash}-{region}.a.run.app`
- Streamlit: `https://project-orbit-streamlit-{hash}-{region}.a.run.app`
- HITL: `https://project-orbit-hitl-{hash}-{region}.a.run.app`
- MCP: `https://project-orbit-mcp-{hash}-{region}.a.run.app`
- Agent: `https://project-orbit-agent-{hash}-{region}.a.run.app`

### Useful Commands
```bash
# Build all images
./scripts/build_images.sh all

# Deploy single service
gcloud run deploy SERVICE_NAME --image gcr.io/$PROJECT_ID/project-orbit-SERVICE:latest

# View logs
gcloud logging read "resource.labels.service_name=SERVICE_NAME" --limit 50

# Update environment variables
gcloud run services update SERVICE_NAME --update-env-vars KEY=VALUE --region $REGION
```

---

**Last Updated**: 2025-01-XX
**Version**: 2.0

