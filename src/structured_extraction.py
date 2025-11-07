"""
Lab 5: Dynamic Structured Extraction with Pydantic + Instructor

✅ Uses PYDANTIC models for type validation
✅ Uses INSTRUCTOR for structured extraction with retry
✅ Zero hardcoding - searches ALL sources
✅ Zero hallucination - validates with Pydantic + post-processing

IMPROVEMENTS IN THIS VERSION:
✅ is_website_section() - Filters fake products (website pages)
✅ extract_founded_year_aggressive() - Better year detection
✅ Unique event IDs with full dates (YYYY_MM_DD)
✅ Stricter leadership cross-validation
✅ Timeline-only event extraction
"""

import json
import os
import re
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, date

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import instructor
from openai import OpenAI
from bs4 import BeautifulSoup
from pydantic import ValidationError 

try:
    from models import (
        Company, Event, Snapshot, Product, Leadership, Visibility,
        Provenance, Payload
    )
except ImportError:
    from src.models import (
        Company, Event, Snapshot, Product, Leadership, Visibility,
        Provenance, Payload
    )
try:
    from google.cloud import storage
    try:
        from google.oauth2 import service_account
    except ImportError:
        service_account = None
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    storage = None
    service_account = None
    print("⚠️  Google Cloud Storage not available. Install with: pip install google-cloud-storage google-auth")

storage_client = None

def get_storage_client():
    """Get or create GCS storage client (similar to api.py)"""
    global storage_client
    
    if storage_client is not None:
        return storage_client
    
    bucket_name = os.getenv("GCS_BUCKET_NAME")
    if not bucket_name:
        return None
    
    if not GCS_AVAILABLE:
        print("⚠️  GCS_BUCKET_NAME is set but google-cloud-storage is not installed")
        return None
    
    try:
        project_id = os.getenv("PROJECT_ID")
        PROJECT_ROOT = Path(__file__).parent.parent
        credentials_path = PROJECT_ROOT / "config" / "gcp.json"
        
        if credentials_path.exists():
            if service_account is None:
                print("⚠️  service_account not available, cannot use credentials file")
                return None
            credentials = service_account.Credentials.from_service_account_file(
                str(credentials_path)
            )
            storage_client = storage.Client(project=project_id, credentials=credentials)
            print(f"✅ GCS client initialized with credentials from {credentials_path}")
        else:
            # Use Application Default Credentials (production/Cloud Run)
            storage_client = storage.Client(project=project_id)
            print("✅ GCS client initialized with Application Default Credentials")
        
        return storage_client
    except Exception as e:
        print(f"⚠️  Failed to initialize GCS client: {e}")
        return None

# Initialize Instructor client
api_key = os.getenv("OPENAI_API_KEY")
model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
client = instructor.from_openai(OpenAI(api_key=api_key))
print(f"✅ Instructor client initialized with model: {model_name}")
print(f"✅ Using Pydantic models for validation")


# ============================================================================
# VALIDATION HELPERS
# ============================================================================

def is_placeholder_name(name: str) -> bool:
    """Check if name is a placeholder."""
    if not name:
        return True
    
    placeholder_names = {
        'john doe', 'jane doe', 'john smith', 'jane smith',
        'unknown', 'test user', 'example user', 'placeholder',
        'anonymous', 'unnamed', 'tbd', 'tba', 'n/a', 'na',
        'ceo', 'cto', 'cfo', 'coo', 'founder', 'executive'
    }
    
    name_lower = name.lower().strip()
    
    if name_lower in placeholder_names:
        return True
    
    placeholder_patterns = [
        r'^john\s+doe',
        r'^jane\s+doe',
        r'^john\s+smith',
        r'^jane\s+smith',
        r'^test\s+',
        r'^example\s+',
        r'^sample\s+',
        r'^dummy\s+'
    ]
    
    for pattern in placeholder_patterns:
        if re.match(pattern, name_lower):
            return True
    
    return False


def is_website_section(name: str) -> bool:
    """
    NEW: Check if 'product' name is actually a website section.
    
    Filters out common false positives like:
    - Website pages: "Blog", "Press Kit", "Newsroom"
    - Legal docs: "Terms and Privacy", "Updates to Policy"
    - Initiatives: "Advisory Council", "Economic Program"
    - Partnerships: "MOU with Government"
    """
    if not name:
        return True
    
    website_sections = {
        'blog', 'videos', 'press kit', 'company', 'newsroom', 'press',
        'careers', 'about', 'contact', 'team', 'investors', 'customers',
        'partners', 'pricing', 'news', 'resources', 'insights', 'events',
        'webinars', 'documentation', 'docs', 'support', 'help center',
        'terms', 'privacy', 'policy', 'legal', 'security', 'compliance',
        'customer info', 'case studies', 'success stories'
    }
    
    name_lower = name.lower().strip()
    
    if name_lower in website_sections:
        return True
    
    # Pattern-based exclusions
    non_product_patterns = [
        r'^updates?\s+to\s+',  # "Updates to Terms"
        r'^signs?\s+',  # "Signs MOU"
        r'^mou\s+with\s+',  # "MOU with UK Government"
        r'^expanding\s+',  # "Expanding Google Cloud TPUs"
        r'^announces?\s+',  # "Announces Partnership"
        r'advisory\s+council',  # "Economic Advisory Council"
        r'futures?\s+program',  # "Economic Futures Program"
        r'program$',  # Ends with "Program" (usually initiatives)
    ]
    
    for pattern in non_product_patterns:
        if re.search(pattern, name_lower):
            return True
    
    return False


def is_valid_full_name(name: str) -> bool:
    """Check if name is a valid full name (First Last)."""
    if not name:
        return False
    
    if ' ' not in name:
        return False
    
    role_words = ['ceo', 'cto', 'cfo', 'chief', 'officer', 'president']
    if any(word in name.lower() for word in role_words):
        return False
    
    return True


def is_placeholder_date(date_value: Any) -> bool:
    """Check if date is a placeholder."""
    if not date_value:
        return False
    
    date_str = str(date_value)
    return 'XX' in date_str or 'xx' in date_str


def normalize_url(url: str, prefix: str = 'https://') -> Optional[str]:
    """Normalize URL (add https:// if missing)."""
    if not url:
        return None
    
    url = url.strip()
    
    if not url.startswith('http://') and not url.startswith('https://'):
        url = prefix + url
    
    return url


def create_provenance(sources: Dict[str, Any], page_types: List[str], 
                     snippet: Optional[str] = None) -> List[Provenance]:
    """Create Provenance objects from metadata."""
    provenance_list = []
    url_mapping = sources.get('url_mapping', {})
    
    for page_type in page_types:
        if page_type in url_mapping:
            url_info = url_mapping[page_type]
            try:
                prov = Provenance(
                    source_url=url_info['source_url'],
                    crawled_at=url_info['crawled_at'],
                    snippet=snippet[:500] if snippet else None
                )
                provenance_list.append(prov)
            except Exception as e:
                print(f"   ⚠️  Failed to create provenance for {page_type}: {e}")
    
    if not provenance_list and sources.get('metadata'):
        metadata = sources['metadata']
        try:
            scrape_ts = metadata.get('scrape_timestamp', datetime.now().isoformat())
            prov = Provenance(
                source_url="https://internal/metadata.json",
                crawled_at=scrape_ts,
                snippet=snippet[:500] if snippet else None
            )
            provenance_list.append(prov)
        except:
            pass
    
    return provenance_list


def extract_founded_year_aggressive(sources: Dict[str, Any]) -> Optional[int]:
    """
    NEW: Aggressively search ALL text content for founding year.
    
    Searches through:
    - All text files
    - All blog posts
    - Using patterns: "founded in", "established in", "since", etc.
    """
    all_text = ""
    
    # Combine ALL text files
    for file_name, file_data in sources.get('files', {}).items():
        all_text += file_data['content'] + "\n\n"
    
    # Add ALL blog posts
    for blog in sources.get('blog_posts', []):
        all_text += blog['content'] + "\n\n"
    
    # Search for founding mentions
    founding_patterns = [
        r'founded\s+in\s+(\d{4})',
        r'established\s+in\s+(\d{4})',
        r'started\s+in\s+(\d{4})',
        r'since\s+(\d{4})',
        r'began\s+in\s+(\d{4})',
        r'launched\s+in\s+(\d{4})',
        r'inception\s+in\s+(\d{4})',
        r'created\s+in\s+(\d{4})'
    ]
    
    for pattern in founding_patterns:
        match = re.search(pattern, all_text.lower())
        if match:
            year = int(match.group(1))
            if 2000 <= year <= 2023:
                print(f"   ✓ Found in text: founded {year}")
                return year
    
    return None


# ============================================================================
# FIELD KEYWORDS - COMPREHENSIVE
# ============================================================================

FIELD_KEYWORDS = {
    'legal_name': ['company', 'incorporated', 'inc', 'llc', 'ltd', 'corp'],
    'founded_year': ['founded', 'established', 'since', 'started', 'began', 'inception'],
    'hq_city': ['headquarters', 'based in', 'located in', 'office', 'hq'],
    'website': ['website', 'visit', 'learn more', 'contact'],
    'categories': ['industry', 'sector', 'focus', 'specializes', 'provides'],
    'related_companies': ['competitor', 'similar', 'alternative', 'compared to', 'vs'],
    'funding': ['raises', 'raised', 'funding', 'series', 'round', 'investment', 'capital', 'valuation', 'investors', 'led by'],
    'investors': ['investor', 'led by', 'backed by', 'participated', 'venture'],
    'founders': ['founder', 'co-founder', 'founded by', 'started by', 'ceo and founder'],
    'executives': ['ceo', 'cto', 'cfo', 'coo', 'chief', 'officer', 'president', 'joins as', 'appointed', 'leadership'],
    'linkedin': ['linkedin.com', 'linkedin profile'],
    'products': ['product', 'platform', 'solution', 'offering', 'service', 'introducing', 'launches', 'release'],
    'pricing': ['pricing', 'price', 'tier', 'plan', 'subscription', 'cost', 'free', 'enterprise'],
    'integrations': ['integrates', 'integration', 'partners with', 'works with', 'compatible'],
    'github': ['github.com', 'github repository', 'open source', 'source code'],
    'license': ['license', 'mit', 'apache', 'gpl', 'bsd', 'open source'],
    'customers': ['customer', 'client', 'uses', 'deployed', 'case study'],
    'hiring': ['hiring', 'careers', 'jobs', 'positions', 'roles', 'join', 'openings'],
    'headcount': ['employees', 'team size', 'headcount', 'people', 'staff'],
    'offices': ['office', 'location', 'expands', 'opens', 'headquarters'],
    'partnerships': ['partnership', 'partners with', 'teams up', 'collaboration', 'announces'],
    'launches': ['launches', 'introducing', 'announces', 'unveils', 'releases'],
    'mna': ['acquires', 'acquisition', 'merger', 'acquired by', 'merges'],
    'integration': ['integrates with', 'integration with', 'now available'],
    'customer_win': ['signs', 'contract', 'major customer', 'enterprise deal'],
    'regulatory': ['compliance', 'certification', 'soc2', 'hipaa', 'gdpr', 'regulatory'],
    'security_incident': ['breach', 'security incident', 'vulnerability', 'attack'],
    'pricing_change': ['price change', 'pricing update', 'new pricing'],
    'layoff': ['layoff', 'downsizing', 'reducing headcount', 'restructuring'],
    'hiring_spike': ['rapid hiring', 'hiring surge', 'expanding team'],
    'office_open': ['opens office', 'new office', 'expands to'],
    'office_close': ['closes office', 'shutting down', 'consolidating'],
    'benchmark': ['benchmark', 'performance', 'evaluation', 'test results'],
    'open_source': ['open source', 'releases on github', 'available on github'],
    'contract_award': ['awarded contract', 'wins contract', 'government contract'],
    'github_stars': ['github stars', 'github repository', 'open source'],
    'glassdoor': ['glassdoor', 'employee rating', 'workplace rating'],
}


# ============================================================================
# HTML & JSON-LD PARSING
# ============================================================================

def extract_jsonld_item(item: Dict[str, Any], jsonld_data: Dict[str, Any]):
    """Helper to extract data from a single JSON-LD item."""
    item_type = item.get('@type')
    
    if item_type == 'Organization':
        jsonld_data.update({
            'name': item.get('name'),
            'legalName': item.get('legalName'),
            'foundingDate': item.get('foundingDate'),
            'url': item.get('url'),
            'address': item.get('address'),
            'description': item.get('description'),
            'numberOfEmployees': item.get('numberOfEmployees')
        })
    
    elif item_type == 'Product':
        if 'products' not in jsonld_data:
            jsonld_data['products'] = []
        jsonld_data['products'].append({
            'name': item.get('name'),
            'description': item.get('description'),
            'offers': item.get('offers')
        })
    
    elif item_type == 'Person':
        if 'people' not in jsonld_data:
            jsonld_data['people'] = []
        jsonld_data['people'].append({
            'name': item.get('name'),
            'jobTitle': item.get('jobTitle'),
            'worksFor': item.get('worksFor'),
            'sameAs': item.get('sameAs')
        })
    
    elif item_type == 'Event':
        if 'events' not in jsonld_data:
            jsonld_data['events'] = []
        jsonld_data['events'].append({
            'name': item.get('name'),
            'startDate': item.get('startDate'),
            'description': item.get('description')
        })


def extract_jsonld_data(html_content: str) -> Dict[str, Any]:
    """Extract JSON-LD structured data from HTML."""
    jsonld_data = {}
    
    try:
        soup = BeautifulSoup(html_content, 'lxml')
        jsonld_scripts = soup.find_all('script', type='application/ld+json')
        
        for script in jsonld_scripts:
            try:
                data = json.loads(script.string)
                
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            extract_jsonld_item(item, jsonld_data)
                elif isinstance(data, dict):
                    extract_jsonld_item(data, jsonld_data)
                
            except json.JSONDecodeError as e:
                print(f"   ⚠️  JSON-LD parse error: {str(e)[:50]}")
                continue
    
    except Exception as e:
        print(f"   ⚠️  JSON-LD extraction error: {str(e)[:50]}")
    
    return jsonld_data


def extract_structured_from_html(html_content: str) -> Dict[str, Any]:
    """Extract ALL structured data from HTML patterns."""
    structured = {}
    
    try:
        soup = BeautifulSoup(html_content, 'lxml')
        text = soup.get_text()
        
        # Team members
        team_members = []
        for member_div in soup.find_all(['div', 'article'], class_=lambda x: x and 'team' in x.lower() if x else False):
            name_tag = member_div.find(['h2', 'h3', 'h4', 'strong'])
            role_tag = member_div.find(class_=lambda x: x and 'role' in x.lower() if x else False)
            
            if name_tag:
                team_members.append({
                    'name': name_tag.get_text().strip(),
                    'role': role_tag.get_text().strip() if role_tag else None
                })
        
        if team_members:
            structured['team_members'] = team_members[:20]
        
        # Pricing tiers
        pricing_tiers = []
        for table in soup.find_all('table'):
            headers = [th.get_text().strip() for th in table.find_all('th')]
            if any(word in ' '.join(headers).lower() for word in ['price', 'plan', 'tier']):
                for row in table.find_all('tr')[1:]:
                    cells = [td.get_text().strip() for td in row.find_all('td')]
                    if cells:
                        pricing_tiers.append(cells[0])
        
        for div in soup.find_all('div', class_=lambda x: x and 'price' in x.lower() if x else False):
            tier_name = div.find(['h2', 'h3', 'h4'])
            if tier_name:
                pricing_tiers.append(tier_name.get_text().strip())
        
        if pricing_tiers:
            structured['pricing_tiers'] = list(set(pricing_tiers))[:10]
        
        # Office locations
        locations = []
        for address in soup.find_all('address'):
            address_text = address.get_text().strip()
            cities = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b', address_text)
            locations.extend(cities)
        
        if locations:
            structured['locations'] = list(set(locations))[:10]
        
        # Copyright years
        copyright_years = re.findall(r'©\s*(\d{4})', html_content)
        if copyright_years:
            years = [int(y) for y in copyright_years if 1990 <= int(y) <= 2023]
            if years:
                structured['copyright_years'] = sorted(set(years))
        
        # Headcount
        headcount_patterns = [
            r'(\d+)\+?\s+employees',
            r'team\s+of\s+(\d+)',
            r'(\d+)\s+people',
            r'headcount[:\s]+(\d+)'
        ]
        for pattern in headcount_patterns:
            match = re.search(pattern, text.lower())
            if match:
                try:
                    headcount = int(match.group(1))
                    if 10 <= headcount <= 100000:
                        structured['headcount'] = headcount
                        break
                except:
                    pass
        
        # GitHub repo URLs
        github_links = soup.find_all('a', href=lambda x: x and 'github.com' in x.lower() if x else False)
        if github_links:
            repos = []
            for link in github_links:
                href = link.get('href')
                if '/github.com/' in href and href.count('/') >= 4:
                    repos.append(href)
            if repos:
                structured['github_repos'] = list(set(repos))[:5]
        
        # Glassdoor rating
        glassdoor_patterns = [
            r'glassdoor[:\s]+(\d+\.?\d*)',
            r'(\d+\.?\d*)\s+(?:stars?|rating)\s+on\s+glassdoor',
            r'rated\s+(\d+\.?\d*)\s+on\s+glassdoor'
        ]
        for pattern in glassdoor_patterns:
            match = re.search(pattern, text.lower())
            if match:
                try:
                    rating = float(match.group(1))
                    if 0 <= rating <= 5:
                        structured['glassdoor_rating'] = rating
                        break
                except:
                    pass
        
        # Job opening counts
        job_patterns = [
            r'(\d+)\s+open\s+(?:positions|roles|jobs)',
            r'(\d+)\s+(?:positions|roles|jobs)\s+available',
            r'hiring\s+for\s+(\d+)\s+(?:positions|roles)'
        ]
        for pattern in job_patterns:
            match = re.search(pattern, text.lower())
            if match:
                try:
                    count = int(match.group(1))
                    if 1 <= count <= 1000:
                        structured['job_openings'] = count
                        break
                except:
                    pass
        
        # Engineering/sales openings
        eng_patterns = [
            r'(\d+)\s+engineering\s+(?:positions|roles|openings)',
            r'(\d+)\s+(?:software|backend|frontend|fullstack)\s+engineer'
        ]
        for pattern in eng_patterns:
            match = re.search(pattern, text.lower())
            if match:
                try:
                    structured['engineering_openings'] = int(match.group(1))
                    break
                except:
                    pass
        
        sales_patterns = [
            r'(\d+)\s+sales\s+(?:positions|roles|openings)',
            r'(\d+)\s+(?:account\s+executive|sales\s+rep)'
        ]
        for pattern in sales_patterns:
            match = re.search(pattern, text.lower())
            if match:
                try:
                    structured['sales_openings'] = int(match.group(1))
                    break
                except:
                    pass
    
    except Exception as e:
        print(f"   ⚠️  HTML parsing error: {str(e)[:50]}")
    
    return structured


def search_html_sources(sources: Dict[str, Any], keywords: List[str], max_chars: int = 5000) -> str:
    """Search through HTML files for relevant content."""
    relevant_content = []
    total_chars = 0
    
    for file_name, file_data in sources.get('html_files', {}).items():
        if total_chars >= max_chars:
            break
        
        html = file_data['content']
        
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()
            
            paragraphs = soup.find_all(['p', 'div', 'section', 'article'])
            
            for para in paragraphs:
                text = para.get_text().strip()
                if not text or len(text) < 50:
                    continue
                
                text_lower = text.lower()
                
                if any(kw.lower() in text_lower for kw in keywords):
                    snippet = ' '.join(text.split()[:200])
                    relevant_content.append(f"[{file_name.upper()} HTML]\n{snippet}\n")
                    total_chars += len(snippet)
                    
                    if total_chars >= max_chars:
                        break
        
        except Exception as e:
            continue
    
    return '\n---\n'.join(relevant_content)


# ============================================================================
# SOURCE LOADING - COMPREHENSIVE
# ============================================================================

def read_file_from_gcs(bucket_name: str, file_path: str) -> Optional[str]:
    """Read a file from GCS bucket"""
    try:
        client = get_storage_client()
        if not client:
            return None
        
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(file_path)
        
        if not blob.exists():
            return None
        
        return blob.download_as_text()
    except Exception as e:
        print(f"   ⚠️  Failed to read {file_path} from GCS: {e}")
        return None

def list_files_from_gcs(bucket_name: str, prefix: str) -> List[str]:
    """List files in GCS bucket with given prefix"""
    try:
        client = get_storage_client()
        if not client:
            return []
        
        bucket = client.bucket(bucket_name)
        blobs = bucket.list_blobs(prefix=prefix)
        return [blob.name for blob in blobs]
    except Exception as e:
        print(f"   ⚠️  Failed to list files from GCS with prefix {prefix}: {e}")
        return []

def write_file_to_gcs(bucket_name: str, file_path: str, content: str) -> bool:
    """Write a file to GCS bucket"""
    try:
        client = get_storage_client()
        if not client:
            return False
        
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(file_path)
        
        blob.upload_from_string(content, content_type='application/json')
        print(f"   ✅ Saved to GCS: gs://{bucket_name}/{file_path}")
        return True
    except Exception as e:
        print(f"   ⚠️  Failed to write {file_path} to GCS: {e}")
        return False

def save_structured_data(company_id: str, structured_data: Dict[str, Any]) -> Optional[Path]:
    """
    Lab 5: Save structured data to data/structured/<company_id>.json
    Supports both local filesystem and GCS bucket.
    """
    bucket_name = os.getenv("GCS_BUCKET_NAME")
    use_gcs = bucket_name is not None and get_storage_client() is not None
    
    structured_json = json.dumps(structured_data, indent=2, default=str)
    
    if use_gcs:
        # Save to GCS
        file_path = f"structured/{company_id}.json"
        success = write_file_to_gcs(bucket_name, file_path, structured_json)
        if success:
            return Path(f"gs://{bucket_name}/{file_path}")
        else:
            # Fallback to local if GCS fails
            print(f"   ⚠️  GCS save failed, falling back to local filesystem")
            use_gcs = False
    
    if not use_gcs:
        # Save to local filesystem
        output_path = Path(f"data/structured/{company_id}.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        output_path.write_text(structured_json, encoding='utf-8')
        print(f"   ✅ Saved structured data: {output_path}")
        return output_path
    
    return None

def save_payload_to_storage(company_id: str, payload: Payload) -> Optional[Path]:
    """
    Lab 6: Save payload to data/payloads/<company_id>.json
    Supports both local filesystem and GCS bucket.
    """
    bucket_name = os.getenv("GCS_BUCKET_NAME")
    use_gcs = bucket_name is not None and get_storage_client() is not None
    
    payload_json = json.dumps(payload.model_dump(), indent=2, default=str)
    
    if use_gcs:
        # Save to GCS
        file_path = f"payloads/{company_id}.json"
        success = write_file_to_gcs(bucket_name, file_path, payload_json)
        if success:
            return Path(f"gs://{bucket_name}/{file_path}")
        else:
            # Fallback to local if GCS fails
            print(f"   ⚠️  GCS save failed, falling back to local filesystem")
            use_gcs = False
    
    if not use_gcs:
        # Save to local filesystem
        output_path = Path(f"data/payloads/{company_id}.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        output_path.write_text(payload_json, encoding='utf-8')
        print(f"   ✅ Saved payload: {output_path}")
        return output_path
    
    return None


def load_all_sources(company_id: str) -> Dict[str, Any]:
    """Load ALL sources: text, HTML, JSON, JSON-LD, structured, blogs, press, Forbes seed.
    
    Supports both local filesystem and GCS bucket (when GCS_BUCKET_NAME is set).
    """
    bucket_name = os.getenv("GCS_BUCKET_NAME")
    use_gcs = bucket_name is not None and get_storage_client() is not None
    
    # Determine base path (local or GCS prefix)
    if use_gcs:
        base_prefix = f"raw/{company_id}/initial_pull"
        print(f"📂 Loading sources from GCS: gs://{bucket_name}/{base_prefix}")
    else:
        base_path = Path(f"data/raw/{company_id}/initial_pull")
        print(f"📂 Loading sources from local filesystem: {base_path}")
    
    sources = {
        'files': {},
        'html_files': {},
        'structured_json': {},
        'jsonld_data': {},
        'html_structured': {},
        'blog_posts': [],
        'press_releases': [],
        'metadata': {},
        'url_mapping': {},
        'forbes_seed': {}
    }
    
    if use_gcs:
        # Load from GCS
        # List all files with the prefix
        all_files = list_files_from_gcs(bucket_name, base_prefix)
        
        # Text files
        for file_path in all_files:
            if file_path.endswith("_clean.txt") and "blog_posts" not in file_path:
                page_type = Path(file_path).stem.replace("_clean", "")
                content = read_file_from_gcs(bucket_name, file_path)
                if content:
                    sources['files'][page_type] = {
                        'content': content,
                        'path': f"gs://{bucket_name}/{file_path}",
                        'size': len(content)
                    }
        
        # HTML files
        for file_path in all_files:
            if file_path.endswith(".html") and "blog_posts" not in file_path:
                page_type = Path(file_path).stem
                content = read_file_from_gcs(bucket_name, file_path)
                if content:
                    sources['html_files'][page_type] = {
                        'content': content,
                        'path': f"gs://{bucket_name}/{file_path}",
                        'size': len(content)
                    }
                    
                    # Extract JSON-LD
                    jsonld = extract_jsonld_data(content)
                    if jsonld:
                        sources['jsonld_data'][page_type] = jsonld
                    
                    # Extract structured
                    html_struct = extract_structured_from_html(content)
                    if html_struct:
                        sources['html_structured'][page_type] = html_struct
        
        # Structured JSON
        for file_path in all_files:
            if file_path.endswith("_structured.json"):
                page_type = Path(file_path).stem.replace("_structured", "")
                content = read_file_from_gcs(bucket_name, file_path)
                if content:
                    try:
                        data = json.loads(content)
                        sources['structured_json'][page_type] = data
                    except Exception as e:
                        print(f"   ⚠️  Failed to parse JSON from {file_path}: {e}")
        
        # Blog posts
        blog_prefix = f"{base_prefix}/blog_posts/"
        blog_files = list_files_from_gcs(bucket_name, blog_prefix)
        for file_path in blog_files:
            if file_path.endswith("_clean.txt"):
                post_id = Path(file_path).stem.replace("_clean", "")
                content = read_file_from_gcs(bucket_name, file_path)
                if content:
                    sources['blog_posts'].append({
                        'id': post_id,
                        'content': content,
                        'path': f"gs://{bucket_name}/{file_path}",
                        'size': len(content)
                    })
        
        # Metadata
        metadata_path = f"{base_prefix}/metadata.json"
        content = read_file_from_gcs(bucket_name, metadata_path)
        if content:
            try:
                metadata = json.loads(content)
                sources['metadata'] = metadata
                
                if 'pages' in metadata:
                    for page in metadata['pages']:
                        page_type = page.get('page_type')
                        source_url = page.get('source_url')
                        crawled_at = page.get('crawled_at')
                        
                        if page_type and source_url and crawled_at:
                            sources['url_mapping'][page_type] = {
                                'source_url': source_url,
                                'crawled_at': crawled_at
                            }
            except Exception as e:
                print(f"   ⚠️  Failed to load metadata: {e}")
        
        # Forbes seed data from GCS
        seed_file_path = os.getenv("GCS_SEED_FILE_PATH", "seed/forbes_ai50_seed.json")
        content = read_file_from_gcs(bucket_name, seed_file_path)
        if content:
            try:
                forbes_data = json.loads(content)
                for company in forbes_data:
                    website = company.get('website', '').lower()
                    if company_id.lower() in website:
                        sources['forbes_seed'] = company
                        print(f"   ✓ Loaded Forbes seed data for {company_id}")
                        break
            except Exception as e:
                print(f"   ⚠️  Failed to load Forbes seed: {e}")
    
    else:
        # Original local filesystem loading code
        # Text files
        for txt_file in base_path.glob("*_clean.txt"):
            page_type = txt_file.stem.replace("_clean", "")
            try:
                content = txt_file.read_text(encoding='utf-8')
                sources['files'][page_type] = {
                    'content': content,
                    'path': str(txt_file),
                    'size': len(content)
                }
            except Exception as e:
                print(f"   ⚠️  Failed to read {txt_file.name}: {e}")
        
        # HTML files
        for html_file in base_path.glob("*.html"):
            page_type = html_file.stem
            try:
                content = html_file.read_text(encoding='utf-8')
                sources['html_files'][page_type] = {
                    'content': content,
                    'path': str(html_file),
                    'size': len(content)
                }
                
                # Extract JSON-LD
                jsonld = extract_jsonld_data(content)
                if jsonld:
                    sources['jsonld_data'][page_type] = jsonld
                
                # Extract structured
                html_struct = extract_structured_from_html(content)
                if html_struct:
                    sources['html_structured'][page_type] = html_struct
            
            except Exception as e:
                print(f"   ⚠️  Failed to read {html_file.name}: {e}")
        
        # Structured JSON
        for json_file in base_path.glob("*_structured.json"):
            page_type = json_file.stem.replace("_structured", "")
            try:
                data = json.loads(json_file.read_text(encoding='utf-8'))
                sources['structured_json'][page_type] = data
            except Exception as e:
                print(f"   ⚠️  Failed to read {json_file.name}: {e}")
        
        # Blog posts
        blog_dir = base_path / "blog_posts"
        if blog_dir.exists():
            for blog_file in sorted(blog_dir.glob("*_clean.txt")):
                post_id = blog_file.stem.replace("_clean", "")
                try:
                    content = blog_file.read_text(encoding='utf-8')
                    sources['blog_posts'].append({
                        'id': post_id,
                        'content': content,
                        'path': str(blog_file),
                        'size': len(content)
                    })
                except:
                    pass
        
        # Press releases
        if 'press' in sources['files']:
            sources['press_releases'] = parse_press_releases(sources['files']['press']['content'])
        
        # Metadata
        metadata_file = base_path / "metadata.json"
        if metadata_file.exists():
            try:
                metadata = json.loads(metadata_file.read_text(encoding='utf-8'))
                sources['metadata'] = metadata
                
                if 'pages' in metadata:
                    for page in metadata['pages']:
                        page_type = page.get('page_type')
                        source_url = page.get('source_url')
                        crawled_at = page.get('crawled_at')
                        
                        if page_type and source_url and crawled_at:
                            sources['url_mapping'][page_type] = {
                                'source_url': source_url,
                                'crawled_at': crawled_at
                            }
            except Exception as e:
                print(f"   ⚠️  Failed to load metadata: {e}")
        
        # Forbes seed data
        forbes_path = Path("data/forbes_ai50_seed.json")
        if forbes_path.exists():
            try:
                with open(forbes_path, 'r', encoding='utf-8') as f:
                    forbes_data = json.load(f)
                
                for company in forbes_data:
                    website = company.get('website', '').lower()
                    if company_id.lower() in website:
                        sources['forbes_seed'] = company
                        print(f"   ✓ Loaded Forbes seed data for {company_id}")
                        break
                
                if not sources['forbes_seed']:
                    print(f"   ⚠️  No Forbes seed data found for {company_id}")
                    
            except Exception as e:
                print(f"   ⚠️  Failed to load Forbes seed: {e}")
    
    # Press releases (common for both GCS and local)
    if 'press' in sources['files']:
        sources['press_releases'] = parse_press_releases(sources['files']['press']['content'])
    
    return sources


def parse_press_releases(press_text: str) -> List[Dict[str, str]]:
    """Parse press releases into structured format with dates."""
    from dateutil import parser as date_parser
    
    releases = []
    lines = press_text.strip().split('\n')
    
    current_category = None
    current_title = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        if line in ['Announcements', 'Policy', 'Product', 'Research', 'Engineering']:
            current_category = line
            continue
        
        date_pattern = r'^([A-Z][a-z]{2})\s+(\d{1,2}),?\s+(\d{4})$'
        if re.match(date_pattern, line) and current_title:
            try:
                parsed_date = date_parser.parse(line)
                releases.append({
                    'title': current_title,
                    'date': parsed_date.strftime('%Y-%m-%d'),
                    'category': current_category or 'General'
                })
                current_title = None
            except:
                current_title = line
        else:
            if line and '@' not in line:
                current_title = line
    
    return releases


def get_jsonld_value(sources: Dict[str, Any], field: str) -> Any:
    """Get field from JSON-LD data across all pages."""
    for page_type, jsonld in sources.get('jsonld_data', {}).items():
        if field in jsonld and jsonld[field]:
            return jsonld[field]
    return None


def get_structured_data(sources: Dict[str, Any], field: str) -> Any:
    """Get field from structured JSON files."""
    for page_type, data in sources.get('structured_json', {}).items():
        if field in data and data[field]:
            return data[field]
    return None


def search_all_sources(sources: Dict[str, Any], keywords: List[str], max_chars: int = 5000) -> str:
    """COMPREHENSIVE: Search through ALL sources (text, HTML, blog posts)."""
    relevant_content = []
    total_chars = 0
    
    # Search text files
    for file_name, file_data in sources.get('files', {}).items():
        if total_chars >= max_chars:
            break
        
        content = file_data['content']
        paragraphs = re.split(r'\n\s*\n', content)
        
        for para in paragraphs:
            para_lower = para.lower()
            
            if any(kw.lower() in para_lower for kw in keywords):
                snippet = para.strip()
                relevant_content.append(f"[{file_name.upper()}]\n{snippet}\n")
                total_chars += len(snippet)
                
                if total_chars >= max_chars:
                    break
        
    # Search HTML files
    if total_chars < max_chars:
        html_content = search_html_sources(sources, keywords, max_chars - total_chars)
        if html_content:
            relevant_content.append(html_content)
            total_chars += len(html_content)
    
    # Search blog posts
    if total_chars < max_chars:
        for blog in sources.get('blog_posts', [])[:10]:
            if total_chars >= max_chars:
                break
            
            content = blog['content']
            paragraphs = re.split(r'\n\s*\n', content)
            
            for para in paragraphs:
                para_lower = para.lower()
                
                if any(kw.lower() in para_lower for kw in keywords):
                    snippet = para.strip()
                    relevant_content.append(f"[BLOG: {blog['id']}]\n{snippet}\n")
                    total_chars += len(snippet)
                    
                    if total_chars >= max_chars:
                        break
    
    return '\n---\n'.join(relevant_content)


def get_structured_timeline(sources: Dict[str, Any], event_type: str) -> str:
    """Get structured timeline of events with dates."""
    press_releases = sources.get('press_releases', [])
    
    if event_type == 'funding':
        keywords = FIELD_KEYWORDS['funding']
    elif event_type == 'product':
        keywords = FIELD_KEYWORDS['products']
    elif event_type == 'office':
        keywords = FIELD_KEYWORDS['offices']
    elif event_type == 'leadership':
        keywords = FIELD_KEYWORDS['executives']
    else:
        return '\n'.join([f"{pr['date']}: {pr['title']}" for pr in press_releases])
    
    filtered = [pr for pr in press_releases 
                if any(kw in pr['title'].lower() for kw in keywords)]
    
    return '\n'.join([f"{pr['date']}: {pr['title']}" for pr in filtered])


# ============================================================================
# EXTRACTION FUNCTIONS - COMPREHENSIVE WITH ANTI-HALLUCINATION
# ============================================================================

def extract_funding_events(sources: Dict[str, Any], company_id: str) -> Tuple[List[Event], Dict]:
    """IMPROVED: Enhanced investor extraction from scraped sources ONLY."""
    
    timeline = get_structured_timeline(sources, 'funding')
    details = search_all_sources(sources, FIELD_KEYWORDS['funding'], max_chars=4000)
    
    # IMPROVED: More comprehensive investor search
    investor_keywords = FIELD_KEYWORDS['investors'] + [
        'led by', 'backed by', 'participated', 'investment from', 'raised from',
        'venture capital', 'participated in', 'joined by', 'financing led',
        'round led', 'investment led', 'funding led', 'capital from'
    ]
    investor_context = search_all_sources(sources, investor_keywords, max_chars=4000)
    has_scraped_data = False
    if sources.get('files'):
        # Check if any file has actual content (not just whitespace)
        if any(file_data.get('content', '').strip() for file_data in sources['files'].values()):
            has_scraped_data = True

    if sources.get('html_files'):
        if any(file_data.get('content', '').strip() for file_data in sources['html_files'].values()):
            has_scraped_data = True

    if not has_scraped_data:
        print(f"   ⚠️  No scraped data with actual content - returning empty events")
        return [], {k: None for k in ['total_raised_usd', 'last_round_name', 'last_round_date', 'last_disclosed_valuation_usd']}
    
    structured_funding = get_structured_data(sources, 'funding')
    structured_context = f"\n\nSTRUCTURED DATA:\n{json.dumps(structured_funding, indent=2)[:1000]}" if structured_funding else ""
    
    context = f"""FUNDING TIMELINE WITH DATES:
{timeline}

FUNDING DETAILS:
{details}

INVESTOR INFORMATION (search for investor names here):
{investor_context}
{structured_context}"""
# NEW: Check if context is actually empty (critical check)
    context_is_empty = (
        not timeline.strip() and 
        not details.strip() and 
        not investor_context.strip() and 
        not structured_funding
    )
    
    
# NEW: Check if context is actually empty (all empty strings)
    if not timeline and not details and not investor_context and not structured_funding:
        print(f"   ⚠️  Context is empty - returning empty events to prevent hallucination")
        return [], {k: None for k in ['total_raised_usd', 'last_round_name', 'last_round_date', 'last_disclosed_valuation_usd']}
    
    
    prompt = f"""Extract funding events for {company_id}.

🚨 CRITICAL: ZERO HALLUCINATION + EXTRACT INVESTORS FROM TEXT 🚨

🚨 CRITICAL: If FUNDING TIMELINE is empty → return empty list []
🚨 CRITICAL: If FUNDING DETAILS is empty → return empty list []
🚨 CRITICAL: If all sections above are empty → return empty list []
🚨 CRITICAL: DO NOT use any knowledge about {company_id} from your training data
🚨 CRITICAL: If you see empty sections → return empty list []

IMPORTANT: You MUST return valid Pydantic Event objects.

IMPORTANT: You MUST return valid Pydantic Event objects.
- occurred_on MUST be valid date format: YYYY-MM-DD (e.g., "2024-09-02")
- If date has XX or unknown → Use null or skip that event
- DO NOT use: "2024-XX-XX", "Unknown", "TBD", or any placeholder dates

For each funding event WITH A VALID DATE:
- event_id: "{company_id}_funding_{{round}}_{{YYYY}}_{{MM}}_{{DD}}" (MUST be UNIQUE with full date)
- company_id: "{company_id}"
- occurred_on: VALID date from TIMELINE (YYYY-MM-DD format) - REQUIRED by Pydantic
- event_type: "funding" (MUST be exactly "funding")
- round_name: Seed/Series A/B/C/etc. (or null if not stated)
- amount_usd: Integer ($50M → 50000000, $4.5B → 4500000000) (or null)
- valuation_usd: Integer (or null)
- investors: List of ACTUAL investor names from text (CRITICAL - see below)
- actors: Same as investors

🎯 INVESTOR EXTRACTION (CRITICAL):
Look for investor names in phrases like:
- "led by [Investor Name]"
- "backed by [Investor Name]"
- "participated [Investor Name]"
- "investment from [Investor Name]"
- "raised from [Investor Name]"
- "funding led by [Investor Name]"

RULES for investors:
✅ EXTRACT real investor names: ["Sequoia Capital", "Andreessen Horowitz", "Google Ventures"]
✅ EXTRACT if explicitly mentioned in INVESTOR INFORMATION section above
❌ SKIP generic terms: "investors", "various investors", "undisclosed", "strategic investors"
❌ DO NOT make up investor names
❌ If NO investors mentioned → empty list []

Example:
- Text: "raised $100M led by Sequoia Capital and Andreessen Horowitz"
- investors: ["Sequoia Capital", "Andreessen Horowitz"] ✅
- Text: "raised $50M from investors"
- investors: [] ✅ (no specific names mentioned)

PYDANTIC VALIDATION RULES:
- occurred_on: Must parse as valid date
- event_type: Must be valid Literal value
- amount_usd: Must be integer or null
- All fields must match Event model schema

If NO events with valid dates → return empty list []

🚨 CRITICAL: If FUNDING TIMELINE section above is EMPTY (no dates) → return empty list []
🚨 CRITICAL: If FUNDING DETAILS section above is EMPTY (no text) → return empty list []
🚨 CRITICAL: If INVESTOR INFORMATION section above is EMPTY → return empty list []
🚨 CRITICAL: DO NOT use training data knowledge about {company_id}
🚨 CRITICAL: If all context sections are empty → return empty list []


{context}"""
    
    try:
        events = client.chat.completions.create(
            model=model_name,
            response_model=List[Event],
            messages=[
                {"role": "system", "content": "You extract funding data. Return valid Pydantic Event objects."},
                {"role": "user", "content": prompt}
            ],
            max_retries=3
        )
        
        valid_events = []
        seen_ids = set()
        
        for event in events:
            if not event.occurred_on:
                print(f"   ⚠️  Skipped event with no date")
                continue
            
            # IMPROVED: Ensure unique event_id with full date
            if event.event_id in seen_ids:
                month = str(event.occurred_on.month).zfill(2)
                day = str(event.occurred_on.day).zfill(2)
                round_slug = (event.round_name or 'unknown').lower().replace(' ', '_')
                event.event_id = f"{company_id}_funding_{round_slug}_{event.occurred_on.year}_{month}_{day}"
                print(f"   ⚠️  Regenerated unique ID: {event.event_id}")
            
            seen_ids.add(event.event_id)
            
            # IMPROVED: Filter placeholder investors
            if event.investors:
                placeholder_investors = {
                    'unknown', 'tbd', 'not disclosed', 'various', 'undisclosed',
                    'investors', 'strategic investors', 'venture capital', 'vc',
                    'private investors', 'angel investors', 'institutional investors'
                }
                
                filtered_investors = []
                for inv in event.investors:
                    inv_lower = inv.lower().strip()
                    # Keep only if NOT a generic placeholder AND has substance
                    if inv_lower not in placeholder_investors and len(inv.split()) >= 2:
                        filtered_investors.append(inv)
                    else:
                        print(f"   ⚠️  Filtered generic investor: {inv}")
                
                event.investors = filtered_investors
            
            # Log investor extraction
            if event.investors:
                print(f"   ✓ Found {len(event.investors)} investors: {', '.join(event.investors[:3])}")
            else:
                print(f"   ⚠️  No specific investors mentioned for {event.round_name or 'funding'}")
            
            event.provenance = create_provenance(sources, ['press', 'homepage'],
                snippet=f"funding: {event.title} - ${event.amount_usd:,}" if event.amount_usd else f"funding: {event.title}")
            
            valid_events.append(event)
        
        summary = {
            'total_raised_usd': sum(e.amount_usd or 0 for e in valid_events) or None,
            'last_round_name': None,
            'last_round_date': None,
            'last_disclosed_valuation_usd': None
        }
        
        if valid_events:
            dated = [e for e in valid_events if e.occurred_on]
            if dated:
                recent = max(dated, key=lambda e: e.occurred_on)
                summary.update({
                    'last_round_name': recent.round_name,
                    'last_round_date': recent.occurred_on,
                    'last_disclosed_valuation_usd': recent.valuation_usd
                })
        
        return valid_events, summary
        
    except ValidationError as e:
        print(f"   ⚠️  Pydantic validation failed after retries: {e}")
        return [], {k: None for k in ['total_raised_usd', 'last_round_name', 'last_round_date', 'last_disclosed_valuation_usd']}
    except Exception as e:
        print(f"   ⚠️  Funding extraction failed: {e}")
        return [], {k: None for k in ['total_raised_usd', 'last_round_name', 'last_round_date', 'last_disclosed_valuation_usd']}


def extract_leadership(sources: Dict[str, Any], company_id: str) -> List[Leadership]:
    """COMPREHENSIVE leadership extraction with cross-validation."""
    
    founder_context = search_all_sources(sources, FIELD_KEYWORDS['founders'], max_chars=4000)
    exec_context = search_all_sources(sources, FIELD_KEYWORDS['executives'], max_chars=4000)
    linkedin_context = search_all_sources(sources, FIELD_KEYWORDS['linkedin'], max_chars=2000)
    leadership_timeline = get_structured_timeline(sources, 'leadership')
    
    # Get team from HTML
    html_team_members = []
    for page_type, html_struct in sources.get('html_structured', {}).items():
        if 'team_members' in html_struct:
            html_team_members.extend(html_struct['team_members'])

    has_scraped_data = (
        len(sources.get('files', {})) > 0 or 
        len(sources.get('html_files', {})) > 0 or
        len(html_team_members) > 0
    )
    
    if not has_scraped_data:
        print(f"   ⚠️  No scraped data found - returning empty leadership")
        return []
    
    
    html_team_context = ""
    if html_team_members:
        html_team_context = "\n\nTEAM FROM HTML:\n" + "\n".join([
            f"- {m['name']}: {m.get('role', 'N/A')}" 
            for m in html_team_members[:15]
        ])
    
    context = f"""FOUNDERS:
{founder_context}

EXECUTIVES:
{exec_context}

LINKEDIN PROFILES:
{linkedin_context}

ANNOUNCEMENTS:
{leadership_timeline}
{html_team_context}"""
    
    prompt = f"""Extract ALL leadership for {company_id}.

🚨 ZERO HALLUCINATION + CROSS-VALIDATION RULES 🚨

For each person extract ALL FIELDS:
- person_id: "{company_id}_{{name_slug}}"
- company_id: "{company_id}"
- name: Full name (First Last) - REQUIRED
- role: Job title - REQUIRED (CEO, CTO, Founder, etc.)
- is_founder: True if founder/co-founder
- start_date: Appointment date YYYY-MM-DD (or null)
- end_date: Departure date YYYY-MM-DD (or null)
- previous_affiliation: Former company (or null)
- education: School/degree if mentioned (or null)
- linkedin: LinkedIn URL if mentioned (or null)

CRITICAL CROSS-VALIDATION:
- ONLY {company_id.upper()} employees
- If person works at ANOTHER company → SKIP THEM
- If previous_affiliation suggests they're CURRENTLY elsewhere → SKIP THEM
- Skip other companies' people
- Skip placeholders (John Doe, Unknown, etc.)
- Skip single names (need First Last)
- linkedin: ONLY if URL explicitly mentioned (e.g., "linkedin.com/in/person")
- end_date: ONLY if departure/leaving mentioned

VERIFY: Is this person CURRENTLY employed by {company_id.upper()}? If unsure → SKIP

{context}"""
    
    try:
        leaders = client.chat.completions.create(
            model=model_name,
            response_model=List[Leadership],
            messages=[
                {"role": "system", "content": f"Extract {company_id.upper()} leadership ONLY. Cross-validate company affiliation. ALL fields. NO placeholders. NO other companies."},
                {"role": "user", "content": prompt}
            ],
            max_retries=3
        )
        
        valid_leaders = []
        placeholder_names = {
            'john doe', 'jane doe', 'john smith', 'jane smith', 
            'unknown', 'test user', 'ceo', 'cto', 'founder'
        }
        
        for leader in leaders:
            if not leader.name or leader.name.lower().strip() in placeholder_names:
                print(f"   ⚠️  Filtered placeholder: {leader.name}")
                continue
            
            if ' ' not in leader.name:
                print(f"   ⚠️  Filtered incomplete name: {leader.name}")
                continue
            
            if leader.linkedin and 'linkedin.com' not in str(leader.linkedin).lower():
                print(f"   ⚠️  Invalid LinkedIn URL: {leader.linkedin}")
                leader.linkedin = None
            
            leader.provenance = create_provenance(sources, ['about', 'team', 'homepage'],
                snippet=f"{leader.name} - {leader.role}" + (f" (Founder)" if leader.is_founder else ""))
            
            valid_leaders.append(leader)
        
        return valid_leaders
        
    except ValidationError as e:
        print(f"   ⚠️  Pydantic validation failed: {e}")
        return []
    except Exception as e:
        print(f"   ⚠️  Leadership failed: {e}")
        return []


def extract_products(sources: Dict[str, Any], company_id: str) -> List[Product]:
    """COMPREHENSIVE product extraction with STRICT filtering against website sections."""
    
    product_context = search_all_sources(sources, FIELD_KEYWORDS['products'], max_chars=4000)
    pricing_context = search_all_sources(sources, FIELD_KEYWORDS['pricing'], max_chars=3000)
    integration_context = search_all_sources(sources, FIELD_KEYWORDS['integrations'], max_chars=2000)
    github_context = search_all_sources(sources, FIELD_KEYWORDS['github'], max_chars=2000)
    license_context = search_all_sources(sources, FIELD_KEYWORDS['license'], max_chars=1500)
    customer_context = search_all_sources(sources, FIELD_KEYWORDS['customers'], max_chars=2000)
    product_timeline = get_structured_timeline(sources, 'product')
    
    # Get data from HTML and JSON-LD
    html_pricing_tiers = []
    html_github_repos = []
    for page_type, html_struct in sources.get('html_structured', {}).items():
        if 'pricing_tiers' in html_struct:
            html_pricing_tiers.extend(html_struct['pricing_tiers'])
        if 'github_repos' in html_struct:
            html_github_repos.extend(html_struct['github_repos'])
    
    jsonld_products = get_jsonld_value(sources, 'products')
    has_scraped_data = (
        len(sources.get('files', {})) > 0 or 
        len(sources.get('html_files', {})) > 0 or
        len(html_pricing_tiers) > 0 or
        jsonld_products is not None
    )
    
    if not has_scraped_data:
        print(f"   ⚠️  No scraped data found - returning empty products")
        return []
    
    
    structured_info = f"""HTML DATA:
- Pricing tiers: {', '.join(html_pricing_tiers) if html_pricing_tiers else 'Not found'}
- GitHub repos: {', '.join(html_github_repos) if html_github_repos else 'Not found'}

JSON-LD PRODUCTS:
{json.dumps(jsonld_products, indent=2)[:1000] if jsonld_products else 'Not available'}"""
    
    context = f"""PRODUCT INFO:
{product_context}

PRICING:
{pricing_context}

INTEGRATIONS:
{integration_context}

GITHUB & OSS:
{github_context}

LICENSE:
{license_context}

CUSTOMERS:
{customer_context}

LAUNCHES WITH DATES:
{product_timeline}

{structured_info}"""
    
    prompt = f"""Extract ALL products for {company_id}.

🚨 ZERO HALLUCINATION + STRICT PRODUCT DEFINITION 🚨

A PRODUCT is something customers can USE, BUY, or DEPLOY.

✅ INCLUDE (Real Products):
- Software products: apps, APIs, platforms, tools, models, SDKs
- Hardware products: robots, devices, equipment
- SaaS offerings, enterprise software
- Developer tools, libraries, frameworks

❌ EXCLUDE (NOT Products - Website Sections/Pages):
- Website pages: "Blog", "Videos", "Press Kit", "Company", "Newsroom", "Press", "Careers"
- Content sections: "Resources", "Insights", "Documentation", "Support", "News"
- Legal documents: "Terms", "Privacy Policy", "Updates to Terms and Privacy"
- Initiatives/Programs: "Advisory Council", "Economic Program", "Futures Program"
- Partnerships/MOUs: "Partnership with X", "MOU with Government", "Signs Agreement"
- Announcements: "Expanding X", "Announces Y", "Updates to Z"
- Generic pages: "About", "Contact", "Team", "Investors", "Customers", "Partners", "Pricing"

For each product extract ALL FIELDS:
- product_id: "{company_id}_{{name_slug}}"
- company_id: "{company_id}"
- name: Product name - REQUIRED
- description: What it does (or null)
- pricing_model: "seat"/"usage"/"tiered" (or null)
- pricing_tiers_public: Tier names (use HTML: {html_pricing_tiers}) (or empty list)
- ga_date: Launch date from timeline (YYYY-MM-DD) (or null)
- integration_partners: Partners (or empty list)
- github_repo: GitHub URL (use HTML: {html_github_repos}) (or null)
- license_type: License (MIT, Apache, GPL, BSD, proprietary) (or null)
- reference_customers: Customers (or empty list)

VALIDATION: Ask yourself - Is this a REAL product customers use? Or is it a webpage/section/initiative?
If it's a webpage or initiative → SKIP IT

{context}"""
    
    try:
        products = client.chat.completions.create(
            model=model_name,
            response_model=List[Product],
            messages=[
                {"role": "system", "content": "Extract ONLY real products. NO website sections. NO initiatives. NO partnerships. STRICT filtering."},
                {"role": "user", "content": prompt}
            ],
            max_retries=3
        )
        
        valid_products = []
        generic_names = {'product', 'platform', 'ai platform', 'product 1', 'software'}
        
        for product in products:
            # IMPROVED: Strict filtering using is_website_section()
            if not product.name or is_website_section(product.name):
                print(f"   ⚠️  Filtered website section/non-product: {product.name}")
                continue
            
            if product.name.lower().strip() in generic_names:
                print(f"   ⚠️  Filtered generic: {product.name}")
                continue
            
            # Validate dates
            if product.ga_date and is_placeholder_date(product.ga_date):
                print(f"   ⚠️  Filtered invalid date: {product.ga_date}")
                product.ga_date = None
            
            # Override with HTML GitHub repos if LLM missed them
            if not product.github_repo and html_github_repos:
                for repo_url in html_github_repos:
                    if product.name.lower().replace(' ', '-') in repo_url.lower():
                        product.github_repo = repo_url
                        break
            
            # Normalize GitHub URL
            if product.github_repo:
                github_str = str(product.github_repo)
                if 'github.com' not in github_str.lower():
                    print(f"   ⚠️  Invalid GitHub: {github_str}")
                    product.github_repo = None
                else:
                    product.github_repo = normalize_url(github_str)
            
            product.provenance = create_provenance(sources, ['product', 'homepage'],
                snippet=f"Product: {product.name}" + (f" - {product.description[:100]}" if product.description else ""))
            
            valid_products.append(product)
        
        return valid_products
        
    except ValidationError as e:
        print(f"   ⚠️  Pydantic validation failed: {e}")
        return []
    except Exception as e:
        print(f"   ⚠️  Products failed: {e}")
        return []


def extract_snapshot(sources: Dict[str, Any], company_id: str, products: List[Product]) -> Snapshot:
    """COMPREHENSIVE snapshot extraction from all sources."""
    
    hiring_context = search_all_sources(sources, FIELD_KEYWORDS['hiring'], max_chars=3000)
    office_context = search_all_sources(sources, FIELD_KEYWORDS['offices'], max_chars=3000)
    office_timeline = get_structured_timeline(sources, 'office')
    
    # Get locations from HTML
    html_locations = []
    for page_type, html_struct in sources.get('html_structured', {}).items():
        if 'locations' in html_struct:
            html_locations.extend(html_struct['locations'])
    
    html_locations_context = ""
    if html_locations:
        html_locations_context = f"\n\nLOCATIONS FROM HTML:\n{', '.join(html_locations)}"
    
    product_names = [p.name for p in products]
    has_scraped_data = (
        len(sources.get('files', {})) > 0 or 
        len(sources.get('html_files', {})) > 0 or
        len(html_locations) > 0
    )
    context_is_empty = (
        not hiring_context.strip() and 
        not office_context.strip() and 
        not office_timeline.strip() and
        not html_locations
    )
    if not has_scraped_data or context_is_empty:
        print(f"   ⚠️  No scraped data or empty context - returning empty snapshot")
        return Snapshot(
            company_id=company_id, 
            as_of=date.today(), 
            provenance=create_provenance(sources, ['careers', 'homepage'])
        )
    context = f"""HIRING:
{hiring_context}

OFFICES:
{office_context}
{html_locations_context}

OFFICE TIMELINE:
{office_timeline}

PRODUCTS: {', '.join(product_names)}"""
    
    prompt = f"""Extract snapshot for {company_id}.

- company_id: "{company_id}"
- as_of: Today (YYYY-MM-DD)
- job_openings_count: Number
- hiring_focus: Departments
- pricing_tiers: Tier names
- active_products: Product list
- geo_presence: Office cities

{context}"""
    
    try:
        snapshot = client.chat.completions.create(
            model=model_name,
            response_model=Snapshot,
            messages=[
                {"role": "system", "content": "Extract snapshot."},
                {"role": "user", "content": prompt}
            ],
            max_retries=2
        )
        snapshot.company_id = company_id
        snapshot.as_of = date.today()
        
        snapshot.provenance = create_provenance(sources, ['careers', 'homepage'],
            snippet=f"Headcount: {snapshot.headcount_total}, Openings: {snapshot.job_openings_count}")
        
        return snapshot
    except Exception as e:
        print(f"   ⚠️  Snapshot failed: {e}")
        return Snapshot(
            company_id=company_id, 
            as_of=date.today(), 
            provenance=create_provenance(sources, ['careers', 'homepage'])
        )


def extract_other_events(sources: Dict[str, Any], company_id: str) -> List[Event]:
    """IMPROVED: Event extraction with RISK and OUTLOOK tagging from scraped sources ONLY."""
    
    timeline = get_structured_timeline(sources, 'all')
    
    # Build comprehensive context for ALL event types
    all_event_keywords = []
    for event_type in ['partnerships', 'launches', 'mna', 'integration', 'customer_win',
                       'regulatory', 'security_incident', 'pricing_change', 'layoff',
                       'hiring_spike', 'office_open', 'office_close', 'benchmark',
                       'open_source', 'contract_award']:
        all_event_keywords.extend(FIELD_KEYWORDS.get(event_type, []))
    
    event_context = search_all_sources(sources, all_event_keywords, max_chars=6000)
    
    # NEW: Search for risk factors in scraped text
    risk_keywords = [
        'risk', 'challenge', 'concern', 'issue', 'problem', 'setback',
        'investigation', 'lawsuit', 'litigation', 'complaint', 'scrutiny',
        'controversy', 'criticism', 'backlash', 'delay', 'regulatory action'
    ]
    risk_context = search_all_sources(sources, risk_keywords, max_chars=3000)
    
    # NEW: Search for outlook/forward-looking statements in scraped text
    outlook_keywords = [
        'plans to', 'will', 'expects', 'forecasts', 'outlook', 'guidance',
        'projects', 'anticipates', 'intends to', 'aims to', 'goals', 'roadmap',
        'future', 'upcoming', 'next year', 'expansion plans', 'strategy'
    ]
    outlook_context = search_all_sources(sources, outlook_keywords, max_chars=3000)
    has_scraped_data = (
        len(sources.get('files', {})) > 0 or 
        len(sources.get('html_files', {})) > 0 or
        len(sources.get('press_releases', [])) > 0
    )
    if not has_scraped_data:
        print(f"   ⚠️  No scraped data found - returning empty events")
        return []
    
    
    context = f"""EVENT TIMELINE WITH DATES (ONLY SOURCE OF TRUTH):
{timeline}

EVENT DETAILS (from all sources):
{event_context}

RISK FACTORS & CHALLENGES (tag as risk_factor if mentioned):
{risk_context}

OUTLOOK & FORWARD-LOOKING STATEMENTS (tag as outlook_statement if mentioned):
{outlook_context}"""
    
    prompt = f"""Extract ALL company events for {company_id} (NOT funding).

🚨 ZERO HALLUCINATION + STRICT TIMELINE VALIDATION 🚨

The TIMELINE above from press releases is your ONLY SOURCE OF TRUTH for dates.

Extract ALL event types:
1. product_release: Product launches
2. mna: Mergers & acquisitions ("acquires", "acquired by", "merger")
3. integration: Technology integrations ("integrates with X")
4. partnership: Business partnerships
5. customer_win: Major customer signings ("signs", "contract with")
6. leadership_change: Executive appointments/departures
7. regulatory: Compliance certifications ("SOC2", "HIPAA", "ISO")
8. security_incident: Security breaches or incidents
9. pricing_change: Pricing updates
10. layoff: Workforce reductions
11. hiring_spike: Rapid hiring announcements
12. office_open: New office openings
13. office_close: Office closures
14. benchmark: Performance benchmarks published
15. open_source_release: OSS releases
16. contract_award: Contract wins (esp. government)
17. other: Anything else significant

For EACH event:
- event_id: "{company_id}_{{type}}_{{title_slug}}_{{YYYY}}_{{MM}}_{{DD}}" (MUST be UNIQUE with full date)
- company_id: "{company_id}"
- occurred_on: VALID date from TIMELINE (YYYY-MM-DD) - REQUIRED
  * ❌ If no date in timeline → DO NOT extract that event
  * ❌ DO NOT use "2024-XX-XX" or placeholders
  * ✅ ONLY use dates that appear in TIMELINE
- event_type: Choose correct type from list above
- title: Brief title (from timeline preferred)
- description: Full details (or null)
- actors: Companies/people involved (or empty list)
- tags: Relevant tags (CRITICAL - see below)
- amount_usd: Dollar amount if applicable (or null)

🎯 TAGGING RULES (CRITICAL):
Use tags to categorize events based on SCRAPED TEXT ONLY:

RISK FACTORS:
- IF event mentions risks/challenges/problems in RISK FACTORS section above
- THEN add: ["risk_factor"] or ["risk_factor", "legal"] or ["risk_factor", "regulatory"]
- Example: "Investigation announced" → tags: ["risk_factor", "legal"]
- ❌ DO NOT tag as risk if not explicitly mentioned as risk/challenge

OUTLOOK STATEMENTS:
- IF event mentions future plans/expectations in OUTLOOK section above
- THEN add: ["outlook_statement"] or ["outlook_statement", "expansion"]
- Example: "Plans to expand to Europe" → tags: ["outlook_statement", "expansion"]
- ❌ DO NOT tag as outlook if not forward-looking

REGULATORY:
- IF regulatory/compliance event → tags: ["regulatory", "compliance"]
- Example: "Achieves SOC2" → tags: ["regulatory", "compliance"]

OTHER CATEGORIES:
- Use descriptive tags: ["strategic", "international"], ["AI", "research"], etc.
- ONLY use tags if explicitly supported by text

EXAMPLES:
✅ Text says "investigation into practices" → tags: ["risk_factor", "legal"]
✅ Text says "plans to launch in 2025" → tags: ["outlook_statement", "expansion"]
✅ Text says "achieves SOC2 certification" → tags: ["regulatory", "compliance"]
❌ Product launch with no risk mentioned → tags: [] (not ["risk_factor"])
❌ Event with no outlook mentioned → tags: [] (not ["outlook_statement"])

CRITICAL TIMELINE VALIDATION:
- Event MUST appear in TIMELINE with a real date
- If event is NOT in timeline → SKIP IT ENTIRELY
- ONLY extract events explicitly stated in timeline
- event_id MUST be unique (use full date YYYY_MM_DD)

{context}"""
    
    try:
        events = client.chat.completions.create(
            model=model_name,
            response_model=List[Event],
            messages=[
                {"role": "system", "content": "Extract ALL event types from TIMELINE ONLY. Tag risks and outlook based on SCRAPED TEXT ONLY. STRICT validation. NO placeholders. NO hallucinated events."},
                {"role": "user", "content": prompt}
            ],
            max_retries=3
        )
        
        valid_events = []
        seen_ids = set()
        
        for event in events:
            if event.occurred_on:
                date_str = str(event.occurred_on)
                if 'XX' in date_str or 'xx' in date_str:
                    print(f"   ⚠️  Filtered placeholder date: {date_str}")
                    continue
            else:
                print(f"   ⚠️  Skipped event with no date: {event.title}")
                continue
            
            # IMPROVED: Ensure unique event_id with full date
            if event.event_id in seen_ids:
                month = str(event.occurred_on.month).zfill(2)
                day = str(event.occurred_on.day).zfill(2)
                title_slug = re.sub(r'[^a-z0-9]+', '_', event.title.lower())[:30]
                event.event_id = f"{company_id}_{event.event_type}_{title_slug}_{event.occurred_on.year}_{month}_{day}"
                print(f"   ⚠️  Regenerated unique ID: {event.event_id}")
            
            seen_ids.add(event.event_id)
            
            # Log tagging
            if event.tags:
                if 'risk_factor' in event.tags:
                    print(f"   ✓ Tagged as RISK: {event.title}")
                if 'outlook_statement' in event.tags:
                    print(f"   ✓ Tagged as OUTLOOK: {event.title}")
            
            event.provenance = create_provenance(sources, ['press', 'homepage'],
                snippet=f"{event.event_type}: {event.title}")
            
            valid_events.append(event)
        
        # Summary stats
        risk_events = [e for e in valid_events if e.tags and 'risk_factor' in e.tags]
        outlook_events = [e for e in valid_events if e.tags and 'outlook_statement' in e.tags]
        
        if risk_events:
            print(f"   ✓ Extracted {len(risk_events)} risk factors")
        if outlook_events:
            print(f"   ✓ Extracted {len(outlook_events)} outlook statements")
        
        return valid_events
        
    except ValidationError as e:
        print(f"   ⚠️  Pydantic validation failed: {e}")
        return []
    except Exception as e:
        print(f"   ⚠️  Events failed: {e}")
        return []


def extract_company_record(sources: Dict[str, Any], company_id: str, funding_summary: Dict) -> Company:
    """COMPREHENSIVE company extraction with Forbes seed fallback (NO INFERENCE)."""
    
    # Get founding date from JSON-LD (HIGHEST PRIORITY)
    jsonld_founding = get_jsonld_value(sources, 'foundingDate')
    founded_year = None
    
    if jsonld_founding:
        try:
            year = int(jsonld_founding.split('-')[0])
            if 1990 <= year <= 2023:
                founded_year = year
                print(f"   ✓ Founded year from JSON-LD: {year}")
        except:
            pass
    
    # IMPROVED: Aggressive text search if JSON-LD didn't have it
    if not founded_year:
        founded_year = extract_founded_year_aggressive(sources)
    
    # Get legal name from JSON-LD
    jsonld_name = get_jsonld_value(sources, 'legalName') or get_jsonld_value(sources, 'name')
    
    # Get address from JSON-LD
    jsonld_address = get_jsonld_value(sources, 'address')
    
    # Search text sources
    company_context = search_all_sources(sources, FIELD_KEYWORDS['legal_name'], max_chars=3000)
    founded_context = search_all_sources(sources, FIELD_KEYWORDS['founded_year'], max_chars=2000)
    hq_context = search_all_sources(sources, FIELD_KEYWORDS['hq_city'], max_chars=2000)
    category_context = search_all_sources(sources, FIELD_KEYWORDS['categories'], max_chars=2000)
    
    # Get copyright years from HTML
    copyright_years = []
    for page_type, html_struct in sources.get('html_structured', {}).items():
        if 'copyright_years' in html_struct:
            copyright_years.extend(html_struct['copyright_years'])
    
    founded_info = f"""FOUNDING YEAR SOURCES:
- JSON-LD: {jsonld_founding or 'Not found'}
- Detected year: {founded_year or 'Not found'}
- Copyright years: {sorted(set(copyright_years)) if copyright_years else 'Not found'}"""
    
    jsonld_info = f"""JSON-LD DATA:
- Legal name: {jsonld_name or 'Not found'}
- Address: {jsonld_address or 'Not found'}"""
    
    context = f"""COMPANY INFO:
{company_context}

FOUNDING:
{founded_context}
{founded_info}

HEADQUARTERS:
{hq_context}

CATEGORIES:
{category_context}

{jsonld_info}

FUNDING SUMMARY:
- Total: ${funding_summary.get('total_raised_usd', 'Not disclosed')}
- Last round: {funding_summary.get('last_round_name', 'Not disclosed')}
- Last round date: {funding_summary.get('last_round_date', 'Not disclosed')}
- Valuation: ${funding_summary.get('last_disclosed_valuation_usd', 'Not disclosed')}"""
    
    prompt = f"""Extract company info for {company_id}.

🚨 CRITICAL: ZERO HALLUCINATION RULES 🚨

1. legal_name: ONLY use if explicitly stated or from JSON-LD
   - ✅ CORRECT: "Anthropic PBC" (if stated)
   - ❌ WRONG: Making up company names
   - If NOT found → use "{company_id.title()}"

2. founded_year: MUST be from reliable source
   - Priority 1: JSON-LD foundingDate
   - Priority 2: Explicit text "Founded in YYYY"
   - Priority 3: Earliest copyright year (1990-2023 only)
   - ❌ NEVER use: 2024, 2025 (these are scrape dates!)
   - ❌ NEVER use: Placeholder years, estimated years
   - If NOT found → null

3. hq_city, hq_state, hq_country: ONLY if explicitly stated
   - ✅ CORRECT: "San Francisco, CA, United States" (if stated)
   - ❌ WRONG: Guessing locations, using company name to guess
   - If NOT found → null

4. categories: ONLY if explicitly stated in text
   - ✅ CORRECT: ["AI Infrastructure", "Enterprise Software"] (if stated)
   - ❌ WRONG: Inferring from company name or description
   - If NOT found → empty list []

5. website: Use https://{company_id}.com as fallback only

Extract:
- company_id: "{company_id}"
- legal_name: Official name (or "{company_id.title()}")
- brand_name: Brand if different (or null)
- website: URL (or "https://{company_id}.com")
- hq_city: City (or null)
- hq_state: State code CA/NY/etc. (or null)
- hq_country: Country (or null)
- founded_year: Year 1990-2023 ONLY (or null)
- categories: List (or empty list)
- total_raised_usd: Use funding summary
- last_round_name: Use funding summary
- last_round_date: Use funding summary
- last_disclosed_valuation_usd: Use funding summary

{context}"""
    
    try:
        company = client.chat.completions.create(
            model=model_name,
            response_model=Company,
            messages=[
                {"role": "system", "content": "ONLY extract explicitly stated company info. NO guessing. NO placeholders."},
                {"role": "user", "content": prompt}
            ],
            max_retries=2
        )
        
        company.company_id = company_id
        company.as_of = date.today()
        
        # POST-PROCESSING: Validate founded year
        if company.founded_year:
            if company.founded_year >= 2024:
                print(f"   ⚠️  Filtered scrape date as founding year: {company.founded_year}")
                company.founded_year = None
            elif company.founded_year < 1990:
                print(f"   ⚠️  Filtered unrealistic founding year: {company.founded_year}")
                company.founded_year = None
        
        # Override with funding summary (these are validated)
        if funding_summary['total_raised_usd']:
            company.total_raised_usd = funding_summary['total_raised_usd']
        if funding_summary['last_round_name']:
            company.last_round_name = funding_summary['last_round_name']
        if funding_summary['last_round_date']:
            company.last_round_date = funding_summary['last_round_date']
        if funding_summary['last_disclosed_valuation_usd']:
            company.last_disclosed_valuation_usd = funding_summary['last_disclosed_valuation_usd']
        
        # IMPROVED: Override founded year with aggressive search if we have it
        if founded_year and not company.founded_year:
            company.founded_year = founded_year
        
        # ================================================================
        # NEW: FORBES SEED FALLBACK (NO INFERENCE - ONLY DIRECT OVERRIDE)
        # ================================================================
        forbes_seed = sources.get('forbes_seed', {})
        
        if forbes_seed:
            print(f"   ✓ Using Forbes seed as fallback source")
            
            # Override nulls with Forbes data (NO INFERENCE)
            if not company.hq_city and forbes_seed.get('hq_city'):
                company.hq_city = forbes_seed['hq_city']
                print(f"   ✓ HQ city from Forbes: {company.hq_city}")
            
            if not company.hq_country and forbes_seed.get('hq_country'):
                company.hq_country = forbes_seed['hq_country']
                print(f"   ✓ HQ country from Forbes: {company.hq_country}")
            
            # hq_state: ONLY from scraped data (Forbes doesn't have it)
            # NO INFERENCE - if not in scraped data, stays null
            
            if not company.categories and forbes_seed.get('category'):
                # Forbes has single category string, convert to list
                company.categories = [forbes_seed['category']]
                print(f"   ✓ Category from Forbes: {company.categories}")
            
            if not company.founded_year and forbes_seed.get('founded_year'):
                # Validate year from Forbes
                year = forbes_seed['founded_year']
                if isinstance(year, int) and 1990 <= year <= 2023:
                    company.founded_year = year
                    print(f"   ✓ Founded year from Forbes: {company.founded_year}")
        
        # Set fallback website if none found
        if not company.website or str(company.website) == 'https://example.com':
            company.website = f"https://{company_id}.com"
        
        # Populate provenance
        page_types = ['homepage', 'about']
        if jsonld_founding or jsonld_name:
            page_types.append('homepage')
        if forbes_seed:
            page_types.append('forbes_seed')
        
        company.provenance = create_provenance(sources, page_types, 
            snippet=f"Company: {company.legal_name}, Founded: {company.founded_year}, HQ: {company.hq_city}")
        
        return company
        
    except Exception as e:
        print(f"   ⚠️  Company failed: {e}")
        fallback_company = Company(
            company_id=company_id,
            legal_name=jsonld_name or company_id.title(),
            website=f"https://{company_id}.com",
            founded_year=founded_year,
            as_of=date.today(),
            provenance=create_provenance(sources, ['homepage', 'about'])
        )
        return fallback_company


def extract_visibility(sources: Dict[str, Any], company_id: str) -> Visibility:
    """Extract visibility."""
    
    press_releases = sources.get('press_releases', [])
    
    from datetime import timedelta
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    recent_count = 0
    for pr in press_releases:
        try:
            pr_date = datetime.strptime(pr['date'], '%Y-%m-%d')
            if pr_date >= thirty_days_ago:
                recent_count += 1
        except:
            pass
    
    positive_kw = ['launches', 'raises', 'partners', 'expands']
    negative_kw = ['layoff', 'closes', 'incident', 'breach']
    
    positive = sum(1 for pr in press_releases if any(kw in pr['title'].lower() for kw in positive_kw))
    negative = sum(1 for pr in press_releases if any(kw in pr['title'].lower() for kw in negative_kw))
    
    total = positive + negative
    sentiment = (positive / total) if total > 0 else 0.5
    
    visibility = Visibility(
        company_id=company_id,
        as_of=date.today(),
        news_mentions_30d=recent_count if recent_count > 0 else None,
        avg_sentiment=sentiment if total > 0 else None,
        provenance=create_provenance(sources, ['press', 'homepage'],
            snippet=f"News mentions (30d): {recent_count}, Sentiment: {sentiment:.2f}" if total > 0 else None)
    )
    
    return visibility


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

def extract_company_payload(company_id: str) -> Payload:
    """Extract complete payload using COMPREHENSIVE search + STRICT validation."""
    
    print(f"\n{'='*60}")
    print(f"🔍 EXTRACTING: {company_id}")
    print(f"🤖 Model: {model_name}")
    print(f"🚫 ZERO HALLUCINATION MODE ENABLED")
    print(f"{'='*60}")
    
    # Load ALL sources (text, HTML, JSON-LD, structured JSON)
    print("📂 Loading all sources...")
    sources = load_all_sources(company_id)
    print(f"   ✓ {len(sources['files'])} text files")
    print(f"   ✓ {len(sources['html_files'])} HTML files")
    print(f"   ✓ {len(sources['structured_json'])} structured JSON files")
    print(f"   ✓ {len(sources['jsonld_data'])} pages with JSON-LD")
    print(f"   ✓ {len(sources['blog_posts'])} blog posts")
    print(f"   ✓ {len(sources['press_releases'])} press releases")
    
    # Extract
    print("\n💰 Funding...")
    funding_events, funding_summary = extract_funding_events(sources, company_id)
    print(f"   ✓ {len(funding_events)} events")
    if funding_summary['total_raised_usd']:
        print(f"   ✓ Total raised: ${funding_summary['total_raised_usd']:,}")
    else:
        print(f"   ⚠️  Total raised: Not disclosed")
    
    print("\n👥 Leadership...")
    leadership = extract_leadership(sources, company_id)
    founders = [l for l in leadership if l.is_founder]
    print(f"   ✓ {len(founders)} founders, {len(leadership)-len(founders)} executives")
    if len(leadership) == 0:
        print(f"   ⚠️  No leadership found in scraped data")
    
    print("\n🛠️  Products...")
    products = extract_products(sources, company_id)
    print(f"   ✓ {len(products)} products")
    if len(products) == 0:
        print(f"   ⚠️  No products found in scraped data")
    
    print("\n📊 Snapshot...")
    snapshot = extract_snapshot(sources, company_id, products)
    print(f"   ✓ Snapshot: {snapshot.job_openings_count or 'hiring not disclosed'}")
    
    print("\n📅 Events...")
    other_events = extract_other_events(sources, company_id)
    print(f"   ✓ {len(other_events)} events")
    if len(other_events) == 0:
        print(f"   ⚠️  No non-funding events with dates found")
    
    print("\n🏢 Company record...")
    company = extract_company_record(sources, company_id, funding_summary)
    print(f"   ✓ {company.legal_name}")
    print(f"   ✓ Founded: {company.founded_year or 'Not disclosed'}")
    print(f"   ✓ HQ: {company.hq_city or 'Not disclosed'}")
    
    print("\n📰 Visibility...")
    visibility = extract_visibility(sources, company_id)
    print(f"   ✓ News mentions (30d): {visibility.news_mentions_30d or 'Not available'}")
    
    # Lab 5: Save structured data before payload assembly
    print("\n💾 Lab 5: Saving structured data...")
    structured_data = {
        'company_id': company_id,
        'company': company.model_dump(),
        'events': [e.model_dump() for e in funding_events + other_events],
        'products': [p.model_dump() for p in products],
        'leadership': [l.model_dump() for l in leadership],
        'snapshot': snapshot.model_dump(),
        'visibility': visibility.model_dump(),
        'extracted_at': datetime.now().isoformat(),
        'sources_summary': {
            'text_files': len(sources['files']),
            'html_files': len(sources['html_files']),
            'blog_posts': len(sources['blog_posts']),
            'press_releases': len(sources['press_releases'])
        }
    }
    structured_path = save_structured_data(company_id, structured_data)
    if structured_path:
        print(f"   ✅ Structured data saved: {structured_path}")
    
    all_events = funding_events + other_events
    
    # Lab 6: Build Payload
    payload = Payload(
        company_record=company,
        events=all_events,
        snapshots=[snapshot],
        products=products,
        leadership=leadership,
        visibility=[visibility],
        notes="",
        provenance_policy="ZERO HALLUCINATION: Only data from scraped sources. Missing = null or 'Not disclosed'."
    )
    
    # Data quality summary
    print(f"\n{'='*60}")
    print(f"📊 DATA QUALITY SUMMARY")
    print(f"{'='*60}")
    print(f"Events: {len(all_events)} total")
    print(f"  └─ Funding: {len(funding_events)}")
    print(f"  └─ Other: {len(other_events)}")
    if other_events:
        event_types = {}
        for e in other_events:
            event_types[e.event_type] = event_types.get(e.event_type, 0) + 1
        for event_type, count in sorted(event_types.items()):
            print(f"     • {event_type}: {count}")
    
    print(f"\nProducts: {len(products)}")
    if products:
        products_with_github = sum(1 for p in products if p.github_repo)
        products_with_license = sum(1 for p in products if p.license_type)
        print(f"  └─ With GitHub repo: {products_with_github}")
        print(f"  └─ With license info: {products_with_license}")
    
    print(f"\nLeadership: {len(leadership)}")
    print(f"  └─ Founders: {len(founders)}")
    print(f"  └─ Executives: {len(leadership)-len(founders)}")
    if leadership:
        with_linkedin = sum(1 for l in leadership if l.linkedin)
        with_education = sum(1 for l in leadership if l.education)
        print(f"  └─ With LinkedIn: {with_linkedin}")
        print(f"  └─ With education: {with_education}")
    
    print(f"\nSnapshot:")
    print(f"  └─ Headcount: {snapshot.headcount_total or 'Not disclosed'}")
    print(f"  └─ Job openings: {snapshot.job_openings_count or 'Not disclosed'}")
    print(f"  └─ Engineering openings: {snapshot.engineering_openings or 'Not disclosed'}")
    print(f"  └─ Sales openings: {snapshot.sales_openings or 'Not disclosed'}")
    print(f"  └─ Offices: {len(snapshot.geo_presence)} locations")
    
    print(f"\nVisibility:")
    print(f"  └─ News (30d): {visibility.news_mentions_30d or 'Not available'}")
    print(f"  └─ Sentiment: {visibility.avg_sentiment or 'Not available'}")
    print(f"  └─ GitHub stars: {visibility.github_stars or 'Not available'}")
    print(f"  └─ Glassdoor: {visibility.glassdoor_rating or 'Not available'}")
    
    print(f"{'='*60}\n")
    
    return payload


def process_companies(company_ids: List[str]):
    """Process multiple companies."""
    print(f"\n{'='*60}")
    print(f"🚀 BATCH: {len(company_ids)} companies")
    print(f"{'='*60}")
    
    results = []
    
    for idx, company_id in enumerate(company_ids, 1):
        print(f"\n[{idx}/{len(company_ids)}] {company_id}")
        
        try:
            payload = extract_company_payload(company_id)
            
            # Lab 6: Save payload (supports both local and GCS)
            print(f"\n💾 Lab 6: Saving payload...")
            payload_path = save_payload_to_storage(company_id, payload)
            if payload_path:
                print(f"✅ Saved payload: {payload_path}")
                results.append({'company_id': company_id, 'status': 'success', 'payload_path': str(payload_path)})
            else:
                print(f"⚠️  Failed to save payload")
                results.append({'company_id': company_id, 'status': 'failed', 'error': 'Failed to save payload'})
            
        except Exception as e:
            print(f"❌ Failed: {e}")
            results.append({'company_id': company_id, 'status': 'failed', 'error': str(e)})
    
    successful = [r for r in results if r['status'] == 'success']
    print(f"\n{'='*60}")
    print(f"✅ Successful: {len(successful)}/{len(company_ids)}")
    print(f"{'='*60}")
    
    return results

if __name__ == "__main__":
    test_companies = ["harvey", "figure", "anthropic"]
    results = process_companies(test_companies)


# ============================================================================
# IMPROVEMENTS SUMMARY
# ============================================================================

"""
✅ What Was Added (Anti-Hallucination Improvements):

1. is_website_section() - Filters 30+ website section patterns
   - Removes: "Blog", "Press Kit", "MOU with X", "Updates to Y", "Council", "Program"
   
2. extract_founded_year_aggressive() - Searches ALL text with 8 patterns
   - Patterns: "founded in", "established in", "since", "started in", etc.
   
3. Unique event IDs - Now includes full date (YYYY_MM_DD)
   - OLD: "anthropic_product_release_2025"
   - NEW: "anthropic_product_release_claude_sonnet_2025_09_29"
   
4. Leadership cross-validation - Stronger prompts
   - "Is this person CURRENTLY at {company}?"
   - "If they work at another company → SKIP"
   
5. Timeline-only event extraction - STRICT validation
   - "Event MUST appear in TIMELINE"
   - "If NOT in timeline → DO NOT extract"

✅ What Was Kept (Comprehensive Search):

- ALL HTML parsing (team, pricing, locations, copyright, headcount, GitHub, Glassdoor, jobs)
- ALL JSON-LD extraction (Organization, Product, Person, Event schemas)
- ALL source searching (text files, HTML files, blog posts)
- ALL field keyword mappings (30+ categories)
- ALL structured data extraction
- Complete provenance tracking
"""