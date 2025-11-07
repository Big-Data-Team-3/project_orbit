# Structured Extraction Module

A production-ready structured data extraction system that transforms raw scraped website content into validated, structured JSON using Pydantic models and Instructor (OpenAI). Designed with zero-hallucination principles to ensure all extracted data comes directly from scraped sources.

## Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [Installation](#installation)
4. [Quick Start](#quick-start)
5. [Structured Output Format](#structured-output-format)
6. [Data Models](#data-models)
7. [Extraction Process](#extraction-process)
8. [Source Loading](#source-loading)
9. [Anti-Hallucination Measures](#anti-hallucination-measures)
10. [Function Reference](#function-reference)
11. [Troubleshooting](#troubleshooting)
12. [Contributing](#contributing)
13. [License](#license)
14. [Support](#support)

## Overview

The structured extraction module takes raw scraped website content (HTML, text files, blog posts, press releases) and extracts structured information about companies, including:

- **Company Information**: Legal name, HQ location, founding year, categories, funding
- **Events**: Funding rounds, product launches, partnerships, leadership changes, regulatory milestones
- **Products**: Product names, descriptions, pricing models, GitHub repos, licenses
- **Leadership**: Founders, executives, roles, LinkedIn profiles, education
- **Snapshots**: Current headcount, job openings, hiring focus, office locations
- **Visibility**: News mentions, sentiment, GitHub stars, Glassdoor ratings

### Key Principles

1. **Zero Hallucination**: Only extracts data explicitly found in scraped sources
2. **Pydantic Validation**: All data validated against strict type schemas
3. **Comprehensive Search**: Searches all available sources (text, HTML, JSON-LD, blog posts)
4. **Provenance Tracking**: Every extracted field includes source URLs and timestamps
5. **Fallback Support**: Uses Forbes seed data as fallback (no inference)

## Features

### Anti-Hallucination

- **Empty Context Detection**: Returns empty lists/None if no relevant data found
- **Placeholder Filtering**: Filters out generic terms like "investors", "various", "undisclosed"
- **Website Section Filtering**: Distinguishes real products from website pages/initiatives
- **Cross-Validation**: Validates leadership against company affiliation
- **Timeline-Only Events**: Only extracts events with valid dates from press releases
- **Strict Date Validation**: Rejects placeholder dates (XX, unknown, TBD)

###  Comprehensive Extraction

- **Multi-Source Search**: Searches text files, HTML, JSON-LD, structured JSON, blog posts
- **Keyword-Based Discovery**: Uses 30+ keyword categories for targeted extraction
- **HTML Parsing**: Extracts team members, pricing tiers, locations, GitHub repos
- **JSON-LD Support**: Parses structured data from schema.org markup
- **Press Release Parsing**: Extracts timeline events with dates

###  Storage Support

- **Local Filesystem**: Saves to `data/structured/` and `data/payloads/`
- **Google Cloud Storage**: Optional GCS bucket support for production
- **Automatic Fallback**: Falls back to local if GCS unavailable

### Data Quality

- **Pydantic Validation**: Type-safe models with automatic validation
- **Retry Logic**: Instructor retries failed extractions up to 3 times
- **Error Handling**: Graceful handling of missing data, validation errors
- **Data Quality Summary**: Reports extraction statistics and completeness

## Installation

### Prerequisites

- Python 3.8+
- OpenAI API key
- Scraped data from `scraper.py` (in `data/raw/`)

### Required Dependencies

```bash
pip install instructor openai pydantic beautifulsoup4 lxml python-dateutil
```

### Optional Dependencies

For Google Cloud Storage support:

```bash
pip install google-cloud-storage google-auth
```

### Environment Variables

Create a `.env` file or set environment variables:

```bash
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4o-mini  # Optional, defaults to gpt-4o-mini

# Optional: Google Cloud Storage
GCS_BUCKET_NAME=your-bucket-name
PROJECT_ID=your-project-id
GCS_SEED_FILE_PATH=seed/forbes_ai50_seed.json  # Optional
```

### Verify Installation

```python
from src.structured_extraction import extract_company_payload

# Test extraction
payload = extract_company_payload("anthropic")
print(f"Extracted {len(payload.events)} events")
```

## Quick Start

### Basic Usage

Extract structured data for a single company:

```python
from src.structured_extraction import extract_company_payload

# Extract all data for a company
payload = extract_company_payload("anthropic")

# Access extracted data
print(f"Company: {payload.company_record.legal_name}")
print(f"Events: {len(payload.events)}")
print(f"Products: {len(payload.products)}")
print(f"Leadership: {len(payload.leadership)}")
```

### Batch Processing

Extract data for multiple companies:

```python
from src.structured_extraction import process_companies

# Process multiple companies
company_ids = ["anthropic", "harvey", "figure"]
results = process_companies(company_ids)

# Check results
for result in results:
    print(f"{result['company_id']}: {result['status']}")
```


## Structured Output Format

The module produces two types of structured output:

1. **Structured Data JSON** (`data/structured/{company_id}.json`)
2. **Payload JSON** (`data/payloads/{company_id}.json`)

### Structured Data JSON

This is an intermediate format containing all extracted entities:

```json
{
  "company_id": "anthropic",
  "company": {
    "company_id": "anthropic",
    "legal_name": "Anthropic PBC",
    "brand_name": null,
    "website": "https://www.anthropic.com",
    "hq_city": "San Francisco",
    "hq_state": "CA",
    "hq_country": "US",
    "founded_year": 2021,
    "categories": ["AI Safety", "Large Language Models"],
    "total_raised_usd": 4500000000,
    "last_round_name": "Series C",
    "last_round_date": "2023-05-23",
    "last_disclosed_valuation_usd": null,
    "schema_version": "2.0.0",
    "as_of": "2025-01-15",
    "provenance": [
      {
        "source_url": "https://www.anthropic.com/about",
        "crawled_at": "2025-01-15T10:30:00Z",
        "snippet": "Anthropic PBC was founded in 2021..."
      }
    ]
  },
  "events": [
    {
      "event_id": "anthropic_funding_series_c_2023_05_23",
      "company_id": "anthropic",
      "occurred_on": "2023-05-23",
      "event_type": "funding",
      "title": "Anthropic raises $450M Series C",
      "description": "Anthropic announced a $450M Series C funding round...",
      "round_name": "Series C",
      "investors": ["Spark Capital", "Google", "Salesforce Ventures"],
      "amount_usd": 450000000,
      "valuation_usd": null,
      "actors": ["Spark Capital", "Google", "Salesforce Ventures"],
      "tags": ["Series C"],
      "schema_version": "2.0.0",
      "provenance": [
        {
          "source_url": "https://www.anthropic.com/press",
          "crawled_at": "2025-01-15T10:30:00Z",
          "snippet": "Anthropic raises $450M Series C led by Spark Capital..."
        }
      ]
    }
  ],
  "products": [
    {
      "product_id": "anthropic_claude",
      "company_id": "anthropic",
      "name": "Claude",
      "description": "AI assistant focused on helpfulness, harmlessness, and honesty",
      "pricing_model": "usage",
      "pricing_tiers_public": ["Free", "Pro", "Enterprise"],
      "ga_date": "2023-03-14",
      "integration_partners": ["Slack", "Notion", "Zapier"],
      "github_repo": null,
      "license_type": "proprietary",
      "reference_customers": [],
      "schema_version": "2.0.0",
      "provenance": [
        {
          "source_url": "https://www.anthropic.com/product",
          "crawled_at": "2025-01-15T10:30:00Z",
          "snippet": "Claude is an AI assistant..."
        }
      ]
    }
  ],
  "leadership": [
    {
      "person_id": "anthropic_dario_amodei",
      "company_id": "anthropic",
      "name": "Dario Amodei",
      "role": "CEO",
      "is_founder": true,
      "start_date": "2021-01-01",
      "end_date": null,
      "previous_affiliation": "OpenAI",
      "education": "Stanford University",
      "linkedin": "https://www.linkedin.com/in/dario-amodei",
      "schema_version": "2.0.0",
      "provenance": [
        {
          "source_url": "https://www.anthropic.com/team",
          "crawled_at": "2025-01-15T10:30:00Z",
          "snippet": "Dario Amodei - CEO and Co-founder"
        }
      ]
    }
  ],
  "snapshot": {
    "company_id": "anthropic",
    "as_of": "2025-01-15",
    "headcount_total": 150,
    "headcount_growth_pct": null,
    "job_openings_count": 25,
    "engineering_openings": 15,
    "sales_openings": 5,
    "hiring_focus": ["AI Research", "Engineering", "Sales"],
    "pricing_tiers": ["Free", "Pro", "Enterprise"],
    "active_products": ["Claude"],
    "geo_presence": ["San Francisco", "New York"],
    "confidence": null,
    "schema_version": "2.0.0",
    "provenance": [
      {
        "source_url": "https://www.anthropic.com/careers",
        "crawled_at": "2025-01-15T10:30:00Z",
        "snippet": "We're hiring for 25 open positions..."
      }
    ]
  },
  "visibility": {
    "company_id": "anthropic",
    "as_of": "2025-01-15",
    "news_mentions_30d": 12,
    "avg_sentiment": 0.75,
    "github_stars": null,
    "glassdoor_rating": 4.2,
    "schema_version": "2.0.0",
    "provenance": [
      {
        "source_url": "https://www.anthropic.com/press",
        "crawled_at": "2025-01-15T10:30:00Z",
        "snippet": "Recent news mentions..."
      }
    ]
  },
  "extracted_at": "2025-01-15T12:00:00Z",
  "sources_summary": {
    "text_files": 12,
    "html_files": 12,
    "blog_posts": 15,
    "press_releases": 8
  }
}
```

### Payload JSON

This is the final output format, containing the complete `Payload` object:

```json
{
  "company_record": {
    "company_id": "anthropic",
    "legal_name": "Anthropic PBC",
    "website": "https://www.anthropic.com",
    "hq_city": "San Francisco",
    "hq_state": "CA",
    "hq_country": "US",
    "founded_year": 2021,
    "categories": ["AI Safety", "Large Language Models"],
    "total_raised_usd": 4500000000,
    "last_round_name": "Series C",
    "last_round_date": "2023-05-23",
    "schema_version": "2.0.0",
    "as_of": "2025-01-15",
    "provenance": [...]
  },
  "events": [
    {
      "event_id": "anthropic_funding_series_c_2023_05_23",
      "company_id": "anthropic",
      "occurred_on": "2023-05-23",
      "event_type": "funding",
      "title": "Anthropic raises $450M Series C",
      "round_name": "Series C",
      "investors": ["Spark Capital", "Google", "Salesforce Ventures"],
      "amount_usd": 450000000,
      "schema_version": "2.0.0",
      "provenance": [...]
    }
  ],
  "snapshots": [
    {
      "company_id": "anthropic",
      "as_of": "2025-01-15",
      "headcount_total": 150,
      "job_openings_count": 25,
      "hiring_focus": ["AI Research", "Engineering"],
      "geo_presence": ["San Francisco", "New York"],
      "schema_version": "2.0.0",
      "provenance": [...]
    }
  ],
  "products": [
    {
      "product_id": "anthropic_claude",
      "company_id": "anthropic",
      "name": "Claude",
      "description": "AI assistant focused on helpfulness...",
      "pricing_model": "usage",
      "pricing_tiers_public": ["Free", "Pro", "Enterprise"],
      "ga_date": "2023-03-14",
      "schema_version": "2.0.0",
      "provenance": [...]
    }
  ],
  "leadership": [
    {
      "person_id": "anthropic_dario_amodei",
      "company_id": "anthropic",
      "name": "Dario Amodei",
      "role": "CEO",
      "is_founder": true,
      "linkedin": "https://www.linkedin.com/in/dario-amodei",
      "schema_version": "2.0.0",
      "provenance": [...]
    }
  ],
  "visibility": [
    {
      "company_id": "anthropic",
      "as_of": "2025-01-15",
      "news_mentions_30d": 12,
      "avg_sentiment": 0.75,
      "glassdoor_rating": 4.2,
      "schema_version": "2.0.0",
      "provenance": [...]
    }
  ],
  "notes": "",
  "provenance_policy": "ZERO HALLUCINATION: Only data from scraped sources. Missing = null or 'Not disclosed'."
}
```

### Output File Locations

**Local Filesystem:**
- Structured data: `data/structured/{company_id}.json`
- Payload: `data/payloads/{company_id}.json`

**Google Cloud Storage (if configured):**
- Structured data: `gs://{bucket}/structured/{company_id}.json`
- Payload: `gs://{bucket}/payloads/{company_id}.json`


## Extraction Process

The extraction process follows these steps:

1. **Load Sources**: Loads all available scraped data
2. **Extract Funding Events**: Searches for funding rounds and investor information
3. **Extract Leadership**: Extracts founders and executives
4. **Extract Products**: Identifies products (filters out website sections)
5. **Extract Snapshot**: Current company state (headcount, hiring, offices)
6. **Extract Other Events**: Non-funding events (launches, partnerships, etc.)
7. **Extract Company Record**: Company metadata and information
8. **Extract Visibility**: News mentions, sentiment, ratings
9. **Save Structured Data**: Saves intermediate structured JSON
10. **Build Payload**: Assembles complete Payload object
11. **Save Payload**: Saves final payload JSON

### Extraction Order

The extraction follows a specific order to ensure dependencies are met:

```
1. Funding Events → Company Record (funding summary)
2. Leadership → Company Record (founders)
3. Products → Snapshot (active products)
4. Snapshot → Company Record (current state)
5. Other Events → Payload (all events)
6. Company Record → Payload (company info)
7. Visibility → Payload (metrics)
```

## Source Loading

The module supports loading sources from two locations:

### Local Filesystem

Loads from: `data/raw/{company_id}/initial_pull/`

**File Types:**
- `*_clean.txt`: Clean text files
- `*.html`: Raw HTML files
- `*_structured.json`: Pre-parsed structured data
- `blog_posts/*_clean.txt`: Blog post content
- `metadata.json`: Scraping metadata

### Google Cloud Storage

Loads from: `gs://{bucket}/raw/{company_id}/initial_pull/`

**Configuration:**
- Set `GCS_BUCKET_NAME` environment variable
- Set `PROJECT_ID` environment variable
- Place credentials at `config/gcp.json` (optional, uses ADC if not found)

**Automatic Fallback:**
- If GCS is unavailable, falls back to local filesystem
- If GCS read fails, falls back to local filesystem

## Anti-Hallucination Measures

The module implements multiple measures to prevent hallucination:

### 1. Empty Context Detection

Before extraction, checks if relevant content exists:

```python
if not timeline and not details and not investor_context:
    return []  # Return empty list, don't hallucinate
```

### 2. Placeholder Filtering

Filters out generic placeholder terms:

- **Investors**: "investors", "various", "undisclosed", "strategic investors"
- **Names**:"Unknown", "CEO", "CTO"
- **Dates**: "XX", "unknown", "TBD", "TBA"

### 3. Website Section Filtering

Distinguishes real products from website pages:

**Excluded:**
- Website pages: "Blog", "Press Kit", "Newsroom"
- Legal docs: "Terms", "Privacy Policy"
- Initiatives: "Advisory Council", "Economic Program"
- Partnerships: "MOU with X", "Partnership with Y"

**Included:**
- Software products: APIs, platforms, tools
- Hardware products: robots, devices
- SaaS offerings, developer tools

### 4. Cross-Validation

Validates extracted data against company affiliation:

- **Leadership**: Only includes people currently at the company
- **Events**: Only includes events with valid dates from timeline
- **Products**: Only includes real products, not website sections


### 6. Strict Date Validation

Rejects placeholder dates:

- ❌ "2024-XX-XX"
- ❌ "Unknown"
- ❌ "TBD"
- ✅ "2024-09-02" (valid date)

### 7. Forbes Seed Fallback

Uses Forbes seed data as fallback (no inference):

- Only overrides `null` fields
- Does not infer or guess values
- Direct field mapping only


## Function Reference

### Main Orchestration Functions

#### `extract_company_payload(company_id: str) -> Payload`

**Purpose**: Main orchestrator function that extracts complete structured data for a company.

**Workflow**:
1. Loads all sources (text files, HTML, JSON-LD, blog posts, press releases)
2. Extracts funding events and summary
3. Extracts leadership team (founders + executives)
4. Extracts products (with website section filtering)
5. Extracts snapshot (headcount, hiring, offices)
6. Extracts other events (non-funding events with timeline validation)
7. Extracts company record (legal name, HQ, founded year, categories)
8. Extracts visibility metrics (news mentions, sentiment)
9. Saves structured data to `data/structured/{company_id}.json`
10. Builds and returns complete Payload object

**Parameters:**
- `company_id` (str): Company identifier (e.g., "anthropic")

**Returns:**
- `Payload`: Complete payload with all extracted entities

**Example:**
```python
payload = extract_company_payload("anthropic")
print(f"Company: {payload.company_record.legal_name}")
print(f"Events: {len(payload.events)}")
print(f"Products: {len(payload.products)}")
```

#### `process_companies(company_ids: List[str]) -> List[Dict]`

**Purpose**: Batch processing for multiple companies.

**Workflow**:
1. Iterates through each company ID
2. Calls `extract_company_payload()` for each
3. Saves payload to storage (local or GCS)
4. Collects results with status and paths
5. Returns summary of successful/failed extractions

**Parameters:**
- `company_ids` (List[str]): List of company identifiers

**Returns:**
- `List[Dict]`: Results with `company_id`, `status`, `payload_path` (or `error`)

### Source Loading Functions

#### `load_all_sources(company_id: str) -> Dict[str, Any]`

**Purpose**: Loads all available scraped data from local filesystem or GCS.

**Supports**:
- **Local**: `data/raw/{company_id}/initial_pull/`
- **GCS**: `gs://{bucket}/raw/{company_id}/initial_pull/` (if `GCS_BUCKET_NAME` is set)

**Returns Dictionary With**:
- `files`: Text files (`*_clean.txt`) with content and metadata
- `html_files`: HTML files (`*.html`) with content
- `structured_json`: Pre-parsed structured JSON (`*_structured.json`)
- `jsonld_data`: JSON-LD structured data extracted from HTML
- `html_structured`: HTML-parsed data (team members, pricing tiers, locations, GitHub repos)
- `blog_posts`: Blog post content with IDs
- `press_releases`: Parsed press releases with dates
- `metadata`: Scraping metadata with page URLs and timestamps
- `url_mapping`: URL mappings by page type
- `forbes_seed`: Forbes seed data (if available)

**Automatic Fallback**: Falls back to local filesystem if GCS is unavailable.

### Extraction Functions

#### `extract_funding_events(sources: Dict[str, Any], company_id: str) -> Tuple[List[Event], Dict]`

**Purpose**: Extracts funding events and investor information with zero-hallucination validation.

**Process**:
1. Gets structured timeline from press releases
2. Searches all sources for funding keywords
3. Searches specifically for investor names (led by, backed by, participated)
4. **Empty Context Check**: Returns empty list if no funding data found
5. Uses Instructor + Pydantic to extract events
6. Filters placeholder investors ("various", "undisclosed", "strategic investors")
7. Validates dates (rejects "XX", "unknown", "TBD")
8. Creates unique event IDs with full date: `{company_id}_funding_{round}_{YYYY}_{MM}_{DD}`
9. Returns events list and funding summary (total raised, last round, valuation)

**Anti-Hallucination Measures**:
- Returns empty list if timeline/details/investor context are all empty
- Filters generic investor terms
- Only extracts events with valid dates from timeline
- Validates investor names have substance (at least 2 words)

**Returns**:
- `Tuple[List[Event], Dict]`: Events list and funding summary dict

#### `extract_leadership(sources: Dict[str, Any], company_id: str) -> List[Leadership]`

**Purpose**: Extracts founders and executives with cross-validation.

**Process**:
1. Searches for founders using founder keywords
2. Searches for executives using executive keywords
3. Searches for LinkedIn profiles
4. Gets team members from HTML parsing
5. Uses Instructor + Pydantic to extract leadership
6. **Cross-Validation**: Only includes people currently at the company
7. Filters placeholders (John Doe, Unknown, CEO, CTO)
8. Validates full names (must have space, not just role)
9. Validates LinkedIn URLs (must contain "linkedin.com")
10. Creates provenance from team/about/homepage pages

**Anti-Hallucination Measures**:
- Cross-validates company affiliation
- Filters placeholder names
- Requires full names (First Last)
- Validates LinkedIn URLs

**Returns**:
- `List[Leadership]`: List of leadership objects with founders and executives

#### `extract_products(sources: Dict[str, Any], company_id: str) -> List[Product]`

**Purpose**: Extracts products with strict filtering against website sections.

**Process**:
1. Searches all sources for product keywords
2. Searches for pricing, integrations, GitHub, license, customer info
3. Gets pricing tiers and GitHub repos from HTML parsing
4. Gets products from JSON-LD data
5. Uses Instructor + Pydantic to extract products
6. **Website Section Filtering**: Uses `is_website_section()` to filter out:
   - Website pages: "Blog", "Press Kit", "Newsroom", "Careers"
   - Legal docs: "Terms", "Privacy Policy"
   - Initiatives: "Advisory Council", "Economic Program"
   - Partnerships: "MOU with X", "Partnership with Y"
7. Filters generic names ("product", "platform", "software")
8. Validates GitHub URLs
9. Overrides with HTML-extracted GitHub repos if LLM missed them

**Anti-Hallucination Measures**:
- `is_website_section()` filters 30+ website section patterns
- Distinguishes real products from website pages/initiatives
- Only includes products customers can use/buy/deploy

**Returns**:
- `List[Product]`: List of product objects

#### `extract_snapshot(sources: Dict[str, Any], company_id: str, products: List[Product]) -> Snapshot`

**Purpose**: Extracts current company state snapshot.

**Process**:
1. Searches for hiring information
2. Searches for office locations
3. Gets locations from HTML parsing
4. Uses active product names from extracted products
5. Uses Instructor + Pydantic to extract snapshot
6. Sets `as_of` to today's date
7. Creates provenance from careers/homepage pages

**Returns**:
- `Snapshot`: Snapshot object with headcount, job openings, offices, active products

#### `extract_other_events(sources: Dict[str, Any], company_id: str) -> List[Event]`

**Purpose**: Extracts non-funding events with strict timeline validation and risk/outlook tagging.

**Process**:
1. Gets structured timeline from press releases (ONLY source of truth for dates)
2. Searches all sources for event keywords (partnerships, launches, M&A, etc.)
3. Searches for risk factors (risk, challenge, concern, lawsuit, investigation)
4. Searches for outlook statements (plans to, will, expects, forecasts, roadmap)
5. Uses Instructor + Pydantic to extract events
6. **Timeline Validation**: Only extracts events that appear in timeline with valid dates
7. **Tagging**: Tags events as `risk_factor` or `outlook_statement` based on scraped text
8. Creates unique event IDs: `{company_id}_{type}_{title_slug}_{YYYY}_{MM}_{DD}`
9. Filters placeholder dates

**Event Types Extracted**:
- `product_release`, `mna`, `integration`, `partnership`, `customer_win`
- `leadership_change`, `regulatory`, `security_incident`, `pricing_change`
- `layoff`, `hiring_spike`, `office_open`, `office_close`, `benchmark`
- `open_source_release`, `contract_award`, `other`

**Anti-Hallucination Measures**:
- **Timeline-only extraction**: Event MUST appear in timeline with date
- If event not in timeline → SKIP entirely
- Tags only based on explicit mentions in scraped text

**Returns**:
- `List[Event]`: List of event objects with risk/outlook tags

#### `extract_company_record(sources: Dict[str, Any], company_id: str, funding_summary: Dict) -> Company`

**Purpose**: Extracts company information with Forbes seed fallback (no inference).

**Process**:
1. Gets founding date from JSON-LD (highest priority)
2. If not found, uses `extract_founded_year_aggressive()` to search all text
3. Gets legal name from JSON-LD
4. Gets address from JSON-LD
5. Searches text sources for company info, HQ, categories
6. Gets copyright years from HTML
7. Uses Instructor + Pydantic to extract company record
8. **Post-processing**: Validates founded year (rejects 2024+, <1990)
9. Overrides with funding summary (validated data)
10. **Forbes Seed Fallback**: Overrides null fields with Forbes data (NO INFERENCE)
    - Only overrides if field is null
    - Direct field mapping only
    - Does not infer or guess values

**Anti-Hallucination Measures**:
- Only uses explicitly stated values
- Rejects scrape dates as founding years
- Forbes fallback only for null fields (no inference)

**Returns**:
- `Company`: Company object with legal name, HQ, founded year, categories, funding

#### `extract_visibility(sources: Dict[str, Any], company_id: str) -> Visibility`

**Purpose**: Extracts visibility metrics from press releases.

**Process**:
1. Counts press releases in last 30 days
2. Calculates sentiment from press release titles (positive vs negative keywords)
3. Creates Visibility object with news mentions and sentiment

**Returns**:
- `Visibility`: Visibility object with news mentions, sentiment

### Helper Functions

#### `is_website_section(name: str) -> bool`

**Purpose**: Filters out website sections that are not real products.

**Filters**:
- Website pages: "Blog", "Press Kit", "Newsroom", "Careers", "About"
- Legal docs: "Terms", "Privacy Policy", "Updates to Terms"
- Initiatives: "Advisory Council", "Economic Program", "Futures Program"
- Partnerships: "MOU with X", "Signs Agreement", "Announces Partnership"

**Returns**: `True` if name is a website section (should be filtered), `False` if it's a real product.

#### `extract_founded_year_aggressive(sources: Dict[str, Any]) -> Optional[int]`

**Purpose**: Aggressively searches ALL text content for founding year.

**Process**:
1. Combines all text files and blog posts
2. Searches with 8 patterns: "founded in", "established in", "since", "started in", etc.
3. Validates year is between 2000-2023
4. Returns first valid year found

**Returns**: Founding year (int) or `None` if not found.

#### `is_placeholder_name(name: str) -> bool`

**Purpose**: Checks if name is a placeholder (John Doe, Unknown, CEO, etc.).

**Returns**: `True` if placeholder, `False` if valid name.

#### `create_provenance(sources: Dict[str, Any], page_types: List[str], snippet: Optional[str] = None) -> List[Provenance]`

**Purpose**: Creates Provenance objects from metadata for source tracking.

**Process**:
1. Gets URL mappings from sources
2. Creates Provenance objects with source URLs, crawl timestamps, and snippets
3. Falls back to metadata if URL mapping unavailable

**Returns**: List of Provenance objects for source tracking.

### Storage Functions

#### `save_structured_data(company_id: str, structured_data: Dict[str, Any]) -> Optional[Path]`

**Purpose**: Saves structured data JSON to local filesystem or GCS.

**Supports**:
- **Local**: `data/structured/{company_id}.json`
- **GCS**: `gs://{bucket}/structured/{company_id}.json` (if `GCS_BUCKET_NAME` is set)

**Automatic Fallback**: Falls back to local if GCS save fails.

**Returns**: Path to saved file (local Path or GCS path string).

#### `save_payload_to_storage(company_id: str, payload: Payload) -> Optional[Path]`

**Purpose**: Saves complete Payload JSON to local filesystem or GCS.

**Supports**:
- **Local**: `data/payloads/{company_id}.json`
- **GCS**: `gs://{bucket}/payloads/{company_id}.json` (if `GCS_BUCKET_NAME` is set)

**Automatic Fallback**: Falls back to local if GCS save fails.

**Returns**: Path to saved file (local Path or GCS path string).

## Troubleshooting

### Common Issues

#### 1. No Data Extracted

**Issue:** All extractions return empty lists/None

**Possible Causes:**
- No scraped data available
- Sources not loaded correctly
- Content doesn't match keywords

**Solutions:**
1. Verify scraped data exists:
   ```python
   sources = load_all_sources("anthropic")
   print(f"Files: {len(sources['files'])}")
   ```

2. Check source content:
   ```python
   if sources['files'].get('about'):
       print(sources['files']['about']['content'][:500])
   ```

3. Enable verbose logging to see extraction process

#### 2. Pydantic Validation Errors

**Issue:** `ValidationError` exceptions during extraction

**Possible Causes:**
- Invalid date formats
- Missing required fields
- Type mismatches

**Solutions:**
1. Check date formats in source data
2. Verify required fields are present
3. Review error messages for specific field issues

#### 3. OpenAI API Errors

**Issue:** API errors or rate limits

**Solutions:**
1. Check API key is set: `export OPENAI_API_KEY=your_key`
2. Verify API quota/limits
3. Use a different model: `export OPENAI_MODEL=gpt-4o-mini`
4. Add retry logic (already built-in with Instructor)

#### 4. GCS Connection Errors

**Issue:** GCS read/write failures

**Solutions:**
1. Verify credentials: `config/gcp.json` exists or ADC is configured
2. Check bucket name: `export GCS_BUCKET_NAME=your-bucket`
3. Verify permissions: bucket read/write access
4. Module will automatically fall back to local filesystem

#### 5. Missing Fields

**Issue:** Expected fields are `null` or missing

**Explanation:** This is expected behavior - the module only extracts data explicitly found in sources.

**Solutions:**
1. Check if data exists in scraped sources
2. Review extraction logs for warnings
3. Verify source files contain relevant content
4. Check if Forbes seed data is available as fallback

#### 6. Hallucinated Data

**Issue:** Extracted data doesn't match source content

**Solutions:**
1. Check provenance in output JSON
2. Verify source URLs match extracted data
3. Review extraction logs for filtering messages
4. Report issues if anti-hallucination measures fail

### Debugging Tips

1. **Enable Verbose Logging:**
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

2. **Check Source Loading:**
   ```python
   sources = load_all_sources("anthropic")
   print(f"Loaded {len(sources['files'])} text files")
   print(f"Loaded {len(sources['blog_posts'])} blog posts")
   ```

3. **Inspect Extracted Data:**
   ```python
   payload = extract_company_payload("anthropic")
   print(payload.model_dump_json(indent=2))
   ```

4. **Check Structured Data File:**
   ```python
   import json
   with open("data/structured/anthropic.json") as f:
       data = json.load(f)
   print(json.dumps(data, indent=2))
   ```

5. **Review Provenance:**
   ```python
   for event in payload.events:
       print(f"{event.title}: {event.provenance}")
   ```
## License

See the main repository LICENSE file.

## Support

For issues, questions, or contributions, please open an issue on GitHub.

