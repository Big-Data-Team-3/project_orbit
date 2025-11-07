from pathlib import Path
from typing import Optional
from .models import Payload

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "payloads"

def load_payload(company_id: str) -> Optional[Payload]:
    fp = DATA_DIR / f"{company_id}.json"
    if not fp.exists():
        # fallback to starter
        starter = Path(__file__).resolve().parents[1] / "data" / "starter_payload.json"
        return Payload.model_validate_json(starter.read_text())
    return Payload.model_validate_json(fp.read_text())