# On-Demand Dashboard Generation DAG

## Overview

The `orbit_on_demand_dashboard_dag` generates **three independent dashboards** for a single company on-demand:

1. **Structured Dashboard** - Generated from payload JSON (structured extraction pipeline)
2. **RAG Dashboard** - Generated from Pinecone vector search (RAG pipeline)
3. **Agentic Dashboard** - Generated using SupervisorAgent workflow (full agentic pipeline with HITL)

All three dashboards are generated in parallel, then risk detection is performed, and if risks are detected, the workflow pauses for Human-in-the-Loop (HITL) approval before storing the dashboards to GCS.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Backend API (FastAPI)                       │
│                                                          │
│  POST /api/trigger-dashboard-generation                 │
│  GET  /api/dashboard-status/{dag_run_id}                │
│  POST /api/hitl-approve/{approval_id}                   │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│              Airflow DAG                                │
│  orbit_on_demand_dashboard_dag                          │
│                                                          │
│  1. Extract Company Info                                │
│  2. Generate Structured Dashboard (parallel)            │
│  3. Generate RAG Dashboard (parallel)                  │
│  4. Generate Agentic Dashboard (parallel)               │
│  5. Detect Risks (all dashboards)                       │
│  6. Check HITL Approval (if risks detected)             │
│  7. Store All Dashboards to GCS (if approved)           │
└─────────────────────────────────────────────────────────┘
```

## GCS Storage Structure

All dashboards are stored in:
```
gs://bucket/dashboards/on_demand/{company_id}/{timestamp}/
├── structured_dashboard.md      # Structured pipeline dashboard
├── rag_dashboard.md              # RAG pipeline dashboard
├── agentic_dashboard.md          # Agentic workflow dashboard
├── agentic_trace.json            # ReAct trace from agentic workflow
└── metadata.json                 # Metadata for all three dashboards
```

## API Endpoints

### 1. Trigger Dashboard Generation

**Endpoint:** `POST /api/trigger-dashboard-generation`

**Request Body:**
```json
{
  "company_name": "Anthropic",
  "company_id": "anthropic"  // Optional
}
```

**Response:**
```json
{
  "dag_run_id": "manual__20251120_103000",
  "status": "queued",
  "message": "Dashboard generation triggered for Anthropic",
  "company_name": "Anthropic",
  "airflow_url": "http://localhost:8080/dags/orbit_on_demand_dashboard_dag/grid?dag_run_id=..."
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/api/trigger-dashboard-generation \
  -H "Content-Type: application/json" \
  -d '{"company_name": "Anthropic"}'
```

### 2. Check Dashboard Status

**Endpoint:** `GET /api/dashboard-status/{dag_run_id}`

**Response:**
```json
{
  "dag_run_id": "manual__20251120_103000",
  "state": "success",
  "start_date": "2025-11-20T10:30:00Z",
  "end_date": "2025-11-20T10:35:00Z",
  "task_states": {
    "extract_company_info": "success",
    "generate_structured_dashboard": "success",
    "generate_rag_dashboard": "success",
    "generate_agentic_dashboard": "success",
    "detect_risks": "success",
    "check_hitl_approval": "success",
    "store_dashboards": "success"
  },
  "result": {
    "company_id": "anthropic",
    "company_name": "Anthropic",
    "status": "success",
    "structured_dashboard_path": "dashboards/on_demand/anthropic/2025-11-20_103000/structured_dashboard.md",
    "rag_dashboard_path": "dashboards/on_demand/anthropic/2025-11-20_103000/rag_dashboard.md",
    "agentic_dashboard_path": "dashboards/on_demand/anthropic/2025-11-20_103000/agentic_dashboard.md",
    "agentic_trace_path": "dashboards/on_demand/anthropic/2025-11-20_103000/agentic_trace.json",
    "metadata_path": "dashboards/on_demand/anthropic/2025-11-20_103000/metadata.json"
  }
}
```

**Example:**
```bash
curl http://localhost:8000/api/dashboard-status/manual__20251120_103000
```

### 3. Approve/Reject HITL Request

**Endpoint:** `POST /api/hitl-approve/{approval_id}`

**Request Body:**
```json
{
  "approved": true,
  "decided_by": "admin"  // Optional
}
```

**Response:**
```json
{
  "approval_id": "123e4567-e89b-12d3-a456-426614174000",
  "approved": true,
  "message": "HITL decision recorded",
  "gcs_path": "gs://bucket/hitl_approvals/123e4567-e89b-12d3-a456-426614174000.json"
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/api/hitl-approve/123e4567-e89b-12d3-a456-426614174000 \
  -H "Content-Type: application/json" \
  -d '{"approved": true}'
```

## Environment Variables

The DAG uses the following environment variables (set in `.env` or Airflow Variables):

- `GCS_BUCKET_NAME` - GCS bucket name
- `PROJECT_ID` - GCP project ID
- `OPENAI_API_KEY` - OpenAI API key
- `MCP_SERVER_URL` - MCP server URL (default: `http://host.docker.internal:8000`)
- `MCP_API_KEY` - MCP API key
- `API_BASE` - Backend API URL (default: `http://host.docker.internal:8000`)

For the backend API to trigger Airflow:

- `AIRFLOW_BASE_URL` - Airflow webserver URL (default: `http://localhost:8080`)
- `AIRFLOW_USERNAME` - Airflow username (default: `airflow`)
- `AIRFLOW_PASSWORD` - Airflow password (default: `airflow`)

## Workflow Details

### 1. Extract Company Info
- Extracts `company_name` and `company_id` from DAG run parameters
- If `company_id` not provided, looks it up from seed file or derives it

### 2. Generate Dashboards (Parallel)
- **Structured Dashboard**: Calls `/dashboard/structured` API endpoint
- **RAG Dashboard**: Calls `/dashboard/rag` API endpoint
- **Agentic Dashboard**: Uses `SupervisorAgent.execute_workflow()` directly

### 3. Detect Risks
- Analyzes all three dashboards for risk signals
- Uses `detect_risk_signals()` from `risk_detection` module
- Aggregates risks from all dashboards

### 4. Check HITL Approval
- If no risks detected: Proceeds automatically
- If risks detected: 
  - Generates approval ID
  - Waits for approval file in GCS (`hitl_approvals/{approval_id}.json`)
  - Polls every 10 seconds for up to 5 minutes
  - If timeout: Rejects automatically

### 5. Store Dashboards
- Only stores if:
  - No risks detected, OR
  - Risks detected AND HITL approved
- Stores all three dashboards separately
- Stores agentic trace (if available)
- Stores metadata JSON with all information

## Integration with Existing System

✅ **No Impact on Current Frontend:**
- All existing endpoints (`/dashboard/structured`, `/dashboard/rag`, `/dashboard/agent`) remain unchanged
- Streamlit frontend continues to work as before
- New DAG runs independently in the background

✅ **Separate Storage:**
- New dashboards stored in `dashboards/on_demand/` prefix
- Existing dashboards remain in their original locations
- No conflicts or overwrites

## Usage Example

### Python Client

```python
import requests

# 1. Trigger dashboard generation
response = requests.post(
    "http://localhost:8000/api/trigger-dashboard-generation",
    json={"company_name": "Anthropic"}
)
dag_run_id = response.json()["dag_run_id"]

# 2. Poll for completion
import time
while True:
    status = requests.get(
        f"http://localhost:8000/api/dashboard-status/{dag_run_id}"
    ).json()
    
    if status["state"] == "success":
        print("✅ Dashboards generated!")
        print(f"Structured: {status['result']['structured_dashboard_path']}")
        print(f"RAG: {status['result']['rag_dashboard_path']}")
        print(f"Agentic: {status['result']['agentic_dashboard_path']}")
        break
    elif status["state"] == "failed":
        print("❌ Dashboard generation failed")
        break
    else:
        print(f"⏳ Status: {status['state']}")
        time.sleep(10)

# 3. If HITL approval needed (check metadata)
if status.get("result", {}).get("status") == "rejected":
    approval_id = status["result"].get("approval_id")
    # Approve via API
    requests.post(
        f"http://localhost:8000/api/hitl-approve/{approval_id}",
        json={"approved": True}
    )
```

## Troubleshooting

### DAG Not Triggering
- Check Airflow is running: `docker-compose -f docker-compose.airflow.yml ps`
- Verify `AIRFLOW_BASE_URL` is correct
- Check Airflow credentials in environment variables

### API Connection Errors
- For Docker Airflow, use `http://host.docker.internal:8000` for backend API
- For local Airflow, use `http://localhost:8000`
- Ensure backend API is running and accessible

### HITL Approval Not Working
- Check GCS bucket permissions
- Verify `hitl_approvals/` folder exists in bucket
- Check approval file format matches expected JSON structure

### Dashboard Generation Fails
- Check logs in Airflow UI: `http://localhost:8080`
- Verify all environment variables are set
- Check backend API endpoints are accessible from Airflow container

## Next Steps

1. **Test the DAG**: Trigger it manually from Airflow UI or via API
2. **Monitor Execution**: Watch task logs in Airflow UI
3. **Verify Storage**: Check GCS bucket for generated dashboards
4. **Integrate Frontend** (Optional): Add button in Streamlit to trigger DAG

