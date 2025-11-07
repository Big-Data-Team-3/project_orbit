# Cloud Functions Documentation

## Table of Contents

1. [Introduction](#introduction)
2. [Architecture Overview](#architecture-overview)
3. [Function Details](#function-details)
   - [full_ingest](#1-full_ingest)
   - [daily_refresh](#2-daily_refresh)
   - [scrape_and_index](#3-scrape_and_index)
   - [structured_extraction](#4-structured_extraction)
4. [Deployment](#deployment)
5. [Usage Examples](#usage-examples)
6. [Monitoring and Debugging](#monitoring-and-debugging)
7. [Data Flow Diagrams](#data-flow-diagrams)
8. [Troubleshooting](#troubleshooting)

---

## Introduction

### Overview

This project implements a serverless data pipeline using Google Cloud Functions to automate private-equity intelligence for Forbes AI 50 startups. The system scrapes public data from company websites, processes it through two parallel pipelines (RAG and structured), and stores the results in Google Cloud Storage (GCS) and Pinecone vector database.

### Technology Stack

- **Runtime**: Python 3.11
- **Framework**: Cloud Functions Gen2 (HTTP-triggered)
- **Storage**: Google Cloud Storage (GCS)
- **Vector Database**: Pinecone
- **LLM**: OpenAI (GPT-4o-mini for structured extraction, text-embedding-3-small for embeddings)
- **Structured Extraction**: Instructor + Pydantic
- **Web Scraping**: requests, BeautifulSoup, trafilatura, Playwright (fallback)

### Project Context

The system processes 50 companies from the Forbes AI 50 list, extracting:
- **Unstructured Data**: Website content → Chunks → Embeddings → Pinecone (RAG pipeline)
- **Structured Data**: Website content → Pydantic models → JSON files (Structured pipeline)

---

## Architecture Overview

### System Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    Seed File (GCS)                              │
│         gs://bucket/seed/forbes_ai50_seed.json                  │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│              Cloud Functions Orchestration                      │
└───┬───────────────────────────────────────────────────────────┬─┘
    │                                                            │
    ├──────────────────────┐                                   │
    │                      │                                    │
    ▼                      ▼                                    ▼
┌─────────────┐  ┌──────────────────┐  ┌──────────────────────┐
│ Pipeline 1  │  │   Pipeline 2      │  │   Pipeline 3         │
│ Scraping    │  │   RAG Indexing    │  │   Structured Extract │
└─────────────┘  └──────────────────┘  └──────────────────────┘
    │                      │                                    │
    ▼                      ▼                                    ▼
┌─────────────┐  ┌──────────────────┐  ┌──────────────────────┐
│ GCS: raw/   │  │   Pinecone       │  │   GCS: structured/   │
│ HTML + TXT  │  │   Vector DB      │  │   GCS: payloads/     │
└─────────────┘  └──────────────────┘  └──────────────────────┘
```

### GCS Bucket Structure

```
gs://project-orbit-data-12345/
├── seed/
│   └── forbes_ai50_seed.json          # Input: Company list
├── raw/
│   ├── {company_id}/
│   │   └── initial_pull/
│   │       ├── homepage.html
│   │       ├── homepage_clean.txt
│   │       ├── about.html
│   │       ├── about_clean.txt
│   │       ├── blog_posts/
│   │       └── metadata.json
│   └── ...
├── structured/
│   ├── {company_id}.json               # Structured data (Lab 5)
│   └── ...
├── payloads/
│   ├── {company_id}.json               # Complete payload (Lab 6)
│   └── ...
└── scraping_results/
    ├── scraping_results_initial_pull.json
    ├── scraping_and_indexing_results_batch_*.json
    └── structured_extraction_results_batch_*.json
```

### Function Relationships

1. **full_ingest** → Scrapes all companies → Stores in `raw/`
2. **scrape_and_index** → Scrapes + Chunks + Embeds → Stores in `raw/` + Pinecone
3. **structured_extraction** → Reads from `raw/` → Extracts structured data → Stores in `structured/` + `payloads/`
4. **daily_refresh** → Checks for changes → Re-scrapes updated pages → Stores in dated folders

---

## Function Details

### 1. full_ingest

**Purpose**: Full-load scraping for all Forbes AI 50 companies. Scrapes website content and stores HTML/TXT files in GCS.

**HTTP Endpoint**: `POST https://full-ingest-{hash}-uc.a.run.app`

**Trigger Method**: HTTP POST (manual or Cloud Scheduler)

**Query Parameters**: None

**Workflow**:

1. Loads company list from `gs://bucket/seed/forbes_ai50_seed.json`
2. For each company:
   - Discovers 12 page types (homepage, about, product, careers, blog, team, investors, customers, press, pricing, partners, contact)
   - Scrapes each page (HTTP-first, Playwright fallback)
   - Extracts clean text using trafilatura
   - Discovers and scrapes up to 20 blog posts
   - Saves HTML and TXT files locally
   - Uploads to `gs://bucket/raw/{company_id}/initial_pull/`
3. Aggregates results and saves summary to `scraping_results/scraping_results_initial_pull.json`

**Input Sources**:
- GCS: `seed/forbes_ai50_seed.json`
- External: Company websites

**Output Destinations**:
- GCS: `raw/{company_id}/initial_pull/` (HTML + TXT files)
- GCS: `scraping_results/scraping_results_initial_pull.json` (summary)

**Response Format**:
```json
{
  "status": "success",
  "message": "Processed 45/50 companies",
  "summary": {
    "successful": 45,
    "failed": 5,
    "total_pages": 523,
    "total_files": 1046
  }
}
```

**Configuration**:
- Memory: 512MB
- Timeout: 540s (9 minutes)
- Max Instances: 10
- Environment Variables: `GCP_PROJECT`, `GCS_BUCKET_NAME`, `REGION`

**Error Handling**:
- Individual company failures don't stop the entire process
- Errors are logged and included in the summary
- Returns HTTP 500 on critical failures

---

### 2. daily_refresh

**Purpose**: Daily refresh of key pages for all companies. Checks for changes and re-scrapes only updated pages.

**HTTP Endpoint**: `POST https://daily-refresh-{hash}-uc.a.run.app`

**Trigger Method**: HTTP POST (typically via Cloud Scheduler with cron: `0 3 * * *`)

**Query Parameters**: None

**Workflow**:

1. Creates dated folder: `daily_{YYYY-MM-DD}`
2. Loads company list from seed file
3. For each company:
   - Checks if key pages (homepage, about, careers, blog) have changed
   - If changed OR no previous data exists:
     - Re-scrapes the company
     - Uploads to `raw/{company_id}/daily_{YYYY-MM-DD}/`
   - If no changes detected: Skips scraping
4. Aggregates results and saves summary

**Input Sources**:
- GCS: `seed/forbes_ai50_seed.json`
- GCS: Previous scrape data (for change detection)
- External: Company websites

**Output Destinations**:
- GCS: `raw/{company_id}/daily_{YYYY-MM-DD}/` (dated folders)
- GCS: `scraping_results/scraping_results_daily_{YYYY-MM-DD}.json`

**Response Format**:
```json
{
  "status": "success",
  "message": "Daily refresh completed for 2025-11-06",
  "summary": {
    "successful": 12,
    "changed": 8,
    "total": 50
  }
}
```

**Configuration**:
- Memory: 512MB
- Timeout: 540s
- Max Instances: 10
- Environment Variables: `GCP_PROJECT`, `GCS_BUCKET_NAME`, `REGION`

**Note**: Change detection is currently a placeholder. Full implementation would compare content hashes.

---

### 3. scrape_and_index

**Purpose**: Combined scraping + RAG indexing pipeline. Scrapes companies, chunks text, creates embeddings, and stores in Pinecone. Supports batch processing to avoid timeouts.

**HTTP Endpoint**: `POST https://scrape-and-index-{hash}-uc.a.run.app`

**Trigger Method**: HTTP POST (manual or Cloud Scheduler)

**Query Parameters**:
- `start` (int, default: 0): Start index in company list
- `end` (int, optional): End index (defaults to start + batch_size)
- `batch_size` (int, default: 3): Number of companies per batch
- `batch_index` (int, optional): Batch number (alternative to start/end)

**Workflow**:

1. Loads company list from seed file
2. Determines batch range from parameters
3. For each company in batch:
   - **Step 1**: Scrapes company → Gets HTML + TXT files → Uploads to GCS
   - **Step 2**: Lists TXT files from GCS
   - **Step 3**: For each TXT file:
     - Downloads content from GCS
     - Chunks text (1000 characters per chunk)
     - Creates embeddings using OpenAI (`text-embedding-3-small`)
     - Stores embeddings in Pinecone with metadata
4. Aggregates results and saves batch summary

**Input Sources**:
- GCS: `seed/forbes_ai50_seed.json`
- External: Company websites
- OpenAI API: Embeddings generation
- Pinecone: Vector storage

**Output Destinations**:
- GCS: `raw/{company_id}/initial_pull/` (scraped files)
- Pinecone: Vector embeddings with metadata
- GCS: `scraping_results/scraping_and_indexing_results_batch_{N}.json`

**Response Format**:
```json
{
  "status": "success",
  "message": "Batch 1 completed: Processed 3/3 companies",
  "batch_info": {
    "batch_number": 1,
    "batch_start": 0,
    "batch_end": 3,
    "total_companies": 50
  },
  "summary": {
    "successful": 3,
    "failed": 0,
    "total_chunks_indexed": 364,
    "total_companies_in_batch": 3
  }
}
```

**Configuration**:
- Memory: 1GB
- Timeout: 540s
- Max Instances: 10
- Environment Variables:
  - `GCP_PROJECT`
  - `GCS_BUCKET_NAME`
  - `REGION`
  - `OPENAI_API_KEY`
  - `PINECONE_API_KEY`
  - `PINECONE_INDEX`
  - `EMBEDDING_MODEL` (default: `text-embedding-3-small`)

**Batch Processing**:
- Default batch size: 3 companies
- Processes companies sequentially within batch
- Each batch runs independently
- Results saved per batch for tracking

**Components Used**:
- `Chunker`: Splits text into 1000-character chunks
- `Embeddings`: Creates OpenAI embeddings with retry logic
- `PineconeStorage`: Stores vectors with metadata (text, source_path)

---

### 4. structured_extraction

**Purpose**: Extract structured data from scraped HTML/TXT files using Pydantic models and Instructor. Processes companies in batches and saves both structured data and payloads.

**HTTP Endpoint**: `POST https://structured-extraction-{hash}-uc.a.run.app`

**Trigger Method**: HTTP POST (manual or Cloud Scheduler)

**Query Parameters**:
- `start` (int, default: 0): Start index in company list
- `end` (int, optional): End index (defaults to start + batch_size)
- `batch_size` (int, default: 3): Number of companies per batch
- `batch_index` (int, optional): Batch number (alternative to start/end)

**Workflow**:

1. Loads company list from seed file
2. Determines batch range from parameters
3. For each company in batch:
   - **Step 1**: Loads scraped files from `raw/{company_id}/initial_pull/`
     - Text files (`*_clean.txt`)
     - HTML files (`*.html`)
     - Blog posts
     - Metadata
   - **Step 2**: Runs structured extraction using Instructor + Pydantic:
     - Extracts Company information
     - Extracts Funding Events
     - Extracts Leadership (founders + executives)
     - Extracts Products
     - Extracts Snapshot (hiring, offices, etc.)
     - Extracts Other Events (partnerships, launches, etc.)
     - Extracts Visibility metrics
   - **Step 3**: Saves structured data to `structured/{company_id}.json`
   - **Step 4**: Saves complete payload to `payloads/{company_id}.json`
4. Aggregates results and saves batch summary

**Input Sources**:
- GCS: `seed/forbes_ai50_seed.json`
- GCS: `raw/{company_id}/initial_pull/` (scraped files)
- OpenAI API: GPT-4o-mini for structured extraction

**Output Destinations**:
- GCS: `structured/{company_id}.json` (structured data)
- GCS: `payloads/{company_id}.json` (complete payload)
- GCS: `scraping_results/structured_extraction_results_batch_{N}.json`

**Response Format**:
```json
{
  "status": "success",
  "message": "Batch 1 completed: Processed 3/3 companies",
  "batch_info": {
    "batch_number": 1,
    "batch_start": 0,
    "batch_end": 3,
    "total_companies": 50
  },
  "summary": {
    "successful": 3,
    "failed": 0,
    "total_events": 45,
    "total_products": 12,
    "total_leadership": 18,
    "total_companies_in_batch": 3
  }
}
```

**Configuration**:
- Memory: 2GB (higher due to LLM processing)
- Timeout: 540s
- Max Instances: 5
- Environment Variables:
  - `GCP_PROJECT`
  - `GCS_BUCKET_NAME`
  - `REGION`
  - `OPENAI_API_KEY`
  - `OPENAI_MODEL` (default: `gpt-4o-mini`)
  - `GCS_SEED_FILE_PATH` (default: `seed/forbes_ai50_seed.json`)

**Structured Data Models** (Pydantic):
- `Company`: Legal name, HQ, founded year, categories, funding info
- `Event`: Funding events, product releases, partnerships, etc.
- `Product`: Name, description, pricing, GitHub, license
- `Leadership`: Founders and executives with roles, LinkedIn, education
- `Snapshot`: Headcount, job openings, offices, active products
- `Visibility`: News mentions, sentiment, GitHub stars, Glassdoor rating
- `Payload`: Complete container with all above entities

**Extraction Features**:
- Zero hallucination: Only extracts from scraped sources
- Comprehensive search: Searches all text files, HTML, blog posts
- JSON-LD parsing: Extracts structured data from HTML
- HTML pattern matching: Extracts team, pricing, locations, etc.
- Cross-validation: Validates leadership affiliation, filters placeholders
- Provenance tracking: Tracks source URLs and crawl timestamps

---

## Deployment

### Prerequisites

1. **GCP Project Setup**:
   - Project ID: `project-orbit123`
   - Region: `us-central1`
   - GCS Bucket: `project-orbit-data-12345`

2. **Required APIs Enabled**:
   - Cloud Functions API
   - Cloud Build API
   - Cloud Storage API
   - Cloud Scheduler API (for scheduled triggers)

3. **Service Account Permissions**:
   - Cloud Functions Invoker
   - Storage Object Admin (for GCS access)
   - Cloud Functions Developer

4. **Environment Variables** (in `.env` file):
   ```bash
   OPENAI_API_KEY=sk-...
   PINECONE_API_KEY=...
   PINECONE_INDEX=forbes-ai-index
   EMBEDDING_MODEL=text-embedding-3-small
   OPENAI_MODEL=gpt-4o-mini
   ```

### Deployment Script

**File**: `scripts/deploy_functions.sh`

**Usage**:
```bash
bash scripts/deploy_functions.sh
```

**What It Does**:
1. Loads environment variables from `.env` file
2. Loads bucket configuration from `.gcs_config`
3. Deploys all 4 Cloud Functions:
   - `full_ingest`
   - `daily_refresh`
   - `scrape_and_index`
   - `structured_extraction`
4. Retrieves function URLs
5. Saves configuration to `.functions_config`

**Configuration File**: `.functions_config`
```bash
PROJECT_ID=project-orbit123
REGION=us-central1
BUCKET_NAME=project-orbit-data-12345
FULL_INGEST_URL=https://full-ingest-{hash}-uc.a.run.app
DAILY_REFRESH_URL=https://daily-refresh-{hash}-uc.a.run.app
SCRAPE_AND_INDEX_URL=https://scrape-and-index-{hash}-uc.a.run.app
STRUCTURED_EXTRACTION_URL=https://structured-extraction-{hash}-uc.a.run.app
```

### Manual Deployment

To deploy a single function:
```bash
gcloud functions deploy {function_name} \
    --gen2 \
    --runtime=python311 \
    --region=us-central1 \
    --source=cloud_functions \
    --entry-point=main_{function_name} \
    --trigger-http \
    --allow-unauthenticated \
    --memory={memory} \
    --timeout=540s \
    --set-env-vars="GCP_PROJECT=project-orbit123,GCS_BUCKET_NAME=project-orbit-data-12345,..." \
    --project=project-orbit123
```

---

## Usage Examples

### Manual Invocation

#### 1. Full Ingest (All Companies)
```bash
source .functions_config
curl -X POST "$FULL_INGEST_URL"
```

#### 2. Daily Refresh
```bash
source .functions_config
curl -X POST "$DAILY_REFRESH_URL"
```

#### 3. Scrape and Index (Single Company)
```bash
source .functions_config
curl -X POST "$SCRAPE_AND_INDEX_URL?start=0&batch_size=1"
```

#### 4. Scrape and Index (Batch of 3)
```bash
source .functions_config
curl -X POST "$SCRAPE_AND_INDEX_URL?start=0&end=3&batch_size=3"
```

#### 5. Structured Extraction (Single Company)
```bash
source .functions_config
curl -X POST "$STRUCTURED_EXTRACTION_URL?start=0&batch_size=1"
```

#### 6. Structured Extraction (Batch of 3)
```bash
source .functions_config
curl -X POST "$STRUCTURED_EXTRACTION_URL?start=0&end=3&batch_size=3"
```

### Batch Processing Scripts

#### Process All Companies - Scrape and Index
```bash
bash scripts/run_batch_scrape_index.sh
```

This script:
- Loads function URL from `.functions_config`
- Counts total companies from seed file
- Processes in batches of 3
- Shows progress and handles errors
- Saves results summary

#### Process All Companies - Structured Extraction
```bash
bash scripts/run_batch_structured_extraction.sh
```

This script:
- Loads function URL from `.functions_config`
- Counts total companies from seed file
- Processes in batches of 3
- Shows progress and handles errors
- Saves results summary

### Cloud Scheduler Setup

#### Create Scheduler for Daily Refresh
```bash
gcloud scheduler jobs create http daily-refresh-job \
    --location=us-central1 \
    --schedule="0 3 * * *" \
    --uri="$DAILY_REFRESH_URL" \
    --http-method=POST \
    --project=project-orbit123
```

#### Create Scheduler for Weekly Scrape and Index
```bash
gcloud scheduler jobs create http scrape-index-job \
    --location=us-central1 \
    --schedule="0 4 * * 0" \
    --uri="$SCRAPE_AND_INDEX_URL?start=0&batch_size=3" \
    --http-method=POST \
    --project=project-orbit123
```

**Note**: For batch processing via scheduler, you'll need to trigger multiple batches sequentially or use Cloud Tasks for parallel execution.

---

## Monitoring and Debugging

### Viewing Logs

#### Cloud Console
1. Go to Cloud Functions in GCP Console
2. Click on function name
3. Navigate to "Logs" tab
4. Filter by severity level or search for specific terms

#### Command Line
```bash
# View logs for a specific function
gcloud functions logs read {function_name} \
    --gen2 \
    --region=us-central1 \
    --limit=50 \
    --project=project-orbit123

# Follow logs in real-time
gcloud functions logs read {function_name} \
    --gen2 \
    --region=us-central1 \
    --follow \
    --project=project-orbit123
```

### Checking Function Status

```bash
# List all functions
gcloud functions list --gen2 --region=us-central1 --project=project-orbit123

# Describe a specific function
gcloud functions describe {function_name} \
    --gen2 \
    --region=us-central1 \
    --project=project-orbit123

# Check function URL
gcloud functions describe {function_name} \
    --gen2 \
    --region=us-central1 \
    --format="get(serviceConfig.uri)" \
    --project=project-orbit123
```

### Verifying GCS Output

```bash
# List scraped files
gsutil ls -r gs://project-orbit-data-12345/raw/

# List structured data
gsutil ls gs://project-orbit-data-12345/structured/

# List payloads
gsutil ls gs://project-orbit-data-12345/payloads/

# View a specific file
gsutil cat gs://project-orbit-data-12345/structured/{company_id}.json | python3 -m json.tool

# Check batch results
gsutil ls gs://project-orbit-data-12345/scraping_results/
```

### Checking Pinecone Index

```python
from pinecone import Pinecone

pc = Pinecone(api_key="your-api-key")
index = pc.Index("forbes-ai-index")

# Check index stats
stats = index.describe_index_stats()
print(f"Total vectors: {stats.total_vector_count}")

# Query a sample
results = index.query(
    vector=[0.0] * 1536,  # Dummy vector
    top_k=5,
    include_metadata=True
)
```

---

## Data Flow Diagrams

### Complete Pipeline Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    INITIAL SETUP                            │
│  Seed File: gs://bucket/seed/forbes_ai50_seed.json         │
│  Contains: 50 companies with website URLs                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              PIPELINE 1: SCRAPE AND INDEX                   │
│                                                              │
│  scrape_and_index() Function                                │
│  ├─ Load companies from seed                                 │
│  ├─ For each company (batch of 3):                          │
│  │   ├─ Scrape website → HTML + TXT                          │
│  │   ├─ Upload to GCS: raw/{company_id}/initial_pull/      │
│  │   ├─ Download TXT files                                   │
│  │   ├─ Chunk text (1000 chars)                             │
│  │   ├─ Create embeddings (OpenAI)                            │
│  │   └─ Store in Pinecone                                   │
│  └─ Save batch summary                                       │
│                                                              │
│  Output:                                                     │
│  • GCS: raw/{company_id}/initial_pull/*.html, *.txt        │
│  • Pinecone: Vector embeddings with metadata                 │
│  • GCS: scraping_results/scraping_and_indexing_results_*   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│         PIPELINE 2: STRUCTURED EXTRACTION                   │
│                                                              │
│  structured_extraction() Function                            │
│  ├─ Load companies from seed                                 │
│  ├─ For each company (batch of 3):                          │
│  │   ├─ Load scraped files from GCS                          │
│  │   ├─ Extract Company info (Pydantic)                      │
│  │   ├─ Extract Events (funding, launches, etc.)            │
│  │   ├─ Extract Products                                     │
│  │   ├─ Extract Leadership                                   │
│  │   ├─ Extract Snapshot                                     │
│  │   ├─ Extract Visibility                                   │
│  │   ├─ Save structured/{company_id}.json                    │
│  │   └─ Save payloads/{company_id}.json                     │
│  └─ Save batch summary                                       │
│                                                              │
│  Output:                                                     │
│  • GCS: structured/{company_id}.json                        │
│  • GCS: payloads/{company_id}.json                          │
│  • GCS: scraping_results/structured_extraction_results_*    │
└─────────────────────────────────────────────────────────────┘
```

### Scrape and Index Detailed Flow

```
Company Website
    │
    ▼
┌─────────────────┐
│  Scraper        │ → Discovers 12 page types
│  (scraper.py)   │ → Scrapes HTML
└────────┬────────┘ → Extracts clean text (trafilatura)
         │
         ▼
┌─────────────────┐
│  GCS Upload     │ → raw/{company_id}/initial_pull/
│  (gcs_utils.py) │   • homepage.html, homepage_clean.txt
└────────┬────────┘   • about.html, about_clean.txt
         │            • blog_posts/*.html, *.txt
         │
         ▼
┌─────────────────┐
│  TXT Download   │ → List TXT files from GCS
│  (gcs_utils.py) │ → Download content
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Chunker        │ → Split into 1000-char chunks
│  (chunker.py)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Embeddings     │ → OpenAI API call
│  (embeddings.py)│ → text-embedding-3-small
└────────┬────────┘ → 1536-dimensional vector
         │
         ▼
┌─────────────────┐
│  Pinecone       │ → Store vector with metadata
│  (embeddings.py)│   • text: chunk content
└─────────────────┘   • source_path: company_id/filename
```

### Structured Extraction Detailed Flow

```
GCS: raw/{company_id}/initial_pull/
    │
    ├─ homepage_clean.txt
    ├─ about_clean.txt
    ├─ blog_posts/*.txt
    └─ metadata.json
    │
    ▼
┌─────────────────────────────────┐
│  load_all_sources()              │
│  • Loads all TXT files           │
│  • Loads all HTML files          │
│  • Extracts JSON-LD              │
│  • Parses HTML patterns          │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│  extract_company_payload()      │
│                                  │
│  ├─ extract_funding_events()    │ → Events: funding rounds
│  ├─ extract_leadership()        │ → Leadership: founders, execs
│  ├─ extract_products()          │ → Products: name, pricing, GitHub
│  ├─ extract_snapshot()          │ → Snapshot: hiring, offices
│  ├─ extract_other_events()      │ → Events: launches, partnerships
│  ├─ extract_company_record()    │ → Company: HQ, founded, categories
│  └─ extract_visibility()        │ → Visibility: news, sentiment
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│  Instructor + Pydantic          │
│  • GPT-4o-mini extracts data    │
│  • Pydantic validates structure │
│  • Zero hallucination enforced  │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│  Save to GCS                    │
│  • structured/{company_id}.json │ → All extracted entities
│  • payloads/{company_id}.json   │ → Complete Payload object
└─────────────────────────────────┘
```

---

## Troubleshooting

### Common Issues

#### 1. Function Timeout

**Symptom**: Function returns timeout error after 540 seconds

**Solutions**:
- Reduce batch size (use `batch_size=1` or `batch_size=2`)
- Increase timeout (requires redeployment with `--timeout=600s`)
- Process fewer companies per invocation

**Example**:
```bash
# Process single company to avoid timeout
curl -X POST "$SCRAPE_AND_INDEX_URL?start=0&batch_size=1"
```

#### 2. Import Errors

**Symptom**: `ImportError: No module named 'structured_extraction'`

**Solutions**:
- Ensure `structured_extraction.py` and `models.py` are in `cloud_functions/src/`
- Redeploy function: `bash scripts/deploy_functions.sh`
- Check Python path in function logs

#### 3. GCS Permission Errors

**Symptom**: `403 Forbidden` when accessing GCS bucket

**Solutions**:
- Verify service account has `Storage Object Admin` role
- Check bucket name is correct in environment variables
- Verify bucket exists: `gsutil ls gs://project-orbit-data-12345`

#### 4. OpenAI API Errors

**Symptom**: `RateLimitError` or `APIError` from OpenAI

**Solutions**:
- Check API key is set correctly: `echo $OPENAI_API_KEY`
- Verify API key has sufficient credits
- Function includes retry logic with exponential backoff
- Reduce batch size to avoid rate limits

#### 5. Pinecone Connection Errors

**Symptom**: `Failed to initialize Pinecone`

**Solutions**:
- Verify `PINECONE_API_KEY` is set
- Verify `PINECONE_INDEX` exists: `pc.list_indexes()`
- Check index dimension matches embedding model (1536 for text-embedding-3-small)

#### 6. Empty Results

**Symptom**: Function completes but no files in GCS

**Solutions**:
- Check function logs for errors
- Verify seed file exists: `gsutil ls gs://bucket/seed/forbes_ai50_seed.json`
- Check company_id extraction logic
- Verify GCS write permissions

#### 7. Dependency Conflicts

**Symptom**: Build fails with `ResolutionImpossible` error

**Solutions**:
- Check `cloud_functions/requirements.txt` for version conflicts
- Ensure compatible versions:
  - `instructor==1.2.0` requires `pydantic==2.7.0`
  - `openai==1.54.0` accepts `pydantic>=1.9.0,<3`
- Pin exact versions to avoid conflicts

#### 8. Batch Processing Stuck

**Symptom**: Batch script stops mid-execution

**Solutions**:
- Check function logs for the specific batch
- Verify network connectivity
- Re-run failed batches individually:
  ```bash
  curl -X POST "$FUNCTION_URL?start={failed_start}&end={failed_end}"
  ```

### Debugging Tips

1. **Enable Verbose Logging**:
   - Check Cloud Functions logs in GCP Console
   - Look for `logger.info()` and `logger.error()` messages
   - Function includes detailed logging at each step

2. **Test Individual Components**:
   ```python
   # Test GCS access
   from gcs_utils import load_json_from_gcs
   data = load_json_from_gcs("bucket-name", "seed/forbes_ai50_seed.json")
   
   # Test scraper locally
   from scraper import scrape_company
   result = scrape_company(company_dict, output_dir=Path("test_output"))
   
   # Test embeddings
   from services.embeddings import Embeddings
   emb = Embeddings()
   vector = emb.embed_text("test text")
   ```

3. **Verify Environment Variables**:
   ```bash
   # Check function environment variables
   gcloud functions describe {function_name} \
       --gen2 \
       --region=us-central1 \
       --format="get(serviceConfig.environmentVariables)" \
       --project=project-orbit123
   ```

4. **Check Function Status**:
   ```bash
   # View recent invocations
   gcloud functions logs read {function_name} \
       --gen2 \
       --region=us-central1 \
       --limit=10 \
       --project=project-orbit123
   ```

### Performance Optimization

1. **Batch Size Tuning**:
   - Start with `batch_size=1` to test
   - Increase to `batch_size=3` for production
   - Monitor execution time per batch
   - Adjust based on average processing time

2. **Memory Allocation**:
   - `scrape_and_index`: 1GB (sufficient for chunking + embeddings)
   - `structured_extraction`: 2GB (higher for LLM processing)
   - Monitor memory usage in Cloud Console

3. **Parallel Processing**:
   - Use Cloud Tasks to trigger multiple batches in parallel
   - Implement queue-based processing for large datasets
   - Consider Cloud Run Jobs for long-running tasks

---

## Additional Resources

### Related Files

- **Main Function**: `cloud_functions/main.py`
- **Scraper**: `cloud_functions/src/scraper.py`
- **GCS Utils**: `cloud_functions/src/gcs_utils.py`
- **Structured Extraction**: `cloud_functions/src/structured_extraction.py`
- **Models**: `cloud_functions/src/models.py`
- **Chunker**: `cloud_functions/src/services/chunker.py`
- **Embeddings**: `cloud_functions/src/services/embeddings.py`

### Deployment Scripts

- **Deploy All**: `scripts/deploy_functions.sh`
- **Batch Scrape Index**: `scripts/run_batch_scrape_index.sh`
- **Batch Structured Extraction**: `scripts/run_batch_structured_extraction.sh`

### Configuration Files

- **Function URLs**: `.functions_config`
- **GCS Config**: `.gcs_config`
- **Environment Variables**: `.env`

---

## Summary

This Cloud Functions architecture provides a scalable, serverless solution for processing Forbes AI 50 company data through two parallel pipelines:

1. **RAG Pipeline** (`scrape_and_index`): Scrapes → Chunks → Embeds → Stores in Pinecone
2. **Structured Pipeline** (`structured_extraction`): Scrapes → Extracts → Validates → Stores as JSON

Both pipelines support batch processing to handle large datasets efficiently while staying within Cloud Functions timeout limits. The system is designed for reliability with comprehensive error handling, logging, and result tracking.

