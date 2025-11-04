def score_dashboard(factual: int, schema: int, provenance: int, hallucination: int, readability: int) -> int:
    return factual + schema + provenance + hallucination + readability