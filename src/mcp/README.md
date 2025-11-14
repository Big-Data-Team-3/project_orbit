# MCP Server - File Structure

This directory contains the Model Context Protocol (MCP) server implementation.

## File Structure

```
src/mcp/
├── __init__.py              # Package initialization
├── server.py                # Main FastAPI MCP server application
├── auth.py                  # API key authentication middleware
├── models.py                # MCP protocol request/response models
├── handlers/                # Endpoint handlers
│   ├── __init__.py
│   ├── tools.py            # Tool endpoint handlers
│   ├── resources.py        # Resource endpoint handlers
│   └── prompts.py          # Prompt endpoint handlers
└── README.md               # This file
```

## Components

### `server.py`
Main FastAPI application that:
- Exposes `/tool/*` endpoints for agent tools
- Exposes `/resource/*` endpoints for resources
- Exposes `/prompt/*` endpoints for prompts
- Handles authentication via API key
- Provides error handling and CORS support

### `auth.py`
Authentication middleware:
- API key verification via `X-API-Key` header
- Configurable via `MCP_API_KEY` environment variable
- Falls back to dev mode if no API key is configured

### `models.py`
Pydantic models for MCP protocol:
- `ToolDefinition`, `ToolListResponse`, `ToolCallRequest`, `ToolCallResponse`
- `ResourceDefinition`, `ResourceListResponse`, `ResourceReadRequest`, `ResourceReadResponse`
- `PromptDefinition`, `PromptListResponse`, `PromptGetRequest`, `PromptGetResponse`
- `MCPError` for error responses

### `handlers/tools.py`
Tool endpoint handlers:
- Lists available tools: `get_latest_structured_payload`, `rag_search_company`, `report_layoff_signal`
- Executes tool calls by routing to agent tools in `src/agents/tools.py`

### `handlers/resources.py`
Resource endpoint handlers:
- Lists available resources: company seed data, payloads, risk signals
- Reads resources from GCS or local filesystem
- Supports parameterized resources (e.g., payloads by company_id)

### `handlers/prompts.py`
Prompt endpoint handlers:
- Lists available prompts: dashboard system prompt
- Retrieves prompt templates from `src/prompts/`
- Supports argument substitution

## API Endpoints

### Tools
- `GET /tool/list` - List all available tools
- `POST /tool/call` - Execute a tool call

### Resources
- `GET /resource/list` - List all available resources
- `POST /resource/read` - Read a resource by URI

### Prompts
- `GET /prompt/list` - List all available prompts
- `POST /prompt/get` - Get a prompt template

### Other
- `GET /health` - Health check
- `GET /` - API information
- `GET /docs` - Interactive API documentation

## Running the Server

```bash
# Development
uvicorn src.mcp.server:app --host 0.0.0.0 --port 8001 --reload

# Production
uvicorn src.mcp.server:app --host 0.0.0.0 --port 8001 --workers 4
```

## Environment Variables

### Required for MCP Server
- `MCP_API_KEY` - API key for authentication (optional, defaults to dev mode if not set)
- `MCP_PORT` - Server port (default: 8001)

### Required for Tool Execution
- `OPENAI_API_KEY` - OpenAI API key (for RAG and LLM operations)
- `PINECONE_API_KEY` - Pinecone API key (for vector database)
- `PINECONE_INDEX` - Pinecone index name
- `EMBEDDING_MODEL` - Embedding model (default: text-embedding-3-small)
- `EMBEDDING_DIMENSION` - Embedding dimension (default: 1536)

### Optional for GCS Resources
- `GCS_BUCKET_NAME` - GCS bucket for resources (uses local filesystem if not set)
- `PROJECT_ID` - GCP project ID (for GCS access)
- `GCS_SEED_FILE_PATH` - Path to seed file in GCS (default: seed/forbes_ai50_seed.json)
- `ENVIROMENT` - Environment mode: "development" or "production" (default: development)

### Example .env file
```bash
# MCP Server
MCP_API_KEY=your_mcp_api_key_here
MCP_PORT=8001

# OpenAI
OPENAI_API_KEY=your_openai_api_key_here
LLM_MODEL=gpt-4o-mini

# Pinecone
PINECONE_API_KEY=your_pinecone_api_key_here
PINECONE_INDEX=your_pinecone_index_name
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSION=1536
RAG_TOP_K=10

# GCP (optional)
PROJECT_ID=your_gcp_project_id
GCS_BUCKET_NAME=your_gcs_bucket_name
GCS_SEED_FILE_PATH=seed/forbes_ai50_seed.json
ENVIROMENT=development
```

## Integration

The MCP server can be:
1. Run as a standalone service
2. Integrated with the existing `src/api.py` FastAPI app
3. Deployed as a separate Cloud Run service
4. Used by agents and Airflow DAGs via HTTP requests

