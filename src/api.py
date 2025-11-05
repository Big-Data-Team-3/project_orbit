from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import json
from pathlib import Path
import os
import dotenv

from rag_pipeline import generate_dashboard, retrieve_context, load_system_prompt
from openai import OpenAI
from services.embeddings import Embeddings

dotenv.load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="Project Orbit API",
    description="PE Dashboard Factory API for Forbes AI 50 Companies",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Initialize clients
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
embeddings_client = Embeddings()

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
SEED_FILE = PROJECT_ROOT / "data" / "forbes_ai50_seed.json"
PAYLOADS_DIR = PROJECT_ROOT / "data" / "payloads"


# ============================================================================
# Pydantic Models
# ============================================================================

class CompanyRequest(BaseModel):
    """Request model for company name"""
    company_name: str = Field(..., description="Name of the company (e.g., 'Abridge', 'Anthropic')")

class RAGSearchRequest(BaseModel):
    """Request model for RAG search"""
    company_name: str = Field(..., description="Name of the company to search")
    top_k: Optional[int] = Field(10, ge=1, le=50, description="Number of top results to return")

class DashboardResponse(BaseModel):
    """Response model for dashboard generation"""
    company_name: str
    dashboard: str
    pipeline_type: str  # "rag" or "structured"

class RAGSearchResponse(BaseModel):
    """Response model for RAG search"""
    company_name: str
    results: List[Dict]
    total_results: int

class CompanyInfo(BaseModel):
    """Company information model"""
    company_name: str
    website: str
    linkedin: str
    hq_city: str
    hq_country: str
    category: str

def load_companies() -> List[Dict]:
    """Load companies from seed file"""
    try:
        with open(SEED_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Company seed file not found")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid JSON in seed file")


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/", tags=["Root"])
async def root():
    """Root endpoint"""
    return {
        "message": "Project Orbit API - PE Dashboard Factory",
        "version": "0.1.0",
        "endpoints": {
            "companies": "/companies",
            "dashboard_rag": "/dashboard/rag",
        }
    }

@app.get("/companies", response_model=List[CompanyInfo], tags=["Companies"])
async def get_companies():
    """
    Get list of all Forbes AI 50 companies.
    
    Returns a list of all companies with their basic information.
    """
    try:
        companies = load_companies()
        return [CompanyInfo(**company) for company in companies]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load companies: {str(e)}")

@app.post("/dashboard/rag", response_model=DashboardResponse, tags=["Dashboard"])
async def generate_rag_dashboard(request: CompanyRequest):
    """
    Generate an investor-facing diligence dashboard using RAG pipeline.
    
    This endpoint implements Lab 7:
    - Retrieves top-k context from vector DB
    - Calls LLM with dashboard prompt
    - Returns markdown dashboard with all 8 required sections
    
    The dashboard is generated from unstructured data stored in the vector database.
    """
    try:
        print(f"Generating dashboard for {request.company_name}")
        dashboard = generate_dashboard(request.company_name)
        print(dashboard)
        return DashboardResponse(
            company_name=request.company_name,
            dashboard=dashboard,
            pipeline_type="rag"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate RAG dashboard: {str(e)}"
        )


# ============================================================================
# Health Check
# ============================================================================

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Project Orbit API"
    }