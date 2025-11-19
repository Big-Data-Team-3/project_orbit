import os
from typing import List, Dict
from src.services.embeddings import PineconeStorage, Embeddings
from openai import OpenAI
from pathlib import Path
import dotenv

dotenv.load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
TOP_K = int(os.getenv("RAG_TOP_K", "10"))

# Initialize clients
openai_client = OpenAI(api_key=OPENAI_API_KEY)
embeddings_client = Embeddings()
pinecone_storage = PineconeStorage()


def retrieve_context(company_name: str, top_k: int = TOP_K) -> List[Dict]:
    """
    Retrieve relevant context from vector DB for a given company.
    
    Args:
        company_name: Name of the company to search for
        top_k: Number of top results to return
        
    Returns:
        List of dictionaries with 'text', 'source_path', and 'score' keys
    """
    # Create a query that searches for company information
    query_text = f"information about {company_name} company business model funding investors"
    
    # Generate embedding for the query
    query_embedding = embeddings_client.embed_text(query_text)
    
    # Query Pinecone - get more results to filter by company name
    all_results = pinecone_storage.query(
        embedding=query_embedding,
        top_k=top_k * 2  # Get more results to filter from
    )
    
    # Filter results by company name in source_path (case-insensitive)
    company_name_lower = company_name.lower()
    filtered_results = [
        result for result in all_results
        if company_name_lower in result.get("source_path", "").lower()
    ]
    
    # If we have filtered results, use them; otherwise use all results
    if filtered_results:
        return filtered_results[:top_k]
    else:
        # If no company-specific results, return top results anyway
        return all_results[:top_k]


def load_system_prompt() -> str:
    """Load the system prompt from dashboard_system.md"""
    prompt_path = Path(__file__).parent / "prompts" / "dashboard_system.md"
    with open(prompt_path, "r") as f:
        return f.read()


def format_context_for_llm(contexts: List[Dict]) -> str:
    """Format retrieved contexts into a string for LLM input"""
    formatted_contexts = []
    for i, ctx in enumerate(contexts, 1):
        source = ctx.get("source_path", "Unknown source")
        text = ctx.get("text", "")
        formatted_contexts.append(f"[Source {i}: {source}]\n{text}\n")
    return "\n".join(formatted_contexts)


def generate_dashboard(company_name: str) -> str:
    """
    Generate an investor-facing diligence dashboard using RAG.
    
    Args:
        company_name: Name of the company to generate dashboard for
        
    Returns:
        Markdown formatted dashboard with all 8 required sections
    """
    # Step 1: Retrieve relevant context from vector DB
    contexts = retrieve_context(company_name, top_k=TOP_K)
    
    if not contexts:
        return f"## Error\n\nNo information found for {company_name} in the vector database."
    
    # Step 2: Format context for LLM
    context_text = format_context_for_llm(contexts)
    
    # Step 3: Load system prompt
    system_prompt = load_system_prompt()
    
    # Step 4: Create user prompt with context
    user_prompt = f"""Generate a comprehensive investor-facing diligence dashboard for {company_name}.

Use ONLY the information provided in the context below. If something is unknown or not disclosed, literally say "Not disclosed."

Context:
{context_text}

IMPORTANT: You MUST include all 8 sections in this exact order:
1. ## Company Overview
2. ## Business Model and GTM
3. ## Funding & Investor Profile
4. ## Growth Momentum
5. ## Visibility & Market Sentiment
6. ## Risks and Challenges
7. ## Outlook
8. ## Disclosure Gaps

Do not include any sections beyond these 8. If you cannot find information for a section, write "Not disclosed." for that section."""
    
    # Step 5: Call LLM with retry logic
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = openai_client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,  # Lower temperature for more consistent, factual output
                max_tokens=4000
            )
            
            dashboard = response.choices[0].message.content
            
            # Validate that all required sections are present
            required_sections = [
                "## Company Overview",
                "## Business Model and GTM",
                "## Funding & Investor Profile",
                "## Growth Momentum",
                "## Visibility & Market Sentiment",
                "## Risks and Challenges",
                "## Outlook",
                "## Disclosure Gaps"
            ]
            
            missing_sections = []
            for section in required_sections:
                if section not in dashboard:
                    missing_sections.append(section)
            
            if missing_sections:
                # If sections are missing, add them with "Not disclosed."
                dashboard += "\n\n"
                for section in missing_sections:
                    dashboard += f"\n{section}\n\nNot disclosed.\n"
            
            return dashboard
            
        except Exception as e:
            if attempt == max_retries - 1:
                raise Exception(f"Failed to generate dashboard after {max_retries} attempts: {str(e)}")
            continue
    
    raise Exception("Failed to generate dashboard")

if __name__ == "__main__":
    # Test with a company name (e.g., "abridge" or "anthropic")
    company_name = "abridge"  # Change this to test different companies
    
    print("=" * 80)
    print(f"Generating dashboard for: {company_name}")
    print("=" * 80)
    
    try:
        dashboard = generate_dashboard(company_name)
        print("\n" + dashboard)
        print("\n" + "=" * 80)
        print("✅ Dashboard generated successfully!")
    except Exception as e:
        print(f"\n❌ Error: {e}")