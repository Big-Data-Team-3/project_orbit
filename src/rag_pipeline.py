import os
import logging
from typing import List, Dict, Optional
from src.services.embeddings import PineconeStorage, Embeddings
from openai import OpenAI
from pathlib import Path
import dotenv

dotenv.load_dotenv()

# Initialize logging
logger = logging.getLogger(__name__)

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
    logger.info(f"🔍 Retrieving context for company identifier: '{company_name}' (top_k={top_k})")
    
    # Create a query that searches for company information
    query_text = f"information about {company_name} company business model funding investors"
    logger.debug(f"   Query text: '{query_text}'")
    
    # Generate embedding for the query
    query_embedding = embeddings_client.embed_text(query_text)
    
    # Query Pinecone - get more results to filter by company name
    all_results = pinecone_storage.query(
        embedding=query_embedding,
        top_k=top_k * 2  # Get more results to filter from
    )
    logger.info(f"   📊 Retrieved {len(all_results)} total results from vector DB")
    
    # Filter results by company name in source_path (case-insensitive)
    company_name_lower = company_name.lower()
    filtered_results = [
        result for result in all_results
        if company_name_lower in result.get("source_path", "").lower()
    ]
    
    # Log source_paths found in results
    if all_results:
        source_paths = [r.get("source_path", "unknown") for r in all_results[:5]]
        logger.info(f"   📁 Sample source_paths from results: {source_paths}")
    
    # If we have filtered results, use them; otherwise use all results
    if filtered_results:
        logger.info(f"   ✅ Found {len(filtered_results)} results matching '{company_name_lower}' in source_path")
        logger.info(f"   📋 Returning top {min(top_k, len(filtered_results))} filtered results")
        return filtered_results[:top_k]
    else:
        # If no company-specific results, return top results anyway
        logger.warning(f"   ⚠️  No results found matching '{company_name_lower}' in source_path")
        logger.warning(f"   ⚠️  Falling back to top {top_k} results (may contain wrong company data)")
        if all_results:
            fallback_sources = [r.get("source_path", "unknown") for r in all_results[:top_k]]
            logger.warning(f"   ⚠️  Fallback results from: {fallback_sources}")
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


def generate_dashboard(company_identifier: str, company_display_name: Optional[str] = None) -> str:
    """
    Generate an investor-facing diligence dashboard using RAG.
    
    Args:
        company_identifier: Company ID or name to use for vector DB lookup (e.g., "anthropic", "abridge")
        company_display_name: Optional display name for the LLM prompt (e.g., "Anthropic"). 
                              If not provided, uses company_identifier.
        
    Returns:
        Markdown formatted dashboard with all 8 required sections
    """
    # Use display name for LLM, but identifier for vector DB lookup
    display_name = company_display_name or company_identifier
    
    logger.info(f"🚀 Starting dashboard generation")
    logger.info(f"   Company Identifier (for vector DB): '{company_identifier}'")
    logger.info(f"   Company Display Name (for LLM): '{display_name}'")
    
    # Step 1: Retrieve relevant context from vector DB using company_identifier
    # This should match the source_path format (e.g., "anthropic/homepage")
    logger.info(f"📥 Step 1: Retrieving context from vector DB for '{company_identifier}'")
    contexts = retrieve_context(company_identifier, top_k=TOP_K)
    
    if not contexts:
        logger.error(f"❌ No contexts found for '{company_identifier}'")
        return f"## Error\n\nNo information found for {display_name} in the vector database."
    
    # Log which companies' data was actually retrieved
    source_paths = [ctx.get("source_path", "unknown") for ctx in contexts]
    unique_companies = set()
    for path in source_paths:
        # Extract company from source_path (e.g., "anthropic/homepage" -> "anthropic")
        if "/" in path:
            company = path.split("/")[0].lower()
            unique_companies.add(company)
    
    logger.info(f"   ✅ Retrieved {len(contexts)} contexts")
    logger.info(f"   📁 Source paths: {source_paths[:3]}..." if len(source_paths) > 3 else f"   📁 Source paths: {source_paths}")
    logger.info(f"   🏢 Companies found in results: {sorted(unique_companies)}")
    
    # Verify we got the right company
    expected_company = company_identifier.lower()
    if unique_companies and expected_company not in unique_companies:
        logger.warning(f"   ⚠️  WARNING: Expected company '{expected_company}' but found: {sorted(unique_companies)}")
    else:
        logger.info(f"   ✅ Verified: Found expected company '{expected_company}' in results")
    
    # Step 2: Format context for LLM
    logger.info(f"📝 Step 2: Formatting {len(contexts)} contexts for LLM")
    context_text = format_context_for_llm(contexts)
    
    # Step 3: Load system prompt
    logger.info(f"📄 Step 3: Loading system prompt")
    system_prompt = load_system_prompt()
    
    # Step 4: Create user prompt with context (use display name for better LLM output)
    logger.info(f"💬 Step 4: Creating LLM prompt for '{display_name}'")
    user_prompt = f"""Generate a comprehensive investor-facing diligence dashboard for {display_name}.

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
    logger.info(f"🤖 Step 5: Calling LLM (model: {LLM_MODEL}) to generate dashboard for '{display_name}'")
    max_retries = 3
    for attempt in range(max_retries):
        try:
            logger.debug(f"   Attempt {attempt + 1}/{max_retries}")
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
            logger.info(f"   ✅ LLM response received ({len(dashboard)} characters)")
            
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
                logger.warning(f"   ⚠️  Missing sections: {missing_sections}, adding them")
                # If sections are missing, add them with "Not disclosed."
                dashboard += "\n\n"
                for section in missing_sections:
                    dashboard += f"\n{section}\n\nNot disclosed.\n"
            else:
                logger.info(f"   ✅ All 8 required sections present in dashboard")
            
            # Verify dashboard mentions the correct company
            dashboard_lower = dashboard.lower()
            display_name_lower = display_name.lower()
            identifier_lower = company_identifier.lower()
            
            if display_name_lower in dashboard_lower or identifier_lower in dashboard_lower:
                logger.info(f"   ✅ Dashboard contains references to '{display_name}' or '{company_identifier}'")
            else:
                logger.warning(f"   ⚠️  Dashboard may not contain expected company name '{display_name}'")
            
            logger.info(f"🎉 Dashboard generation completed successfully for '{display_name}'")
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