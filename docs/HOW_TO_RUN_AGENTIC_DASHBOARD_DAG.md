# How to Run `orbit_agentic_dashboard_dag.py`

This guide explains how to run the agentic dashboard generation DAG in different environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Development (Docker Compose)](#local-development-docker-compose)
3. [Cloud Composer Deployment](#cloud-composer-deployment)
4. [Manual Triggering](#manual-triggering)
5. [Monitoring and Debugging](#monitoring-and-debugging)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Environment Variables

The DAG requires the following environment variables (set via Airflow Variables or `.env` file):

| Variable | Description | Example |
|----------|-------------|---------|
| `GCS_BUCKET_NAME` | GCS bucket name | `project-orbit-data-12345` |
| `PROJECT_ID` | GCP project ID | `your-project-id` |
| `OPENAI_API_KEY` | OpenAI API key | `sk-...` |
| `MCP_SERVER_URL` | MCP server URL | `http://mcp-server:8000` or `http://localhost:8001` |
| `MCP_API_KEY` | MCP server API key | `dev-key` or your API key |

### Required Services

1. **MCP Server**: Must be running and accessible
2. **GCS Bucket**: Must exist with seed file at `seed/forbes_ai50_seed.json`
3. **Pinecone**: Vector database must be configured (used by RAG pipeline)
4. **OpenAI API**: Must be accessible

---

## Local Development (Docker Compose)

### Step 1: Set Up Environment Variables

Create a `.env` file in the project root:

```bash
# GCS Configuration
GCS_BUCKET_NAME=project-orbit-data-12345
PROJECT_ID=your-project-id

# OpenAI Configuration
OPENAI_API_KEY=sk-your-openai-api-key

# MCP Server Configuration
MCP_SERVER_URL=http://project-orbit-mcp:8001
MCP_API_KEY=dev-key

# Pinecone Configuration (if needed)
PINECONE_API_KEY=your-pinecone-api-key
PINECONE_INDEX=your-index-name
```

### Step 2: Start Airflow Services

If you have `docker-compose.airflow.yml`:

```bash
# Start Airflow services
docker-compose -f docker-compose.airflow.yml up -d

# Check logs
docker-compose -f docker-compose.airflow.yml logs -f airflow-scheduler
```

### Step 3: Access Airflow UI

1. Open browser: `http://localhost:8080`
2. Login:
   - Username: `airflow`
   - Password: `airflow` (default)

### Step 4: Set Airflow Variables

In Airflow UI:
1. Go to **Admin → Variables**
2. Add the following variables:

```
Key: GCS_BUCKET_NAME
Value: project-orbit-data-12345

Key: PROJECT_ID
Value: your-project-id

Key: OPENAI_API_KEY
Value: sk-your-openai-api-key

Key: MCP_SERVER_URL
Value: http://project-orbit-mcp:8001

Key: MCP_API_KEY
Value: dev-key
```

### Step 5: Ensure MCP Server is Running

The MCP server must be accessible. If using Docker Compose:

```bash
# Start MCP server (if not already running)
docker-compose up -d mcp

# Verify MCP server is healthy
curl http://localhost:8001/health
```

### Step 6: Verify DAG is Loaded

1. In Airflow UI, go to **DAGs** page
2. Find `orbit_agentic_dashboard_dag`
3. Ensure it's **unpaused** (toggle switch should be ON)

### Step 7: Trigger the DAG

**Option A: Via Airflow UI**
1. Click on `orbit_agentic_dashboard_dag`
2. Click **Trigger DAG** button (play icon)
3. Click **Trigger** to confirm

**Option B: Via CLI**
```bash
# Trigger DAG
docker exec -it <airflow-scheduler-container> airflow dags trigger orbit_agentic_dashboard_dag
```

---

## Cloud Composer Deployment

### Step 1: Upload DAG to Cloud Composer

```bash
# Set your Cloud Composer environment details
export COMPOSER_ENV=your-composer-env
export COMPOSER_LOCATION=us-central1
export COMPOSER_PROJECT=your-project-id

# Upload DAG file
gcloud composer environments storage dags import \
  --environment $COMPOSER_ENV \
  --location $COMPOSER_LOCATION \
  --source dags/orbit_agentic_dashboard_dag.py
```

### Step 2: Upload Source Code

```bash
# Upload src/ directory to Cloud Composer plugins
gcloud composer environments storage plugins import \
  --environment $COMPOSER_ENV \
  --location $COMPOSER_LOCATION \
  --source src/
```

### Step 3: Set Airflow Variables

**Via gcloud CLI:**
```bash
gcloud composer environments run $COMPOSER_ENV \
  --location $COMPOSER_LOCATION \
  variables -- \
  --set GCS_BUCKET_NAME "project-orbit-data-12345" \
  --set PROJECT_ID "your-project-id" \
  --set OPENAI_API_KEY "sk-your-openai-api-key" \
  --set MCP_SERVER_URL "http://mcp-server:8000" \
  --set MCP_API_KEY "your-mcp-api-key"
```

**Via Airflow UI:**
1. Open Cloud Composer Airflow UI
2. Go to **Admin → Variables**
3. Add variables as listed above

### Step 4: Configure MCP Server Access

Ensure the MCP server is accessible from Cloud Composer:

- **If MCP server is in GCP**: Use internal IP or Cloud Run URL
- **If MCP server is external**: Ensure firewall rules allow access

### Step 5: Verify DAG is Loaded

1. Open Cloud Composer Airflow UI
2. Check **DAGs** page for `orbit_agentic_dashboard_dag`
3. Ensure DAG is **unpaused**

### Step 6: Trigger the DAG

**Via Airflow UI:**
1. Click on `orbit_agentic_dashboard_dag`
2. Click **Trigger DAG** button
3. Confirm trigger

**Via gcloud CLI:**
```bash
gcloud composer environments run $COMPOSER_ENV \
  --location $COMPOSER_LOCATION \
  trigger_dag orbit_agentic_dashboard_dag
```

---

## Manual Triggering

### Via Airflow CLI (Local)

```bash
# Trigger DAG
airflow dags trigger orbit_agentic_dashboard_dag

# Check DAG status
airflow dags list | grep orbit_agentic_dashboard_dag

# View DAG runs
airflow dags list-runs -d orbit_agentic_dashboard_dag
```

### Via Airflow API

```bash
# Trigger DAG via API
curl -X POST \
  "http://localhost:8080/api/v1/dags/orbit_agentic_dashboard_dag/dagRuns" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'airflow:airflow' | base64)" \
  -d '{}'
```

### Via Python Script

```python
from airflow.api.client.local_client import Client

client = Client(None, None)
client.trigger_dag(dag_id='orbit_agentic_dashboard_dag')
```

---

## Monitoring and Debugging

### View DAG Run Status

1. **Airflow UI**: Go to DAG details page
2. **Graph View**: See task execution flow
3. **Tree View**: See all DAG runs and their status
4. **Gantt View**: See task duration and timing

### Check Task Logs

1. Click on a task in the Graph View
2. Click **Log** button
3. Review logs for errors or warnings

### Monitor GCS Output

```bash
# List generated dashboards
gsutil ls gs://project-orbit-data-12345/dashboards/

# View a specific dashboard
gsutil cat gs://project-orbit-data-12345/dashboards/anthropic/2025-01-15_020000/dashboard.md

# View batch summary
gsutil cat gs://project-orbit-data-12345/dashboards/batch_20250115_020000/summary.json
```

### Check MCP Server Logs

```bash
# If using Docker
docker logs project-orbit-mcp -f

# Check MCP server health
curl http://localhost:8001/health
```

### Monitor Workflow Execution

The DAG generates detailed logs for each company:

```
🎯 Generating dashboard for Anthropic (anthropic)
  SupervisorAgent initialized for Anthropic
  Executing workflow for Anthropic...
  ✅ Workflow completed for Anthropic. Status: completed, Risk detected: False, Dashboard length: 3247 chars
  📄 Dashboard saved to gs://bucket/dashboards/anthropic/2025-01-15_020000/dashboard.md
  📊 Trace saved to gs://bucket/dashboards/anthropic/2025-01-15_020000/trace.json
```

---

## Troubleshooting

### Issue: DAG Not Appearing in Airflow UI

**Solution:**
1. Check DAG file syntax: `python -m py_compile dags/orbit_agentic_dashboard_dag.py`
2. Check Airflow scheduler logs for import errors
3. Verify DAG file is in correct location: `/opt/airflow/dags/`
4. Restart Airflow scheduler: `docker-compose restart airflow-scheduler`

### Issue: Import Errors

**Error**: `ModuleNotFoundError: No module named 'agents'`

**Solution:**
1. Verify `src/` directory is mounted/copied to `/opt/airflow/src/`
2. Check `PYTHONPATH` includes `/opt/airflow/src`
3. Verify imports use correct path (e.g., `from agents.supervisor import SupervisorAgent`)

### Issue: MCP Server Connection Failed

**Error**: `Connection refused` or `Failed to connect to MCP server`

**Solution:**
1. Verify MCP server is running: `curl http://localhost:8001/health`
2. Check `MCP_SERVER_URL` is correct (use service name in Docker: `http://project-orbit-mcp:8001`)
3. For Cloud Composer: Ensure MCP server is accessible from GCP network
4. Check firewall rules if using external MCP server

### Issue: OPENAI_API_KEY Not Set

**Error**: `OPENAI_API_KEY is not set`

**Solution:**
1. Set Airflow Variable: `OPENAI_API_KEY`
2. Or set environment variable in `.env` file
3. Restart Airflow services after setting variables

### Issue: GCS Access Denied

**Error**: `403 Forbidden` or `Access denied`

**Solution:**
1. Verify service account has GCS permissions
2. Check `GOOGLE_APPLICATION_CREDENTIALS` is set (for local)
3. For Cloud Composer: Ensure Composer service account has `Storage Admin` role
4. Verify bucket name is correct

### Issue: Workflow Execution Timeout

**Error**: Task times out after 1 hour

**Solution:**
1. Increase `execution_timeout` in task decorator:
   ```python
   @task(execution_timeout=timedelta(hours=2))
   ```
2. Check for slow MCP server responses
3. Monitor individual company processing times
4. Consider reducing `max_active_tasks` to avoid resource contention

### Issue: No Companies Loaded

**Error**: `Failed to load seed file from GCS`

**Solution:**
1. Verify seed file exists: `gsutil ls gs://bucket/seed/forbes_ai50_seed.json`
2. Check file permissions
3. Verify `GCS_BUCKET_NAME` variable is correct
4. Check GCS client initialization in logs

### Issue: Dashboard Generation Fails

**Error**: Workflow fails at `data_generator` node

**Solution:**
1. Check Pinecone connection and API key
2. Verify vector database has data for the company
3. Check RAG pipeline logs
4. Verify MCP tools are working: `curl http://mcp-server:8000/tools`

### Issue: HITL Approval Not Working

**Error**: Workflow stuck at `hitl_pause` node

**Solution:**
1. Check approval file location: `data/hitl_approvals/`
2. Verify file permissions
3. Manually approve by editing approval JSON file:
   ```json
   {
     "approval_id": "...",
     "approved": true
   }
   ```

---

## Testing with a Single Company

To test with a single company instead of all 50:

1. **Modify seed file** (temporarily):
   ```bash
   # Download seed file
   gsutil cp gs://bucket/seed/forbes_ai50_seed.json /tmp/
   
   # Edit to include only one company
   # Keep only one company object in the JSON array
   
   # Upload back
   gsutil cp /tmp/forbes_ai50_seed.json gs://bucket/seed/
   ```

2. **Or modify DAG** (for testing):
   ```python
   @task
   def load_company_list(**context):
       # ... existing code ...
       # For testing: return only first company
       return companies_data[:1]  # Only first company
   ```

---

## Schedule Configuration

The DAG is scheduled to run daily at 2 AM UTC:

```python
schedule_interval='0 2 * * *'  # 2 AM daily
```

To change the schedule:

1. **Modify DAG file**:
   ```python
   schedule_interval='0 6 * * *'  # 6 AM daily
   # or
   schedule_interval='@daily'  # Once per day
   # or
   schedule_interval=None  # Manual trigger only
   ```

2. **Redeploy DAG** to Airflow

---

## Performance Considerations

- **Parallelism**: DAG uses `max_active_tasks=5` to limit concurrent executions
- **Timeout**: Each company has 1 hour timeout
- **Expected Duration**: 
  - Single company: ~5-10 minutes
  - All 50 companies: ~2-4 hours (with 5 parallel tasks)
- **Resource Usage**: Each task uses OpenAI API and MCP server

---

## Next Steps

After successful execution:

1. **Check dashboards**: Review generated dashboards in GCS
2. **Review batch summary**: Check `batch_{timestamp}/summary.json`
3. **Monitor logs**: Review Airflow logs for any warnings
4. **Verify traces**: Check ReAct traces for debugging
5. **Set up alerts**: Configure email notifications for failures

---

## Additional Resources

- [ReAct Trace Documentation](REACT_TRACE_EXAMPLE.md)
- [Workflow Graph Documentation](WORKFLOW_GRAPH.md)
- [Architecture Diagram](ARCHITECTURE_DIAGRAM.md)

