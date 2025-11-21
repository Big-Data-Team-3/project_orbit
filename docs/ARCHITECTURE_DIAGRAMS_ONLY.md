# Project ORBIT - Mermaid Diagrams Only

This file contains individual Mermaid diagrams extracted from the main architecture document. Use these to test diagrams individually in [Mermaid Live Editor](https://mermaid.live).

---

## Diagram 1: Current State Architecture

```mermaid
graph TB
    subgraph "Data Sources"
        WEB[Company Websites]
        NEWS[News Articles]
        JOBS[Job Postings]
        RSS[RSS Feeds]
    end

    subgraph "Ingestion Layer"
        CF1[Cloud Function: full_ingest]
        CF2[Cloud Function: daily_refresh]
        CF3[Cloud Function: scrape_and_index]
        CF4[Cloud Function: structured_extraction]
        SCHED[Cloud Scheduler]
    end

    subgraph "Storage Layer"
        GCS[(Google Cloud Storage)]
        PC[(Pinecone Vector DB)]
    end

    subgraph "Processing Layer"
        SCRAPER[Scraper v2<br/>scraper_v2.py]
        CHUNKER[Chunker<br/>chunker.py]
        EMBED[Embeddings<br/>embeddings.py]
        STRUCT[Structured Extraction<br/>structured_extraction_v2.py]
    end

    subgraph "API Layer"
        API[FastAPI Backend<br/>api.py]
        RAG_PIPE[RAG Pipeline<br/>rag_pipeline.py]
        STRUCT_PIPE[Structured Pipeline]
    end

    subgraph "Frontend Layer"
        STREAMLIT[Streamlit App<br/>streamlit_app.py]
    end

    subgraph "External Services"
        OPENAI[OpenAI API<br/>GPT-4o-mini<br/>text-embedding-3-small]
    end

    WEB --> SCRAPER
    NEWS --> SCRAPER
    JOBS --> SCRAPER
    RSS --> SCRAPER

    SCHED --> CF1
    SCHED --> CF2
    CF1 --> SCRAPER
    CF2 --> SCRAPER
    CF3 --> SCRAPER
    CF3 --> CHUNKER
    CF4 --> STRUCT

    SCRAPER --> GCS
    CHUNKER --> EMBED
    EMBED --> OPENAI
    EMBED --> PC
    STRUCT --> OPENAI
    STRUCT --> GCS

    GCS --> RAG_PIPE
    GCS --> STRUCT_PIPE
    PC --> RAG_PIPE
    RAG_PIPE --> OPENAI
    STRUCT_PIPE --> OPENAI

    RAG_PIPE --> API
    STRUCT_PIPE --> API
    API --> STREAMLIT
```

---

## Diagram 2: Data Pipeline Flow (Sequence)

```mermaid
sequenceDiagram
    participant Scheduler as Cloud Scheduler
    participant CF as Cloud Functions
    participant Scraper as Scraper v2
    participant GCS as Google Cloud Storage
    participant Chunker as Chunker Service
    participant Embed as Embeddings Service
    participant Pinecone as Pinecone Vector DB
    participant StructExt as Structured Extractor
    participant OpenAI as OpenAI API
    participant API as FastAPI Backend
    participant Frontend as Streamlit UI

    Note right of Scheduler: Data Ingestion Phase
    Scheduler->>CF: Trigger cron/HTTP
    CF->>Scraper: Scrape Company Website
    Scraper->>Scraper: Extract HTML Text Metadata
    Scraper->>GCS: Upload raw data

    Note right of Scheduler: RAG Pipeline
    CF->>GCS: Download Text Files
    GCS->>Chunker: Text Chunks
    Chunker->>Embed: Chunked Text
    Embed->>OpenAI: Generate Embeddings
    OpenAI->>Embed: Vector Embeddings
    Embed->>Pinecone: Store Vectors

    Note right of Scheduler: Structured Pipeline
    CF->>GCS: Download All Sources
    GCS->>StructExt: HTML Text JSON-LD
    StructExt->>OpenAI: Extract Structured Data
    OpenAI->>StructExt: Pydantic Models
    StructExt->>GCS: Save payloads

    Note right of Frontend: Dashboard Generation
    Frontend->>API: POST /dashboard/rag
    API->>Pinecone: Query Vectors
    Pinecone->>API: Relevant Context
    API->>OpenAI: Generate Dashboard RAG
    OpenAI->>API: Markdown Dashboard
    API->>Frontend: Dashboard Response

    Frontend->>API: POST /dashboard/structured
    API->>GCS: Load payloads
    GCS->>API: Payload Data
    API->>OpenAI: Generate Dashboard Structured
    OpenAI->>API: Markdown Dashboard
    API->>Frontend: Dashboard Response
```

---

## Diagram 3: Agent Architecture Overview

```mermaid
graph TB
    subgraph "Orchestration Layer (Assignment 5)"
        AIRFLOW[Airflow DAG<br/>orbit_agentic_dashboard_dag.py]
        SUPERVISOR[Supervisor Agent<br/>supervisor.py]
        WORKFLOW[LangGraph Workflow<br/>due_diligence_graph.py]
    end

    subgraph "Agent Tools (Lab 12)"
        TOOL1[get_latest_structured_payload]
        TOOL2[rag_search_company]
        TOOL3[report_layoff_signal]
    end

    subgraph "MCP Server (Lab 14)"
        MCP_SERVER[MCP Server<br/>mcp_server.py]
        MCP_TOOL1[POST /tool/generate_structured_dashboard]
        MCP_TOOL2[POST /tool/generate_rag_dashboard]
        MCP_RES1[GET /resource/ai50/companies]
        MCP_PROMPT1[GET /prompt/pe-dashboard]
    end

    subgraph "Workflow Nodes (Lab 17)"
        PLANNER[Planner Node]
        DATA_GEN[Data Generator Node]
        EVALUATOR[Evaluator Node]
        RISK_DET[Risk Detector Node]
        HITL[Human-in-the-Loop Node]
    end

    subgraph "Existing Infrastructure"
        GCS[(GCS)]
        PC[(Pinecone)]
        API[FastAPI]
        RAG[RAG Pipeline]
        STRUCT[Structured Pipeline]
    end

    AIRFLOW --> SUPERVISOR
    SUPERVISOR --> WORKFLOW
    WORKFLOW --> PLANNER
    PLANNER --> DATA_GEN
    DATA_GEN --> MCP_SERVER
    DATA_GEN --> TOOL1
    DATA_GEN --> TOOL2
    DATA_GEN --> TOOL3
    MCP_SERVER --> MCP_TOOL1
    MCP_SERVER --> MCP_TOOL2
    MCP_SERVER --> MCP_RES1
    MCP_SERVER --> MCP_PROMPT1
    MCP_TOOL1 --> STRUCT
    MCP_TOOL2 --> RAG
    TOOL1 --> GCS
    TOOL2 --> PC
    DATA_GEN --> EVALUATOR
    EVALUATOR --> RISK_DET
    RISK_DET -->|High Risk| HITL
    RISK_DET -->|Low Risk| API
    HITL --> API
```

---

## Diagram 4: ReAct Pattern Flow

```mermaid
sequenceDiagram
    participant User as User or Airflow
    participant Supervisor as Supervisor Agent
    participant Tools as Agent Tools
    participant MCP as MCP Server
    participant Services as Backend Services

    User->>Supervisor: Task Generate dashboard
    Supervisor->>Supervisor: Thought Need to gather data
    
    Supervisor->>Tools: get_latest_structured_payload
    Tools->>Services: Load from GCS
    Services->>Tools: Payload Data
    Tools->>Supervisor: Observation Payload found
    
    Supervisor->>Supervisor: Thought Check recent news via RAG
    Supervisor->>Tools: rag_search_company
    Tools->>Services: Query Pinecone
    Services->>Tools: Top relevant chunks
    Tools->>Supervisor: Observation Found funding mentions
    
    Supervisor->>Supervisor: Thought Generate dashboard via MCP
    Supervisor->>MCP: POST generate_structured_dashboard
    MCP->>Services: Call structured pipeline
    Services->>MCP: Dashboard Markdown
    MCP->>Supervisor: Observation Dashboard generated
    
    Supervisor->>Supervisor: Thought Check risk signals
    Supervisor->>Tools: report_layoff_signal
    Tools->>Supervisor: Observation No layoff signals
    
    Supervisor->>User: Final Answer Dashboard ready
```

---

## Diagram 5: LangGraph Workflow

```mermaid
stateDiagram-v2
    [*] --> Planner: Start Workflow
    
    Planner --> DataGenerator: Plan Created
    DataGenerator --> DataGenerator: Invoke MCP Tools
    DataGenerator --> DataGenerator: Gather Structured Data
    DataGenerator --> DataGenerator: Query RAG Pipeline
    
    DataGenerator --> Evaluator: Data Collected
    Evaluator --> Evaluator: Score Dashboard Quality
    Evaluator --> Evaluator: Check Completeness
    
    Evaluator --> RiskDetector: Evaluation Complete
    RiskDetector --> RiskDetector: Analyze Risk Signals
    RiskDetector --> RiskDetector: Check Layoff Signals
    RiskDetector --> RiskDetector: Check Funding Gaps
    
    RiskDetector --> HITL: High Risk Detected
    RiskDetector --> Complete: Low Risk
    
    HITL --> HITL: Wait for Human Approval
    HITL --> Complete: Approved
    HITL --> Planner: Rejected - Replan
    
    Complete --> [*]
```

---

## Diagram 6: Deployment Architecture

```mermaid
graph TB
    subgraph "GCP Services"
        CF[Cloud Functions<br/>Gen 2]
        CS[Cloud Scheduler]
        GCS[(Cloud Storage<br/>project-orbit-data)]
        CR1[Cloud Run<br/>FastAPI]
        CR2[Cloud Run<br/>Streamlit]
        SM[Secret Manager]
        LOG[Cloud Logging]
    end

    subgraph "External Services"
        OPENAI[OpenAI API]
        PC[Pinecone]
    end

    subgraph "Assignment 5 Additions"
        COMPOSER[Cloud Composer<br/>Airflow]
        MCP_CR[Cloud Run<br/>MCP Server]
        AGENT_CR[Cloud Run<br/>Agent Container]
    end

    CS -->|HTTP Trigger| CF
    CF --> GCS
    CF --> OPENAI
    CF --> PC
    CR1 --> GCS
    CR1 --> PC
    CR1 --> OPENAI
    CR1 --> SM
    CR2 --> CR1
    CF --> LOG
    CR1 --> LOG

    COMPOSER -->|Orchestrates| MCP_CR
    COMPOSER -->|Orchestrates| AGENT_CR
    AGENT_CR --> MCP_CR
    MCP_CR --> CR1
    AGENT_CR --> GCS
    AGENT_CR --> PC
```

---

## How to Use This File

1. **To test a single diagram:**
   - Copy the content between ` ```mermaid ` and ` ``` ` for any diagram above
   - Go to [Mermaid Live Editor](https://mermaid.live)
   - Paste the code and view the rendered diagram

2. **To view all diagrams in context:**
   - Open `ARCHITECTURE_DIAGRAM.md` in GitHub, GitLab, or VS Code with Mermaid support
   - The diagrams will render automatically in the markdown preview

3. **Troubleshooting:**
   - If a diagram doesn't render, check for syntax errors
   - Ensure you're using a Mermaid-compatible viewer
   - Some diagrams may need adjustments for specific Mermaid versions

