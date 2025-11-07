# Project ORBIT - Private Equity Intelligence for Forbes AI 50

Automating Private-Equity (PE) Intelligence for the Forbes AI 50

**Project ORBIT** is a comprehensive, cloud-hosted system that automates private-equity intelligence gathering and analysis for the Forbes AI 50 startups. The platform scrapes public data from company websites, processes it through two parallel generation pipelines (RAG and structured extraction), and serves investor-style diligence dashboards through a modern web interface.


- [Application URL](https://project-orbit-streamlit-267172092995.us-central1.run.app/)
- [Backend URL](https://project-orbit-api-267172092995.us-central1.run.app/)
- [Scheduler URL](https://us-central1-project-orbit123.cloudfunctions.net/)
- [Codelabs URL](https://docs.google.com/document/d/1nvzLvddrQmxCtXDee4xZZm30JXYEZF9SzeFhKeGppAM/edit?tab=t.ohf526kuil8m)
- [Video Link](https://drive.google.com/drive/folders/1uC8_yFrUPNdrogmC9K39u_j6KXZdEiel) 

## Problem Statement

Private equity analysts currently perform manual research on Forbes AI 50 companies by visiting websites, LinkedIn pages, and press releases to collect investment signals. This process:
- Doesn't scale to all 50 companies
- Is difficult to refresh daily
- Creates inconsistency across analysts
- Is time-consuming and error-prone

**Project ORBIT** solves this by automating the entire intelligence pipeline from data ingestion to dashboard generation.

## Project Structure

```
project_orbit/
├── cloud_functions/        # Cloud Functions (Lab 2 & 3 - Scraping automation)
│   ├── main.py            # Function entry points
│   ├── requirements.txt   # Function dependencies
│   └── src/               # Scraper and GCS utilities
├── dags/                  # DEPRECATED: Old Airflow DAGs (kept for reference)
├── src/                   # Source code (scraper, RAG, API, etc.)
├── data/                  # Data files (seed JSON, scraped data)
├── scripts/               # Setup and deployment scripts
└── notebooks/             # Jupyter notebooks for development
```

## Quick Start

### Lab 2 & 3: Cloud Functions + Cloud Scheduler

For detailed setup instructions, see [CLOUD_FUNCTIONS_DOCUMENTATION.md](./CLOUD_FUNCTIONS_DOCUMENTATION.md)

**Quick steps:**
1. Enable APIs: `bash scripts/enable_apis.sh`
2. Copy source code: `cp -r src cloud_functions/src`
3. Set bucket config: `echo 'BUCKET_NAME="project-orbit-data-12345"' > .gcs_config`
4. Deploy functions: `bash scripts/deploy_functions.sh`
5. Create schedulers: `bash scripts/create_schedulers.sh`

## Functions

- **full_ingest**: Full-load scraping for all 50 companies (manual trigger)
- **daily_refresh**: Daily refresh of key pages (runs at 3 AM UTC)

## Requirements

- `requirements.txt` - For local development (FastAPI, Streamlit, etc.)
- `cloud_functions/requirements.txt` - For Cloud Functions deployment

## Development

### Local Testing
```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Test scraper locally
python src/scraper.py --companies anthropic abridge
```

### Test Cloud Functions Locally
```bash
# Install functions framework
pip install functions-framework

# Run function locally
cd cloud_functions
functions-framework --target=main_full_ingest --debug
```



- **Cloud Scheduler** → Triggers Cloud Functions via HTTP (cron)
- **Cloud Functions** → Scrape companies and upload to GCS
- **Cloud Storage** → Stores scraped data (`project-orbit-data-12345`)

## Architecture

![Architecture](./assets/architecture.jpeg)

### Two Parallel Generation Pipelines

#### 1. **RAG Pipeline** (Unstructured)
```
Raw Website Data → Text Chunks → Embeddings → Pinecone Vector DB → LLM → PE Dashboard
```
![Architecture](./assets/rag_pipeline.jpeg)
#### 2. **Structured Pipeline** (Pydantic + Instructor)
```
Raw Website Data → Pydantic Models → JSON Payload → LLM → PE Dashboard
```
![Structured Pipeline](./assets/structured_pipeline.jpeg)
### System Components

- **Data Ingestion**: Cloud Functions scrape Forbes AI 50 company websites
- **Processing**: Two parallel pipelines process unstructured and structured data
- **Storage**: Google Cloud Storage for raw data, Pinecone for vector embeddings
- **Orchestration**: Apache Airflow DAGs for scheduled data refresh
- **Serving**: FastAPI backend + Streamlit frontend in Docker containers
- **Deployment**: Google Cloud Run with Cloud Build

### Data Flow

![Data Flow](./assets/data_flow.png)


## Tech Stack

### Core Technologies
- **Backend**: Python 3.11, FastAPI, Uvicorn
- **Frontend**: Streamlit
- **Containerization**: Docker, Docker Compose
- **Orchestration**: Apache Airflow
- **Cloud Platform**: Google Cloud Platform (GCP)

### GCP Services
- **Cloud Storage (GCS)**: Raw data, structured JSON, payloads
- **Cloud Run**: Containerized FastAPI + Streamlit deployment
- **Cloud Functions**: Serverless data processing pipelines
- **Secret Manager**: Secure API key storage
- **Cloud Logging & Monitoring**: Observability
- **Cloud Build / Container Registry**: CI/CD and image storage

### Data Processing
- **Vector Database**: Pinecone
- **LLM**: OpenAI GPT-4o-mini
- **Embeddings**: OpenAI text-embedding-3-small
- **Structured Extraction**: Instructor + Pydantic models
- **Web Scraping**: requests, BeautifulSoup, trafilatura, Playwright

---

## Prerequisites

### System Requirements
- Python 3.11+
- Docker & Docker Compose
- Git
- Google Cloud SDK (`gcloud` CLI)

### GCP Setup
1. **Create GCP Project**:
   ```bash
   gcloud projects create your-project-id
   gcloud config set project your-project-id
   ```

2. **Enable Required APIs**:
   ```bash
   gcloud services enable \
     storage.googleapis.com \
     run.googleapis.com \
     secretmanager.googleapis.com \
     logging.googleapis.com \
     monitoring.googleapis.com \
     cloudbuild.googleapis.com \
     containerregistry.googleapis.com \
     cloudfunctions.googleapis.com
   ```

3. **Create GCS Bucket**:
   ```bash
   gsutil mb -p your-project-id -c STANDARD -l us-central1 gs://your-bucket-name
   ```

4. **Store Secrets in Secret Manager**:
   ```bash
   # OpenAI API Key
   echo -n "your-openai-key" | gcloud secrets create openai-api-key --data-file=-

   # Pinecone API Key & Index
   echo -n "your-pinecone-key" | gcloud secrets create pinecone-api-key --data-file=-
   echo -n "your-index-name" | gcloud secrets create pinecone-index --data-file=-
   ```

---

## Quick Start

### 1. Clone & Setup
```bash
git clone https://github.com/your-username/project-orbit.git
cd project-orbit
```

### 2. Environment Configuration
```bash
# Copy and edit environment file
cp .env.example .env

# Edit .env with your configuration
# Required: GCP_PROJECT, GCS_BUCKET_NAME, REGION
# Optional: OPENAI_API_KEY, PINECONE_API_KEY, etc.
```

### 3. Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run FastAPI server
uvicorn src.api:app --reload --host 0.0.0.0 --port 8000

# In another terminal, run Streamlit
streamlit run src/streamlit_app.py --server.port 8501
```

### 4. Docker Development
```bash
# Build and run with Docker Compose
docker-compose up --build

# Access:
# - FastAPI: http://localhost:8000/docs
# - Streamlit: http://localhost:8501
```

---

## API Endpoints

### FastAPI Endpoints

- **`GET /`** - API root with service information
- **`GET /companies`** - List all Forbes AI 50 companies
- **`POST /dashboard/rag`** - Generate RAG-based PE dashboard
- **`POST /dashboard/structured`** - Generate structured-based PE dashboard
- **`GET /health`** - Health check endpoint

### Dashboard Schema

Both pipelines generate dashboards with 8 required sections:

1. **Company Overview**
2. **Business Model and GTM**
3. **Funding & Investor Profile**
4. **Growth Momentum**
5. **Visibility & Market Sentiment**
6. **Risks and Challenges**
7. **Outlook**
8. **Disclosure Gaps**

---

## Deployment

### Automated GCP Deployment

```bash
# Deploy everything to GCP
./deploy_gcp.sh
```

This script:
- Validates environment variables
- Creates/verifies service accounts
- Sets up IAM permissions
- Builds Docker image with Cloud Build
- Deploys FastAPI and Streamlit to Cloud Run

### Manual Deployment Steps

1. **Build Docker Image**:
   ```bash
   gcloud builds submit --tag gcr.io/$PROJECT_ID/project-orbit:latest
   ```

2. **Deploy FastAPI**:
   ```bash
   gcloud run deploy project-orbit-api \
     --image gcr.io/$PROJECT_ID/project-orbit:latest \
     --platform managed \
     --region us-central1 \
     --service-account=project-orbit-sa@${PROJECT_ID}.iam.gserviceaccount.com \
     --set-env-vars="GCS_BUCKET_NAME=$GCS_BUCKET_NAME,PROJECT_ID=$PROJECT_ID,..."
   ```

3. **Deploy Streamlit**:
   ```bash
   gcloud run deploy project-orbit-streamlit \
     --image gcr.io/$PROJECT_ID/project-orbit:latest \
     --platform managed \
     --region us-central1 \
     --service-account=project-orbit-sa@${PROJECT_ID}.iam.gserviceaccount.com \
     --set-env-vars="API_BASE=<fastapi-url>"
     --command streamlit --args "run,src/streamlit_app.py,--server.port,8501,--server.address,0.0.0.0"
   ```

---

## Monitoring & Debugging

### Cloud Functions Logs
```bash
# View function logs
gcloud functions logs read {function_name} \
  --gen2 \
  --region=us-central1 \
  --limit=50
```

### Cloud Run Logs
```bash
# View service logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=project-orbit-api" \
  --limit 50
```

### GCS Verification
```bash
# Check scraped data
gsutil ls -r gs://your-bucket/raw/

# View structured data
gsutil cat gs://your-bucket/structured/{company_id}.json | python3 -m json.tool
```

---

## Evaluation & Quality Assurance

The project includes comprehensive evaluation of both pipelines:

- **Factual Correctness**: Accuracy of extracted information
- **Schema Adherence**: Proper 8-section dashboard structure
- **Provenance Tracking**: Source attribution for all data
- **Hallucination Control**: Zero fabrication of information
- **Readability**: Investor-friendly presentation

### Testing Commands

```bash
# Test API health
curl http://localhost:8000/health

# Test company listing
curl http://localhost:8000/companies

# Test dashboard generation
curl -X POST "http://localhost:8000/dashboard/rag" \
  -H "Content-Type: application/json" \
  -d '{"company_name": "Anthropic"}'
```

