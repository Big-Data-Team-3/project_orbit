# Structured Extraction V2 - End-to-End Explanation

## Overview

`structured_extraction_v2.py` is a sophisticated data extraction pipeline that uses **Pydantic models** and **Instructor** (OpenAI with structured output) to extract structured company information from scraped website content. It follows a **ZERO HALLUCINATION** philosophy, only extracting data that is explicitly stated in the source material.

### Key Features
- **Pydantic Models**: Type-safe data validation
- **Instructor Integration**: Structured LLM extraction with retry logic
- **Zero Hardcoding**: Searches ALL sources dynamically
- **Zero Hallucination**: Only extracts explicitly stated information
- **Multi-Source Extraction**: Text files, HTML, JSON-LD, structured JSON, blog posts, press releases
- **Pre-extracted Data Priority**: Uses scraper's pre-extracted entities first (most reliable)
- **GCS Support**: Works with both local filesystem and Google Cloud Storage

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Main Entry Point                         │
│  main() → process_companies() → extract_company_payload()   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Source Loading                                  │
│  load_all_sources()                                         │
│  - Text files (*_clean.txt)                                │
│  - HTML files (*.html)                                      │
│  - JSON-LD data (extracted from HTML)                       │
│  - Structured JSON (*_structured.json)                      │
│  - Blog posts                                                │
│  - Press releases                                            │
│  - Pre-extracted entities (from scraper)                    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Entity Extraction (Priority Order)              │
│  1. Pre-extracted entities (scraper output)                 │
│  2. JSON-LD structured data                                 │
│  3. LLM extraction from scraped content                     │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Funding      │ │ Leadership   │ │ Products    │
│ Events       │ │ Extraction   │ │ Extraction  │
└──────────────┘ └──────────────┘ └──────────────┘
        │              │              │
        └──────────────┴──────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Company      │ │ Snapshot     │ │ Visibility  │
│ Record       │ │ Extraction   │ │ Extraction  │
└──────────────┘ └──────────────┘ └──────────────┘
        │              │              │
        └──────────────┴──────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Payload Assembly                                │
│  Payload(company, events, products, leadership, ...)        │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Data Persistence                                │
│  save_structured_data() → structured JSON                   │
│  save_payload_to_storage() → Payload JSON                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Function Catalog

### 1. Validation Helper Functions

#### `is_placeholder_name(name: str) -> bool`
**Purpose**: Check if a name is a placeholder (e.g., "John Doe", "Test User").

**Filters**:
- Common placeholders: "john doe", "jane doe", "unknown", "test user"
- Pattern matching: `^john\s+doe`, `^test\s+`, etc.

**Returns**: `True` if placeholder, `False` otherwise.

---

#### `is_website_section(name: str) -> bool`
**Purpose**: Check if a "product" name is actually a website section (filters false positives).

**Filters**:
- Website pages: "Blog", "Press Kit", "Newsroom", "Careers"
- Legal docs: "Terms and Privacy", "Updates to Policy"
- Initiatives: "Advisory Council", "Economic Program"
- Pattern-based: `^updates?\s+to\s+`, `^mou\s+with\s+`, etc.

**Returns**: `True` if website section, `False` otherwise.

---

#### `is_valid_full_name(name: str) -> bool`
**Purpose**: Check if name is a valid full name (First Last format).

**Requirements**:
- Must contain a space
- Must have at least 2 words
- Each word must be at least 2 characters

**Returns**: `True` if valid full name.

---

#### `is_placeholder_date(date_value: Any) -> bool`
**Purpose**: Check if date is a placeholder (e.g., "1900-01-01", "1970-01-01").

**Returns**: `True` if placeholder date.

---

### 2. URL & Data Utilities

#### `normalize_url(url: str, prefix: str = 'https://') -> Optional[str]`
**Purpose**: Normalize URLs (add protocol if missing, validate format).

**Returns**: Normalized URL or `None` if invalid.

---

#### `create_provenance(sources: Dict[str, Any], page_types: List[str], snippet: str = "") -> Provenance`
**Purpose**: Create provenance object tracking data sources.

**Includes**:
- Source URLs (from url_mapping)
- Page types used
- Crawl dates
- Snippet of extracted data

**Returns**: Provenance Pydantic model.

---

### 3. Source Loading Functions

#### `load_all_sources(company_id: str) -> Dict[str, Any]`
**Purpose**: Load ALL sources for a company (text, HTML, JSON-LD, structured JSON, blogs, press).

**Supports**:
- **Local filesystem**: `data/raw/{company_id}/comprehensive_extraction/`
- **Google Cloud Storage**: `gs://{bucket}/raw/{company_id}/comprehensive_extraction/`

**Loads**:
1. **Text files** (`*_clean.txt`): Clean text content
2. **HTML files** (`*.html`): Raw HTML
3. **JSON-LD data**: Extracted from HTML using `extract_jsonld_data()`
4. **Structured JSON**: From `*_structured.json` files
5. **HTML structured data**: Extracted using `extract_structured_from_html()`
6. **Blog posts**: From `blog_posts/` directory
7. **Press releases**: From press pages
8. **Metadata**: Crawl metadata, URL mappings
9. **Pre-extracted entities**: From `extracted_entities.json` (scraper output)
10. **Forbes seed data**: Initial company data

**Returns**: Dictionary with all sources organized by type.

---

#### `extract_jsonld_data(html_content: str) -> Dict[str, Any]`
**Purpose**: Extract JSON-LD structured data from HTML.

**Uses**: `extruct` library to parse JSON-LD scripts.

**Returns**: Dictionary of JSON-LD items by type (Organization, Person, Product, etc.).

---

#### `extract_structured_from_html(html_content: str) -> Dict[str, Any]`
**Purpose**: Extract structured data from HTML (microdata, RDFa, Open Graph).

**Uses**: `extruct` library for microdata and RDFa.

**Returns**: Dictionary with structured data.

---

### 4. GCS (Google Cloud Storage) Functions

#### `get_storage_client() -> Optional[storage.Client]`
**Purpose**: Get or create GCS storage client.

**Authentication**:
1. Service account file: `config/gcp.json`
2. Application Default Credentials (production)

**Returns**: Storage client or `None` if unavailable.

---

#### `read_file_from_gcs(bucket_name: str, file_path: str) -> Optional[str]`
**Purpose**: Read file content from GCS bucket.

**Returns**: File content as string or `None` if error.

---

#### `list_files_from_gcs(bucket_name: str, prefix: str) -> List[str]`
**Purpose**: List all files in GCS bucket with given prefix.

**Returns**: List of file paths.

---

#### `write_file_to_gcs(bucket_name: str, file_path: str, content: str) -> bool`
**Purpose**: Write content to GCS bucket.

**Returns**: `True` if successful, `False` otherwise.

---

### 5. Data Persistence Functions

#### `save_structured_data(company_id: str, structured_data: Dict[str, Any]) -> Optional[Path]`
**Purpose**: Save structured data to JSON file.

**Location**:
- Local: `data/structured/{company_id}.json`
- GCS: `structured/{company_id}.json`

**Returns**: Path to saved file or `None` if error.

---

#### `save_payload_to_storage(company_id: str, payload: Payload) -> Optional[Path]`
**Purpose**: Save complete Payload to JSON file.

**Location**:
- Local: `data/payloads/{company_id}.json`
- GCS: `payloads/{company_id}.json`

**Returns**: Path to saved file or `None` if error.

---

### 6. Search & Extraction Utilities

#### `search_all_sources(sources: Dict[str, Any], keywords: List[str], max_chars: int = 5000) -> str`
**Purpose**: Search all text sources for keywords and return relevant context.

**Searches**:
- Text files (`*_clean.txt`)
- HTML content
- Blog posts
- Press releases

**Process**:
1. Find files/pages containing keywords
2. Extract relevant snippets (with context)
3. Combine and truncate to `max_chars`

**Returns**: Combined context string.

---

#### `search_html_sources(sources: Dict[str, Any], keywords: List[str], max_chars: int = 5000) -> str`
**Purpose**: Search only HTML sources for keywords.

**Returns**: Combined HTML context string.

---

#### `get_jsonld_value(sources: Dict[str, Any], field: str) -> Any`
**Purpose**: Extract value from JSON-LD data across all pages.

**Searches**: All JSON-LD items for the field.

**Returns**: First matching value or `None`.

---

#### `get_structured_data(sources: Dict[str, Any], field: str) -> Any`
**Purpose**: Extract value from structured data (microdata, RDFa).

**Returns**: First matching value or `None`.

---

#### `get_structured_timeline(sources: Dict[str, Any], event_type: str) -> str`
**Purpose**: Extract timeline text for specific event type.

**Returns**: Timeline text or empty string.

---

### 7. Pre-extracted Data Converters

#### `convert_pre_extracted_funding_events(pre_extracted: Dict[str, Any], company_id: str) -> List[Event]`
**Purpose**: Convert pre-extracted funding events to Event models.

**Process**:
- Validates dates
- Parses amounts (handles "$10M", "$5.5B" formats)
- Creates unique event IDs: `{company_id}_funding_YYYY_MM_DD`
- Validates with Pydantic Event model

**Returns**: List of Event models.

---

#### `convert_pre_extracted_leadership(pre_extracted: Dict[str, Any], company_id: str) -> List[Leadership]`
**Purpose**: Convert pre-extracted team members to Leadership models.

**Process**:
- Filters placeholder names
- Validates full names
- Extracts founder status
- Creates person IDs: `{company_id}_{lowercase_name}`
- Validates with Pydantic Leadership model

**Returns**: List of Leadership models.

---

#### `convert_pre_extracted_products(pre_extracted: Dict[str, Any], company_id: str) -> List[Product]`
**Purpose**: Convert pre-extracted products to Product models.

**Process**:
- Filters website sections (false positives)
- Extracts GitHub repos, licenses, pricing
- Creates product IDs: `{company_id}_{lowercase_name}`
- Validates with Pydantic Product model

**Returns**: List of Product models.

---

#### `convert_pre_extracted_company_info(pre_extracted: Dict[str, Any], company_id: str) -> Dict[str, Any]`
**Purpose**: Convert pre-extracted company info to Company model fields.

**Extracts**:
- Legal name, brand name
- Founded year
- Headquarters (city, state, country)
- Description, categories

**Returns**: Dictionary ready for Company model.

---

### 8. Entity Extraction Functions

#### `extract_founded_year_aggressive(sources: Dict[str, Any]) -> Optional[int]`
**Purpose**: Aggressively search for founded year using regex patterns.

**Patterns**:
- "founded in YYYY"
- "established YYYY"
- "since YYYY"
- Year ranges: "YYYY-YYYY" (takes first)

**Validates**: Year must be between 1990 and 2023.

**Returns**: Founded year or `None`.

---

#### `extract_funding_events(sources: Dict[str, Any], company_id: str) -> Tuple[List[Event], Dict]`
**Purpose**: Extract funding events with ZERO HALLUCINATION policy.

**Priority Order**:
1. **Pre-extracted entities** (from scraper) - NO HALLUCINATION
2. **LLM extraction** from scraped content (STRICT MODE)

**LLM Prompt Rules**:
- ONLY extract explicitly stated information
- DO NOT infer or guess
- If amount not stated → `null`
- If date not stated → `null` (DO NOT use today's date)
- AGGRESSIVELY extract investors, round names, valuations

**Returns**: Tuple of `(events_list, funding_summary_dict)`.

---

#### `extract_leadership(sources: Dict[str, Any], company_id: str) -> List[Leadership]`
**Purpose**: Extract leadership/team members with ZERO HALLUCINATION.

**Priority Order**:
1. **Pre-extracted entities** (from scraper)
2. **LLM extraction** from scraped content (STRICT MODE)

**LLM Prompt Rules**:
- ONLY extract explicitly stated names and roles
- If role not stated → `null`
- If LinkedIn not stated → `null`
- If founder status not explicit → `is_founder = false`

**Post-processing**:
- Filters false positives (product names, etc.)
- Validates full names
- Removes placeholders

**Returns**: List of Leadership models.

---

#### `extract_products(sources: Dict[str, Any], company_id: str) -> List[Product]`
**Purpose**: Extract products with ZERO HALLUCINATION.

**Priority Order**:
1. **Pre-extracted entities** (from scraper)
2. **JSON-LD Product** data
3. **LLM extraction** from scraped content (STRICT MODE)

**LLM Prompt Rules**:
- ONLY extract explicitly stated products
- Filter website sections (blog, press, etc.)
- Extract GitHub repos, licenses, pricing if stated

**Post-processing**:
- Filters website sections using `is_website_section()`
- Validates product names

**Returns**: List of Product models.

---

#### `extract_company_record(sources: Dict[str, Any], company_id: str, funding_summary: Dict) -> Company`
**Purpose**: Extract company record with ZERO HALLUCINATION.

**Priority Order**:
1. **Pre-extracted company info** (from scraper)
2. **JSON-LD** structured data (founding date, legal name)
3. **Aggressive text search** (founded year via regex)

**Extracts**:
- Legal name, brand name
- Founded year
- Headquarters (city, state, country separately)
- Description
- Categories
- Website URL (from metadata)
- Scrape date (for `as_of` field)

**Returns**: Company Pydantic model.

---

#### `extract_snapshot(sources: Dict[str, Any], company_id: str, products: List[Product]) -> Snapshot`
**Purpose**: Extract snapshot data (headcount, job openings, geo presence).

**Priority Order**:
1. **Pre-extracted snapshot data** (from scraper)
2. **HTML structured data** (fallback)

**Extracts**:
- Headcount total, growth %
- Job openings (total, engineering, sales)
- Hiring focus
- Pricing tiers
- Active products
- Geo presence (locations)

**Returns**: Snapshot Pydantic model.

---

#### `extract_other_events(sources: Dict[str, Any], company_id: str) -> List[Event]`
**Purpose**: Extract non-funding events (product launches, partnerships, etc.).

**Process**:
1. Search for timeline content
2. Use LLM to extract events with dates
3. Filter to only events with valid dates
4. Create unique event IDs: `{company_id}_{event_type}_YYYY_MM_DD`

**LLM Prompt Rules**:
- ONLY extract events with explicit dates
- Extract event type, title, description
- Extract actors/companies involved

**Returns**: List of Event models (non-funding).

---

#### `extract_visibility(sources: Dict[str, Any], company_id: str) -> Visibility`
**Purpose**: Extract visibility metrics (news mentions, GitHub stars, Glassdoor rating).

**Extracts**:
- News mentions (30-day count)
- Average sentiment
- GitHub stars (from products)
- Glassdoor rating

**Returns**: Visibility Pydantic model.

---

#### `extract_news_articles(sources: Dict[str, Any], company_id: str) -> List[NewsArticle]`
**Purpose**: Extract news articles from blog posts and press releases.

**Sources**:
- Blog posts (from `blog_posts/` directory)
- Press releases (from press pages)

**Extracts**:
- Title, content, author
- Date published
- URL
- Categories, tags

**Returns**: List of NewsArticle models.

---

### 9. Data Cleaning Functions

#### `clean_geo_presence(geo_list: List[str]) -> List[str]`
**Purpose**: Clean and normalize geographic presence list.

**Process**:
- Removes duplicates
- Normalizes city names
- Filters invalid entries

**Returns**: Cleaned list of locations.

---

#### `clean_hq_city(hq_city: Optional[str]) -> Optional[str]`
**Purpose**: Clean headquarters city name.

**Process**:
- Removes extra whitespace
- Normalizes format

**Returns**: Cleaned city name or `None`.

---

#### `clean_categories(categories: List[str]) -> List[str]`
**Purpose**: Clean and normalize category list.

**Process**:
- Removes duplicates
- Normalizes case
- Filters invalid entries

**Returns**: Cleaned list of categories.

---

### 10. Main Orchestrator Functions

#### `extract_company_payload(company_id: str) -> Payload`
**Purpose**: Main orchestrator that extracts complete payload for a company.

**Process Flow**:

1. **Load All Sources**:
   - Text files, HTML, JSON-LD, structured JSON
   - Blog posts, press releases
   - Pre-extracted entities

2. **Extract Entities** (in order):
   - Funding events
   - Leadership
   - Products
   - Snapshot
   - Other events
   - Company record
   - Visibility
   - News articles

3. **Save Structured Data**:
   - Save intermediate structured data JSON

4. **Build Payload**:
   - Assemble all entities into Payload model

5. **Print Data Quality Summary**:
   - Events count (funding vs other)
   - Products count (with GitHub, licenses)
   - Leadership count (founders vs executives)
   - Snapshot metrics
   - Visibility metrics
   - News articles count

6. **Return Payload**

**Returns**: Payload Pydantic model.

---

#### `process_companies(company_ids: List[str])`
**Purpose**: Process multiple companies in batch.

**Process**:
- For each company:
  - Call `extract_company_payload()`
  - Save payload to storage
  - Track success/failure
- Print summary of successful vs failed

**Returns**: List of result dictionaries.

---

## End-to-End Flow

### 1. Initialization Phase

```
main()
  └─> Parse command-line arguments (company_ids)
  └─> process_companies(company_ids)
       └─> For each company_id:
            └─> extract_company_payload(company_id)
```

### 2. Source Loading Phase

```
extract_company_payload(company_id)
  └─> load_all_sources(company_id)
       ├─> Determine storage (local vs GCS)
       ├─> Load text files (*_clean.txt)
       ├─> Load HTML files (*.html)
       │    ├─> extract_jsonld_data() → JSON-LD
       │    └─> extract_structured_from_html() → Structured data
       ├─> Load structured JSON (*_structured.json)
       ├─> Load blog posts (from blog_posts/)
       ├─> Load press releases (from press pages)
       ├─> Load metadata (crawl info, URL mappings)
       ├─> Load pre-extracted entities (extracted_entities.json)
       └─> Load Forbes seed data
```

### 3. Entity Extraction Phase

```
extract_company_payload() (continued)
  ├─> extract_funding_events()
  │    ├─> Priority 1: Pre-extracted entities
  │    │    └─> convert_pre_extracted_funding_events()
  │    └─> Priority 2: LLM extraction (if no pre-extracted)
  │         ├─> search_all_sources() for funding keywords
  │         └─> LLM prompt (STRICT MODE - NO HALLUCINATION)
  │
  ├─> extract_leadership()
  │    ├─> Priority 1: Pre-extracted entities
  │    │    └─> convert_pre_extracted_leadership()
  │    └─> Priority 2: LLM extraction (if no pre-extracted)
  │         ├─> search_all_sources() for leadership keywords
  │         └─> LLM prompt (STRICT MODE)
  │
  ├─> extract_products()
  │    ├─> Priority 1: Pre-extracted entities
  │    │    └─> convert_pre_extracted_products()
  │    ├─> Priority 2: JSON-LD Product data
  │    └─> Priority 3: LLM extraction (if no pre-extracted)
  │
  ├─> extract_snapshot()
  │    ├─> Priority 1: Pre-extracted snapshot data
  │    └─> Priority 2: HTML structured data (fallback)
  │
  ├─> extract_other_events()
  │    ├─> get_structured_timeline() for timeline content
  │    └─> LLM extraction (events with dates only)
  │
  ├─> extract_company_record()
  │    ├─> Priority 1: Pre-extracted company info
  │    │    └─> convert_pre_extracted_company_info()
  │    ├─> Priority 2: JSON-LD (founding date, legal name)
  │    └─> Priority 3: extract_founded_year_aggressive() (regex)
  │
  ├─> extract_visibility()
  │    └─> Extract from products (GitHub), news (mentions, sentiment)
  │
  └─> extract_news_articles()
       └─> Extract from blog posts and press releases
```

### 4. Data Persistence Phase

```
extract_company_payload() (continued)
  ├─> save_structured_data()
  │    └─> Save intermediate structured data JSON
  │         ├─> Local: data/structured/{company_id}.json
  │         └─> GCS: structured/{company_id}.json
  │
  └─> Build Payload model
       └─> Payload(
            company_record=company,
            events=all_events,
            snapshots=[snapshot],
            products=products,
            leadership=leadership,
            visibility=[visibility],
            news_articles=news_articles
       )
```

### 5. Final Persistence Phase

```
process_companies() (continued)
  └─> For each company:
       └─> save_payload_to_storage()
            ├─> Local: data/payloads/{company_id}.json
            └─> GCS: payloads/{company_id}.json
```

---

## Key Concepts

### 1. Zero Hallucination Policy

**Core Principle**: Only extract data that is **explicitly stated** in source material.

**Rules**:
- DO NOT infer or guess
- DO NOT use training data knowledge
- If information not stated → use `null` or "Not disclosed"
- DO NOT use placeholder dates (e.g., today's date)

**Implementation**:
- Pre-extracted entities (from scraper) are prioritized (most reliable)
- LLM prompts include strict "ZERO HALLUCINATION" instructions
- Post-processing validates and filters extracted data

### 2. Priority Order for Extraction

**General Priority**:
1. **Pre-extracted entities** (from scraper) - Most reliable, NO LLM
2. **JSON-LD structured data** - Structured, validated
3. **LLM extraction** - Only if no pre-extracted data, with strict prompts

**Why This Order?**
- Pre-extracted: Already validated, no hallucination risk
- JSON-LD: Structured data, reliable
- LLM: Last resort, with strict validation

### 3. Source Types

**Text Sources**:
- `*_clean.txt`: Clean text from pages
- Blog posts: Individual blog post files
- Press releases: Extracted from press pages

**Structured Sources**:
- JSON-LD: Extracted from HTML `<script type="application/ld+json">`
- Microdata/RDFa: Extracted from HTML attributes
- Structured JSON: From `*_structured.json` files

**Pre-extracted Sources**:
- `extracted_entities.json`: Output from scraper with pre-extracted entities

### 4. Pydantic Models

All extracted data is validated using Pydantic models:
- **Company**: Company record
- **Event**: Funding and other events
- **Product**: Product information
- **Leadership**: Team members
- **Snapshot**: Current state metrics
- **Visibility**: Visibility metrics
- **NewsArticle**: News articles
- **Payload**: Complete payload container
- **Provenance**: Source tracking

**Benefits**:
- Type safety
- Automatic validation
- Serialization to JSON

### 5. Instructor Integration

**Instructor** provides:
- Structured output from OpenAI
- Automatic retry on validation errors
- Pydantic model validation

**Usage**: Used for LLM extraction when pre-extracted data is unavailable.

### 6. GCS Support

**Dual Storage**:
- **Local**: `data/raw/`, `data/structured/`, `data/payloads/`
- **GCS**: `gs://{bucket}/raw/`, `gs://{bucket}/structured/`, `gs://{bucket}/payloads/`

**Detection**: Uses `GCS_BUCKET_NAME` environment variable to determine storage.

**Authentication**:
1. Service account file: `config/gcp.json`
2. Application Default Credentials (production)

### 7. Event ID Format

**Funding Events**: `{company_id}_funding_YYYY_MM_DD`
**Other Events**: `{company_id}_{event_type}_YYYY_MM_DD`

**Uniqueness**: Ensured by date component.

### 8. Person/Product ID Format

**Leadership**: `{company_id}_{lowercase_name_with_underscores}`
**Products**: `{company_id}_{lowercase_name_with_underscores}`

**Example**: `anthropic_dario_amodei`, `anthropic_claude`

---

## Dependencies

### Core Libraries
- **instructor**: Structured LLM output
- **openai**: OpenAI API client
- **pydantic**: Data validation
- **beautifulsoup4**: HTML parsing
- **extruct**: Structured data extraction (JSON-LD, microdata, RDFa)

### Google Cloud
- **google-cloud-storage**: GCS client
- **google-auth**: Authentication

### Internal Modules
- **models**: Pydantic models (Company, Event, Product, etc.)

---

## Usage

### Command Line

```bash
# Extract single company
python src/structured_extraction_v2.py anthropic

# Extract multiple companies
python src/structured_extraction_v2.py anthropic baseten codeium

# Default test companies (if no args)
python src/structured_extraction_v2.py
```

### Environment Variables

```bash
# Required
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini  # Optional, defaults to gpt-4o-mini

# Optional (for GCS)
GCS_BUCKET_NAME=your-bucket-name
PROJECT_ID=your-project-id
```

---

## Output Files

### Structured Data
- **Location**: `data/structured/{company_id}.json`
- **Content**: All extracted entities (company, events, products, leadership, snapshot, visibility)
- **Format**: JSON with Pydantic model dumps

### Payload
- **Location**: `data/payloads/{company_id}.json`
- **Content**: Complete Payload model
- **Format**: JSON with all entities

### GCS Output (if configured)
- Same structure in GCS bucket:
  - `structured/{company_id}.json`
  - `payloads/{company_id}.json`

---

## Error Handling

### LLM Extraction Errors
- **Validation Errors**: Retried by Instructor
- **No Data Found**: Returns empty list (not an error)
- **API Errors**: Logged, extraction continues with fallbacks

### Source Loading Errors
- **Missing Files**: Logged, continues with available sources
- **Parse Errors**: Logged, source skipped
- **GCS Errors**: Falls back to local if GCS unavailable

### Validation Errors
- **Pydantic Validation**: Errors logged, invalid data filtered
- **Type Errors**: Logged, field set to `None` or default

---

## Performance Considerations

### LLM Calls
- **Rate Limiting**: May be rate-limited by OpenAI API
- **Token Usage**: Each extraction uses ~2000-4000 tokens
- **Cost**: Depends on model (gpt-4o-mini is cheaper than gpt-4)

### Source Loading
- **File I/O**: Sequential file reading (can be parallelized)
- **GCS**: Network latency for GCS reads

### Optimization Opportunities
- **Parallel Company Processing**: Process multiple companies concurrently
- **Caching**: Cache LLM responses for similar content
- **Batch LLM Calls**: Batch multiple extractions in one call
- **Incremental Processing**: Only process new/changed sources

---

## Integration with Other Components

### Input
- **Source**: Output from `scraper_v2.py`
- **Files**: `*_clean.txt`, `*.html`, `*_complete.json`, `extracted_entities.json` in `comprehensive_extraction` directories

### Output
- **Structured Data**: `data/structured/{company_id}.json`
- **Payloads**: `data/payloads/{company_id}.json`
- **Use Case**: Dashboard, analytics, RAG pipeline

### Next Steps
After extraction, payloads can be used by:
- **Dashboard**: Display company information
- **Analytics**: Funding trends, leadership analysis
- **RAG Pipeline**: Company information retrieval
- **Risk Detection**: Company risk analysis

---

## Future Enhancements

Potential improvements:
- **Incremental Extraction**: Only extract new/changed data
- **Parallel Processing**: Process multiple companies concurrently
- **Better Error Recovery**: Retry failed extractions
- **More Entity Types**: Customers, partners, investors
- **Temporal Tracking**: Track changes over time
- **Confidence Scores**: Add confidence scores to extracted data
- **Source Attribution**: Better provenance tracking

