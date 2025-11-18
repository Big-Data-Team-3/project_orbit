"""
RAG Search Module for Assignment 5

Provides functions to query the Vector DB for contextual snippets.
"""
import os
from typing import List, Dict, Optional
from services.embeddings import Embeddings, PineconeStorage
from pathlib import Path
import dotenv

dotenv.load_dotenv()

# Initialize services
embeddings_client = Embeddings()
pinecone_storage = PineconeStorage()


def rag_search_company(company_id: str, query: str, top_k: int = 10) -> List[Dict]:
    """
    Query the Vector DB for contextual snippets about a company.
    
    This is one of the core tools for Assignment 5 - Lab 12.
    
    Args:
        company_id: Company identifier (e.g., "anthropic", "baseten")
        query: Search query string
        top_k: Number of top results to return (default: 10)
        
    Returns:
        List of dictionaries with keys:
            - text: The chunk text
            - source_path: Path to source (e.g., "anthropic/homepage")
            - score: Similarity score (0-1)
    
    Example:
        >>> results = rag_search_company("anthropic", "funding rounds investors")
        >>> for result in results:
        ...     print(f"{result['score']:.3f}: {result['text'][:100]}...")
    """
    # Create enhanced query with company context
    enhanced_query = f"{company_id} {query}"
    
    # Generate embedding for the query
    query_embedding = embeddings_client.embed_text(enhanced_query)
    
    # Query Pinecone with company filter
    filter_dict = {
        "source_path": {"$regex": f"^{company_id}/"}
    }
    
    try:
        results = pinecone_storage.query(
            embedding=query_embedding,
            top_k=top_k * 2,  # Get more to filter
            filter_dict=filter_dict
        )
        
        # If filtered results are empty, try without filter
        if not results:
            results = pinecone_storage.query(
                embedding=query_embedding,
                top_k=top_k
            )
            # Filter by company name in source_path manually
            company_results = [
                r for r in results 
                if company_id.lower() in r.get("source_path", "").lower()
            ]
            if company_results:
                results = company_results[:top_k]
        
        return results[:top_k]
        
    except Exception as e:
        print(f"⚠️  Error querying vector DB: {e}")
        return []


def format_context_snippets(results: List[Dict], max_snippets: int = 5) -> str:
    """
    Format RAG search results into a readable context string.
    
    Args:
        results: List of result dictionaries from rag_search_company
        max_snippets: Maximum number of snippets to include
        
    Returns:
        Formatted string with context snippets
    """
    if not results:
        return "No relevant context found."
    
    formatted = []
    for i, result in enumerate(results[:max_snippets], 1):
        score = result.get('score', 0)
        text = result.get('text', '')
        source = result.get('source_path', 'unknown')
        
        # Truncate long text
        if len(text) > 500:
            text = text[:500] + "..."
        
        formatted.append(
            f"[Snippet {i} | Score: {score:.3f} | Source: {source}]\n{text}\n"
        )
    
    return "\n---\n".join(formatted)


if __name__ == "__main__":
    # Test the RAG search
    print("="*80)
    print("🧪 Testing RAG Search")
    print("="*80)
    
    test_company = "anthropic"
    test_query = "funding rounds investors valuation"
    
    print(f"Company: {test_company}")
    print(f"Query: {test_query}")
    print("\nSearching...")
    
    results = rag_search_company(test_company, test_query, top_k=5)
    
    print(f"\nFound {len(results)} results:")
    print(format_context_snippets(results, max_snippets=5))
    
    print("="*80)

