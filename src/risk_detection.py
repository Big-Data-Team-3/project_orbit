"""
Risk Detection Module for Assignment 5

Detects and reports high-risk events like layoffs, security breaches, etc.
"""
import os
import json
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path
from src.services.embeddings import Embeddings, PineconeStorage
import dotenv

dotenv.load_dotenv()

# Initialize services
embeddings_client = Embeddings()
pinecone_storage = PineconeStorage()

# Risk keywords for detection
RISK_KEYWORDS = {
    "layoff": [
        "layoff", "layoffs", "lay off", "firing", "fired", "termination",
        "workforce reduction", "job cuts", "downsizing", "restructuring",
        "redundancy", "let go", "dismissed", "mass layoff"
    ],
    "security_breach": [
        "breach", "data breach", "security breach", "hack", "hacked",
        "cyber attack", "ransomware", "data leak", "compromised",
        "unauthorized access", "security incident"
    ],
    "financial": [
        "bankruptcy", "insolvency", "liquidation", "financial distress",
        "going concern", "default", "debt crisis"
    ],
    "regulatory": [
        "investigation", "lawsuit", "litigation", "regulatory action",
        "fined", "penalty", "compliance violation", "SEC investigation"
    ],
    "operational": [
        "shutdown", "closure", "discontinued", "service outage",
        "major outage", "system failure"
    ]
}


def detect_risk_signals(text: str, risk_type: Optional[str] = None) -> List[Dict]:
    """
    Detect risk signals in text content.
    
    Args:
        text: Text content to analyze
        risk_type: Specific risk type to look for (optional)
        
    Returns:
        List of detected risk signals with type and context
    """
    text_lower = text.lower()
    detected_risks = []
    
    # If specific risk type requested, only check that
    risk_types_to_check = [risk_type] if risk_type else RISK_KEYWORDS.keys()
    
    for r_type in risk_types_to_check:
        keywords = RISK_KEYWORDS.get(r_type, [])
        for keyword in keywords:
            if keyword in text_lower:
                # Find context around the keyword
                keyword_index = text_lower.find(keyword)
                start = max(0, keyword_index - 100)
                end = min(len(text), keyword_index + len(keyword) + 100)
                context = text[start:end].strip()
                
                detected_risks.append({
                    "risk_type": r_type,
                    "keyword": keyword,
                    "context": context,
                    "severity": "high" if r_type in ["layoff", "security_breach", "financial"] else "medium"
                })
                break  # Only report once per risk type per text
    
    return detected_risks


def report_layoff_signal(signal_data: Dict) -> Dict:
    """
    Log or flag high-risk layoff events.
    
    This is one of the core tools for Assignment 5 - Lab 12.
    
    Args:
        signal_data: Dictionary containing:
            - company_id: Company identifier
            - source_path: Where the signal was found
            - text: The text containing the signal
            - context: Context around the signal
            - detected_at: Timestamp of detection
            
    Returns:
        Dictionary with report status and details
        
    Example:
        >>> signal = {
        ...     "company_id": "anthropic",
        ...     "source_path": "anthropic/news",
        ...     "text": "Company announces layoff of 10% workforce",
        ...     "context": "...",
        ...     "detected_at": "2025-11-14T10:00:00Z"
        ... }
        >>> report = report_layoff_signal(signal)
        >>> print(report["status"])
    """
    # Create risk report
    report = {
        "status": "flagged",
        "risk_type": "layoff",
        "company_id": signal_data.get("company_id"),
        "source_path": signal_data.get("source_path"),
        "detected_at": signal_data.get("detected_at", datetime.now().isoformat()),
        "context": signal_data.get("context", signal_data.get("text", "")[:500]),
        "severity": "high",
        "action_required": True
    }
    
    # Log the risk (in production, this would go to a logging system)
    log_entry = {
        "timestamp": report["detected_at"],
        "event": "risk_detected",
        "risk_type": "layoff",
        "company_id": report["company_id"],
        "severity": "high",
        "source": report["source_path"]
    }
    
    # Save to risk log file
    risk_log_path = Path("data/risk_logs.jsonl")
    risk_log_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(risk_log_path, "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    
    print(f"🚨 RISK DETECTED: {report['risk_type'].upper()} for {report['company_id']}")
    print(f"   Source: {report['source_path']}")
    print(f"   Context: {report['context'][:200]}...")
    
    return report


def search_risks_in_company(company_id: str, risk_type: Optional[str] = None) -> List[Dict]:
    """
    Search for risk signals in a company's vector DB content.
    
    Args:
        company_id: Company identifier
        risk_type: Specific risk type to search for (optional)
        
    Returns:
        List of detected risk signals (empty list if none found)
    """
    try:
        print(f"🔍 [risk_detection] Starting risk search for company_id='{company_id}', risk_type='{risk_type}'")
        
        # Search for risk-related content
        if risk_type:
            query = f"{risk_type} risk"
        else:
            query = "layoff security breach risk"
        
        print(f"🔍 [risk_detection] Query: '{query}'")
        
        # Use RAG to find relevant content
        from src.rag_search import rag_search_company
        print(f"🔍 [risk_detection] Calling rag_search_company(company_id='{company_id}', query='{query}', top_k=20)")
        
        results = rag_search_company(company_id, query, top_k=20)
        print(f"🔍 [risk_detection] Retrieved {len(results)} results from rag_search_company")
        
        all_risks = []
        for i, result in enumerate(results, 1):
            text = result.get("text", "")
            if not text:
                continue
            
            print(f"🔍 [risk_detection] Processing result {i}/{len(results)}: {len(text)} chars")
            risks = detect_risk_signals(text, risk_type)
            
            if risks:
                print(f"🔍 [risk_detection] Found {len(risks)} risk signals in result {i}")
            
            for risk in risks:
                risk["source_path"] = result.get("source_path")
                risk["score"] = result.get("score", 0)
                all_risks.append(risk)
        
        print(f"🔍 [risk_detection] Total risks found (before deduplication): {len(all_risks)}")
        
        # Remove duplicates (same risk type from same source)
        seen = set()
        unique_risks = []
        for risk in all_risks:
            key = (risk.get("risk_type"), risk.get("source_path"))
            if key not in seen:
                seen.add(key)
                unique_risks.append(risk)
        
        print(f"🔍 [risk_detection] Unique risks after deduplication: {len(unique_risks)}")
        print(f"🔍 [risk_detection] Returning {len(unique_risks)} unique risks")
        
        return unique_risks
        
    except Exception as e:
        print(f"❌ [risk_detection] Error in search_risks_in_company: {e}")
        import traceback
        traceback.print_exc()
        return []  # Return empty list on error


if __name__ == "__main__":
    # Test risk detection
    print("="*80)
    print("🧪 Testing Risk Detection")
    print("="*80)
    
    test_company = "anthropic"
    print(f"Searching for risks in: {test_company}")
    
    risks = search_risks_in_company(test_company, "security")
    
    if risks:
        print(f"\n🚨 Found {len(risks)} risk signals:")
        for i, risk in enumerate(risks, 1):
            print(f"\n{i}. {risk['risk_type'].upper()} (Severity: {risk['severity']})")
            print(f"   Source: {risk['source_path']}")
            print(f"   Context: {risk['context'][:200]}...")
    else:
        print("\n✅ No risk signals detected")
    
    print("="*80)

