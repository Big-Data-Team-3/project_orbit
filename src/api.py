from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import json
from pathlib import Path
import os
import dotenv
from google.cloud import storage
from google.api_core.exceptions import NotFound
from google.oauth2 import service_account
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

storage_client = None



def get_storage_client():
    """Get or create GCS storage client"""
    global storage_client
    
    # If already initialized, return it
    if storage_client is not None:
        return storage_client
    
    # Check if we need GCS (production mode)
    bucket_name = os.getenv("GCS_BUCKET_NAME")
    if not bucket_name:
        # Local development - don't initialize
        print("GCS_BUCKET_NAME not set, skipping GCS client initialization")
        return None
    
    # Production mode - MUST initialize successfully
    print(f"Initializing GCS client for bucket: {bucket_name}")
    try:
        project_id = os.getenv("PROJECT_ID")
        PROJECT_ROOT = Path(__file__).parent.parent
        credentials_path = PROJECT_ROOT / "config" / "gcp.json"
        
        # Try to use credentials file if it exists (local development)
        if credentials_path.exists():
            from google.oauth2 import service_account
            credentials = service_account.Credentials.from_service_account_file(
                str(credentials_path)
            )
            storage_client = storage.Client(project=project_id, credentials=credentials)
            print(f"GCS client initialized with credentials from {credentials_path}")
        else:
            # Use Application Default Credentials (production/Cloud Run)
            # Cloud Run automatically provides credentials via the service account
            storage_client = storage.Client(project=project_id)
            print("GCS client initialized with Application Default Credentials (production mode)")
        
        print("GCS client initialized successfully")
        return storage_client
    except Exception as e:
        error_msg = str(e)
        print(f"ERROR: Failed to initialize GCS client: {error_msg}")
        
        # In production, this is a critical error - raise it
        raise HTTPException(
            status_code=500,
            detail=f"GCS client initialization failed. This is required when GCS_BUCKET_NAME is set. "
                   f"Error: {error_msg}. "
                   f"Check that the Cloud Run service account has 'Storage Object Viewer' role. "
                   f"Verify that Application Default Credentials are configured correctly."
        )
        
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
    """Load companies from seed file (local development)"""
    try:
        with open(SEED_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Company seed file not found")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid JSON in seed file")

def load_companies_from_gcs() -> List[Dict]:
    """Load companies from GCS bucket (production)"""
    try:
        # Check if GCS_BUCKET_NAME is set
        bucket_name = os.getenv("GCS_BUCKET_NAME")
        if not bucket_name:
            raise HTTPException(
                status_code=500, 
                detail="GCS_BUCKET_NAME environment variable is not set"
            )
        
        # Initialize GCS client lazily
        client = get_storage_client()
        if not client:
            raise HTTPException(
                status_code=500,
                detail="GCS client is not initialized. Check service account permissions and ensure GCS_BUCKET_NAME is set."
            )
        
        # Get the file path (remove leading slash if present)
        file_path = os.getenv("GCS_SEED_FILE_PATH", "seed/forbes_ai50_seed.json")
        if file_path.startswith('/'):
            file_path = file_path[1:]
        
        # Get the bucket and blob
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(file_path)
        
        # Check if blob exists
        if not blob.exists():
            raise HTTPException(
                status_code=404,
                detail=f"File not found in GCS: gs://{bucket_name}/{file_path}"
            )
        
        # Download and parse JSON
        content = blob.download_as_text()
        companies = json.loads(content)
        
        # Validate it's a list
        if not isinstance(companies, list):
            raise HTTPException(
                status_code=500,
                detail="Invalid data format: expected a list of companies"
            )
        
        return companies
        
    except Exception as e:
        # Check if it's a NotFound exception by checking error message/type
        error_str = str(e).lower()
        if 'not found' in error_str or '404' in error_str:
            raise HTTPException(
                status_code=404,
                detail=f"GCS bucket or file not found: gs://{bucket_name}/{file_path}"
            )
        elif isinstance(e, HTTPException):
            # Re-raise HTTP exceptions
            raise
        elif isinstance(e, json.JSONDecodeError):
            raise HTTPException(
                status_code=500,
                detail=f"Invalid JSON in GCS file: {str(e)}"
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load companies from GCS: {str(e)}"
            )

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
        # Check if we should use GCS (production) or local file (development)
        if os.getenv("GCS_BUCKET_NAME"):
            companies = load_companies_from_gcs()
        else:
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