from fastapi import FastAPI, HTTPException   # pyright: ignore[reportMissingImports]
from fastapi.middleware.cors import CORSMiddleware # pyright: ignore[reportMissingImports]
from pathlib import Path
import json
from .structured_pipeline import load_payload
from .rag_pipeline import retrieve_context

app = FastAPI(title="PE Dashboard API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/companies")
def list_companies():
    seed_path = DATA_DIR / "forbes_ai50_seed.json"
    if seed_path.exists():
        return json.loads(seed_path.read_text())
    return []

@app.post("/dashboard/structured")
def dashboard_structured(company_id: str = "00000000-0000-0000-0000-000000000000"):
    payload = load_payload(company_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Payload not found")

    return {
        "markdown": (
            "## Company Overview\n"
            f"{payload.company_record.legal_name} ({payload.company_record.brand_name})\n\n"
            "## Business Model and GTM\nNot disclosed.\n\n"
            "## Funding & Investor Profile\nNot disclosed.\n\n"
            "## Growth Momentum\nNot disclosed.\n\n"
            "## Visibility & Market Sentiment\nNot disclosed.\n\n"
            "## Risks and Challenges\nNot disclosed.\n\n"
            "## Outlook\nNot disclosed.\n\n"
            "## Disclosure Gaps\n- Valuation not disclosed.\n"
        )
    }

@app.post("/dashboard/rag")
def dashboard_rag(company_name: str = "ExampleAI"):
    ctx = retrieve_context(company_name)
    return {
        "markdown": (
            f"## Company Overview\n{company_name} — generated from retrieved context.\n\n"
            "## Business Model and GTM\nNot disclosed.\n\n"
            "## Funding & Investor Profile\nNot disclosed.\n\n"
            "## Growth Momentum\nNot disclosed.\n\n"
            "## Visibility & Market Sentiment\nNot disclosed.\n\n"
            "## Risks and Challenges\nNot disclosed.\n\n"
            "## Outlook\nNot disclosed.\n\n"
            "## Disclosure Gaps\n- Not disclosed.\n"
        ),
        "retrieved": ctx
    }