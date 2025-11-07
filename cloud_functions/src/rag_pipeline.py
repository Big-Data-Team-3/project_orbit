from typing import List, Dict

def retrieve_context(company_name: str) -> List[Dict]:
    # TODO: replace with real retrieval from vector DB
    return [
        {
            "source_url": "https://example.ai/about",
            "text": f"{company_name} is an AI company providing automation tooling."
        }
    ]