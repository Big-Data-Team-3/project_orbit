 # Unit tests for each tool using pytest and also implemented in Github CI

# region imports
import pytest
from src.agents.tools import get_latest_structured_payload, rag_search_company, report_layoff_signal
from src.agents.models import RiskSignal
from datetime import datetime
# endregion

# region tests
@pytest.mark.asyncio
async def test_get_latest_structured_payload():
    result = await get_latest_structured_payload("abridge")
    assert result is not None
    assert result.company_id == "abridge"
    
    result = await get_latest_structured_payload("anthropic")
    assert result is not None

@pytest.mark.asyncio
async def test_rag_search_company():
    result = await rag_search_company("abridge", "funding rounds", top_k=5)
    assert result is not None
    assert result.company_id == "abridge"
    assert result.query == "funding rounds"

@pytest.mark.asyncio
async def test_report_layoff_signal():
    signal = RiskSignal(
        company_id="abridge",
        event_type="layoff",
        description="Test layoff event",
        severity="high",
        detected_at=datetime.now()
    )
    result = await report_layoff_signal(signal)
    assert result is not None
    assert result.signal_id != ""
    assert result.status in ["logged", "flagged", "escalated"]
# endregion