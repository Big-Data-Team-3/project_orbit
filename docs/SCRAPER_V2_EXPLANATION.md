# Scraper V2 - End-to-End Explanation

## Overview

`scraper_v2.py` is a comprehensive web scraper designed to extract **ALL** data from company websites. It's optimized for speed while maintaining completeness, focusing on extracting structured data, jobs, news articles, team information, and more from Forbes AI50 companies.

### Key Features
- **Speed Optimized**: Default 30 pages max (vs 200), reduced timeouts, minimal waits
- **Comprehensive Extraction**: All structured data, text, links, images, forms, tables, metadata
- **Smart Discovery**: Automatically finds 12 standard page types (homepage, about, careers, blog, etc.)
- **ATS Integration**: Fast job extraction via Greenhouse/Lever/Ashby APIs
- **RSS Integration**: Fast news collection via RSS/Atom feeds
- **Dynamic Pattern Detection**: No hardcoding, adapts to different website structures

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Main Entry Point                         │
│  main() → main_async() → scrape_company()                  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              ComprehensiveCrawler Class                     │
│  - Initialization & Discovery                               │
│  - Priority Content Fetching                                │
│  - Page Crawling                                            │
│  - Entity Extraction                                        │
│  - Results Saving                                           │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Extraction   │ │ ATS/News     │ │ Page         │
│ Functions    │ │ Extractors   │ │ Processing   │
└──────────────┘ └──────────────┘ └──────────────┘
```

---

## Function Catalog

### 1. ATS Domain Detection

#### `is_ats_domain(url: str) -> bool`
**Purpose**: Check if a URL belongs to a known Applicant Tracking System (ATS) domain.

**Returns**: `True` if URL is from Greenhouse, Lever, Workable, Ashby, etc.

**Used for**: Allowing external ATS domains to be crawled for job extraction.

---

### 2. Comprehensive Data Extraction Functions

#### `extract_all_structured_data(html: str, url: str) -> Dict[str, Any]`
**Purpose**: Extract ALL structured data formats from HTML.

**Extracts**:
- JSON-LD (Schema.org)
- Microdata
- RDFa
- Open Graph tags
- Twitter Cards
- Embedded JSON from script tags

**Returns**: Dictionary with all structured data organized by format.

---

#### `extract_all_links(html: str, base_url: str) -> List[Dict[str, Any]]`
**Purpose**: Extract all links with comprehensive metadata.

**Extracts**:
- href, full_url, text, title
- External/internal classification
- Link categories (careers, about, blog, etc.)
- Anchor text, rel, target, classes

**Returns**: List of link dictionaries with metadata.

---

#### `extract_all_images(html: str, base_url: str) -> List[Dict[str, Any]]`
**Purpose**: Extract all images with metadata.

**Extracts**:
- src, full_url, alt, title
- Dimensions (width, height)
- Logo detection
- Loading attributes

**Returns**: List of image dictionaries.

---

#### `extract_all_forms(html: str, base_url: str) -> List[Dict[str, Any]]`
**Purpose**: Extract all forms with field details.

**Extracts**:
- Form action, method, id, name
- All input fields (type, name, placeholder, label, required)
- Field relationships

**Returns**: List of form dictionaries with fields.

---

#### `extract_all_tables(html: str) -> List[Dict[str, Any]]`
**Purpose**: Extract all tables with data.

**Extracts**:
- Headers
- Rows
- Caption
- Table structure

**Returns**: List of table dictionaries.

---

#### `extract_all_metadata(html: str) -> Dict[str, Any]`
**Purpose**: Extract all HTML metadata.

**Extracts**:
- Title, description, keywords
- Author, language, viewport
- Charset, canonical URL
- Robots meta
- All other meta tags

**Returns**: Dictionary of metadata.

---

#### `extract_all_text_content(html: str) -> Dict[str, Any]`
**Purpose**: Extract all text content with semantic structure.

**Extracts**:
- Full clean text (via trafilatura)
- Headings (h1-h6) with hierarchy
- Paragraphs
- Lists (ordered/unordered)
- Blockquotes
- Code blocks

**Returns**: Dictionary with structured text content.

---

#### `extract_all_scripts(html: str) -> List[Dict[str, Any]]`
**Purpose**: Extract all script tags and their content.

**Extracts**:
- Script src, type, id
- Async/defer flags
- Embedded JSON detection
- Data pattern detection

**Returns**: List of script dictionaries.

---

#### `extract_navigation_structure(html: str, base_url: str) -> Dict[str, Any]`
**Purpose**: Extract navigation structure.

**Extracts**:
- Main navigation links
- Footer links
- Breadcrumbs
- Sitemap links

**Returns**: Dictionary with navigation structure.

---

### 3. Job Extraction Functions

#### `extract_jobs_from_all_sources(html: str, url: str) -> List[Dict[str, Any]]`
**Purpose**: Comprehensive job extraction from ALL possible sources.

**Sources**:
1. JSON-LD JobPosting schema
2. Embedded JSON (Greenhouse format)
3. HTML pattern matching (job cards/listings)
4. Link-based extraction
5. Table-based job listings

**Returns**: List of job dictionaries.

---

#### `find_jobs_in_embedded_data(data: Any, jobs: List[Dict] = None) -> List[Dict]`
**Purpose**: Recursively find job objects in nested data structures.

**Patterns Detected**:
- Standard job fields (title + location)
- Greenhouse format (absolute_url + title)
- Lever format (text + hostedUrl)

**Returns**: List of found jobs.

---

#### `extract_job_from_element(elem, base_url: str) -> Optional[Dict]`
**Purpose**: Extract job data from an HTML element.

**Extracts**:
- Title (from h2-h4, .title, .job-title, etc.)
- Location
- Department
- Description
- URL

**Returns**: Job dictionary or None.

---

### 4. News/Article Extraction Functions

#### `extract_news_article(html: str, url: str) -> Dict[str, Any]`
**Purpose**: Extract complete news/blog article data.

**Extracts**:
- Title, author, dates (published/modified)
- Content, excerpt
- Categories, tags
- Images
- Word count, reading time

**Sources**:
1. JSON-LD Article schema
2. Open Graph tags
3. HTML meta tags
4. Article tag content
5. Common content selectors

**Returns**: Complete article dictionary.

---

### 5. Feed & Deduplication Utilities

#### `parse_feed_xml(xml_text: str, base_url: str) -> List[Dict[str, str]]`
**Purpose**: Parse RSS or Atom feed content into generic structure.

**Supports**:
- RSS feeds (channel/item structure)
- Atom feeds (entry structure)
- Namespace handling

**Returns**: List of feed entry dictionaries.

---

#### `fetch_feed_entries(feed_url: str, limit: int = 25) -> List[Dict[str, str]]`
**Purpose**: Fetch and parse feed entries from a URL.

**Returns**: List of parsed feed entries (limited).

---

#### `dedupe_jobs_list(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]`
**Purpose**: Deduplicate jobs by title + URL.

**Returns**: Unique jobs list.

---

#### `dedupe_articles_list(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]`
**Purpose**: Deduplicate articles by URL (or title fallback).

**Returns**: Unique articles list.

---

#### `dedupe_by_field(items: List[Dict[str, Any]], field: str) -> List[Dict[str, Any]]`
**Purpose**: Generic deduplication by any field.

**Returns**: Unique items list.

---

### 6. Page Processing Functions

#### `detect_page_error(html: str, text_content: str = None) -> Optional[str]`
**Purpose**: Detect if a page contains an error message.

**Error Patterns Detected**:
- Application errors
- 404/500 errors
- Network errors
- Loading errors
- Short content with error keywords

**Returns**: Error type string or None.

---

#### `extract_complete_page_data(html: str, url: str) -> Dict[str, Any]`
**Purpose**: Extract ALL data from a page (main extraction function).

**Extracts**:
- All metadata
- All structured data
- All text content
- All links, images, forms, tables
- All scripts
- Navigation structure
- Statistics (word count, link counts, etc.)
- Error detection

**Returns**: Complete page data dictionary.

---

### 7. URL Discovery & Utility Functions

#### `safe_urljoin(base: str, url: str) -> str`
**Purpose**: Safe URL joining with None handling.

---

#### `is_same_domain(url: str, base_url: str) -> bool`
**Purpose**: Check if URL is from the same domain as base URL.

---

### 8. ComprehensiveCrawler Class Methods

#### `__init__(company: Dict, output_dir: Path, run_folder: str, max_pages: int = 50)`
**Purpose**: Initialize crawler for a company.

**Initializes**:
- Company info (id, name, base_url)
- Output directory structure
- Company profile (from company_profiles)
- Page discovery (all 12 page types)
- URL queues (visited, to_visit, priority)

---

#### `_find_page_url(page_type: str) -> Optional[str]`
**Purpose**: Find URL for a page type by trying multiple patterns.

**Method**: HTTP HEAD requests to test URL patterns.

**Returns**: Found URL or None.

---

#### `_discover_links_from_homepage(homepage_html: str) -> Dict[str, str]`
**Purpose**: Discover page URLs by analyzing homepage links.

**Discovers**: All 12 page types by matching URL patterns and link text.

**Returns**: Dictionary mapping page types to URLs.

---

#### `_discover_all_page_types()`
**Purpose**: Systematically discover all 12 page types.

**Process**:
1. Try URL patterns (fast HTTP HEAD requests)
2. Try homepage link analysis
3. Log discovered pages

---

#### `discover_urls(html: str, current_url: str) -> Set[str]`
**Purpose**: Discover all URLs from a page, prioritizing jobs and news.

**Prioritization**:
- Priority URLs: jobs, news, blog posts
- Regular URLs: about, team, product, pricing, etc.
- Skips: legal, docs, signup, login, etc.

**Returns**: Set of discovered URLs.

---

#### `fetch_priority_content(context: BrowserContext) -> None`
**Purpose**: Preload high-value pages before broad crawl.

**Process**:
1. **Crawl all 12 page types systematically**
   - Homepage first (to discover more pages)
   - Then about, product, careers, blog, team, etc.
   - Extract complete page data
   - Apply structured extraction based on page type

2. **Careers pages for jobs**
   - Use ATS extraction (Greenhouse/Lever/Ashby)
   - Check for iframes with external ATS
   - Scroll to load dynamic content
   - Click "Load More" buttons
   - Visit individual job detail pages
   - Comprehensive extraction as fallback

3. **News articles from RSS feeds**
   - Find RSS feeds from homepage
   - Use NewsExtractor for fast extraction
   - Fetch full article content
   - Fallback to profile blog feeds

**Stores**: Preloaded jobs and articles in `self.preloaded_jobs` and `self.preloaded_articles`.

---

#### `crawl_page(page: Page, url: str) -> Optional[Dict[str, Any]]`
**Purpose**: Crawl a single page comprehensively.

**Process**:
1. Check if already visited or at page limit
2. Navigate with Playwright
3. Check for errors (404, 500, PDFs)
4. Scroll and wait for dynamic content (priority pages only)
5. Extract complete page data
6. Check for errors and retry if needed
7. Extract jobs (if careers page) using ATS + comprehensive
8. Extract news article (if blog page) using NewsExtractor
9. Discover new URLs
10. Add to visited set

**Returns**: Page data dictionary or None.

---

#### `crawl()`
**Purpose**: Main crawl loop.

**Process**:
1. Initialize Playwright browser
2. **Fetch priority content** (12 page types + careers + news)
3. Check if page limit reached
4. **Crawl remaining discovered URLs**
   - Priority URLs first
   - Then regular URLs
   - Rate limiting (0.2s delays)
5. **Final summary** of extracted page types
6. Close browser
7. Save results

**Returns**: Summary dictionary with status and counts.

---

#### `extract_entities_from_data() -> Dict[str, Any]`
**Purpose**: Extract entities (jobs, team, products, etc.) from all collected data.

**Extracts**:
1. **Jobs**: From extracted_jobs, JSON-LD, embedded JSON
2. **Team Members**: From JSON-LD Person, HTML extraction (all pages)
3. **Products**: From JSON-LD Product, HTML extraction
4. **Customers**: From customers pages, JSON-LD Organization
5. **Partners**: From partners pages, JSON-LD Organization
6. **Investors**: From investors pages, JSON-LD Organization
7. **Funding Events**: From investors/press pages, text patterns
8. **News Articles**: From extracted_article, RSS feeds
9. **Company Info**: Founded year, HQ, description, categories
10. **Pricing**: Model, tiers from pricing pages
11. **Snapshot Data**: Headcount, job openings, geo presence
12. **Visibility Data**: GitHub stars, Glassdoor rating

**Returns**: Complete entities dictionary.

---

#### `_parse_amount(amount_str: str) -> Optional[float]`
**Purpose**: Parse amount string like "$10M", "$5.5B", "$100K" to float.

**Returns**: Amount in USD or None.

---

#### `_extract_team_from_html(html: str, url: str) -> List[Dict]`
**Purpose**: Extract team members from HTML with strict filtering.

**Methods**:
1. CSS selector matching (.team-member, .person, etc.)
2. Plain text parsing (name + title patterns)

**Filtering**:
- Must have first + last name
- Excludes locations, benefits, perks
- Validates name patterns

**Returns**: List of team member dictionaries.

---

#### `_extract_products_from_html(html: str, url: str) -> List[Dict]`
**Purpose**: Extract products from HTML.

**Extracts**:
- Name, description
- Pricing model, tiers
- GitHub repo
- License type
- Reference customers
- Integration partners
- GA/launch date

**Returns**: List of product dictionaries.

---

#### `_extract_company_info_from_html(html: str, url: str) -> Dict`
**Purpose**: Extract company info from HTML.

**Extracts**:
- Brand name (from h1 or title)
- Legal name (from patterns)
- Founded year
- Headquarters (city, state, country separately)
- Description
- Categories (from meta keywords, inline labels)
- Related companies

**Returns**: Company info dictionary.

---

#### `_extract_customers_from_html(html: str, url: str) -> List[Dict]`
**Purpose**: Extract customer names from HTML.

**Returns**: List of customer dictionaries.

---

#### `_extract_partners_from_html(html: str, url: str) -> List[Dict]`
**Purpose**: Extract partner names from HTML.

**Returns**: List of partner dictionaries.

---

#### `_parse_investors_page(html: str) -> List[Dict]`
**Purpose**: Extract investor and funding information.

**Extracts**:
- Funding round mentions
- Investor names

**Returns**: List of investor/funding dictionaries.

---

#### `_parse_press_page(html: str) -> List[Dict]`
**Purpose**: Extract press releases and funding announcements.

**Extracts**:
- Press release titles
- Dates
- URLs

**Returns**: List of press release dictionaries.

---

#### `_parse_pricing_page(html: str) -> Dict`
**Purpose**: Extract pricing information.

**Extracts**:
- Pricing model (per-seat, usage-based, enterprise)
- Tier names and prices

**Returns**: Pricing dictionary.

---

#### `_parse_customers_page(html: str) -> List[str]`
**Purpose**: Extract customer/client names.

**Returns**: List of customer names.

---

#### `_parse_partners_page(html: str) -> List[str]`
**Purpose**: Extract integration partner names.

**Returns**: List of partner names.

---

#### `save_results()`
**Purpose**: Save all extracted data to files.

**Saves**:
1. **Page data** (for each page):
   - HTML file (`{page_type}.html`)
   - Clean text file (`{page_type}_clean.txt`)
   - Complete JSON (`{page_type}_complete.json`)

2. **Entities**:
   - `extracted_entities.json` (all entities)
   - `all_jobs.json` (jobs only)
   - `all_news_articles.json` (articles only)

3. **Aggregated data**:
   - `complete_extraction.json` (all structured data, links, images, etc.)

4. **Metadata**:
   - `metadata.json` (crawl summary, pages array, page types)

5. **Dashboard payload**:
   - `dashboard_material.json` (summary for dashboard)

**Page Type Determination**:
- Uses `determine_standard_page_type()` function
- Maps URLs to 12 standard page types
- Falls back to path fragment for unknown pages

---

### 9. Main Entry Functions

#### `scrape_company(company: Dict, output_dir: Path, run_folder: str, max_pages: int = 200) -> Dict`
**Purpose**: Scrape one company comprehensively.

**Process**:
1. Create ComprehensiveCrawler instance
2. Call `crawl()` method
3. Return summary

---

#### `load_companies(seed_file: Path, company_ids: Optional[List[str]] = None) -> List[Dict]`
**Purpose**: Load companies from seed file.

**Process**:
1. Load JSON from seed file
2. Generate company_id from domain
3. Filter by company_ids if provided

**Returns**: List of company dictionaries.

---

#### `main_async(args)`
**Purpose**: Async main function.

**Process**:
1. Load companies
2. For each company:
   - Call `scrape_company()`
   - Collect results
   - Handle errors
3. Return all results

---

#### `main()`
**Purpose**: CLI entry point.

**Process**:
1. Parse command-line arguments
2. Set up logging
3. Call `main_async()`
4. Print summary
5. Save summary JSON

**Arguments**:
- `--seed-file`: Path to company seed file
- `--output-dir`: Output directory
- `--run-folder`: Subfolder name for this run
- `--companies`: Specific company IDs to scrape
- `--verbose`: Enable verbose logging
- `--max-pages`: Maximum pages per company (default: 30)

---

## End-to-End Flow

### 1. Initialization Phase

```
main()
  └─> Parse CLI arguments
  └─> main_async()
       └─> load_companies()
            └─> Load JSON, generate company_ids
       └─> For each company:
            └─> scrape_company()
                 └─> ComprehensiveCrawler.__init__()
                      ├─> Load company profile
                      ├─> Discover all 12 page types
                      │    ├─> _find_page_url() (HTTP HEAD requests)
                      │    └─> _discover_links_from_homepage()
                      └─> Initialize URL queues
```

### 2. Priority Content Fetching Phase

```
crawl()
  └─> Initialize Playwright browser
  └─> fetch_priority_content()
       ├─> Crawl all 12 page types systematically
       │    ├─> Navigate to page
       │    ├─> extract_complete_page_data()
       │    │    ├─> extract_all_metadata()
       │    │    ├─> extract_all_structured_data()
       │    │    ├─> extract_all_text_content()
       │    │    ├─> extract_all_links()
       │    │    ├─> extract_all_images()
       │    │    ├─> extract_all_forms()
       │    │    ├─> extract_all_tables()
       │    │    ├─> extract_all_scripts()
       │    │    └─> extract_navigation_structure()
       │    ├─> Apply structured extraction (investors, press, pricing, etc.)
       │    └─> Discover more URLs
       │
       ├─> Careers pages (jobs extraction)
       │    ├─> Use ATSExtractor.extract_jobs()
       │    ├─> Check for iframes (external ATS)
       │    ├─> Scroll to load dynamic content
       │    ├─> Click "Load More" buttons
       │    ├─> extract_jobs_from_all_sources() (comprehensive fallback)
       │    └─> Visit job detail pages
       │
       └─> News articles (RSS feeds)
            ├─> Find RSS feeds (NewsExtractor)
            ├─> Parse feed entries
            ├─> Fetch full article content
            └─> extract_news_article()
```

### 3. General Crawling Phase

```
crawl() (continued)
  └─> While URLs to visit:
       └─> crawl_page()
            ├─> Navigate with Playwright
            ├─> Check for errors (PDFs, 404, 500)
            ├─> Scroll/wait for dynamic content (priority pages)
            ├─> extract_complete_page_data()
            ├─> Error detection and retry
            ├─> Extract jobs (if careers page)
            ├─> Extract news article (if blog page)
            ├─> discover_urls() (find more URLs)
            └─> Add to visited set
```

### 4. Entity Extraction Phase

```
crawl() (continued)
  └─> extract_entities_from_data()
       ├─> Extract from page_data["extracted_jobs"]
       ├─> Extract from page_data["extracted_article"]
       ├─> Extract from JSON-LD (jobs, team, products, etc.)
       ├─> Extract from embedded JSON
       ├─> Extract team from HTML (all pages)
       ├─> Extract products from HTML
       ├─> Extract company info from HTML
       ├─> Extract customers/partners from HTML
       ├─> Extract funding events (from text patterns)
       ├─> Extract pricing (from pricing pages)
       ├─> Extract snapshot data (headcount, openings)
       ├─> Extract visibility data (GitHub, Glassdoor)
       └─> Deduplicate all entities
```

### 5. Results Saving Phase

```
crawl() (continued)
  └─> save_results()
       ├─> For each page:
       │    ├─> Determine page type
       │    ├─> Save HTML file
       │    ├─> Save clean text file
       │    └─> Save complete JSON
       │
       ├─> Save entities:
       │    ├─> extracted_entities.json
       │    ├─> all_jobs.json
       │    └─> all_news_articles.json
       │
       ├─> Save aggregated:
       │    └─> complete_extraction.json
       │
       ├─> Save metadata:
       │    └─> metadata.json (with pages array)
       │
       └─> Save dashboard payload:
            └─> dashboard_material.json
```

### 6. Summary Phase

```
main_async() (continued)
  └─> Collect all results
  └─> main()
       └─> Print summary
       └─> Save comprehensive_summary.json
```

---

## Key Concepts

### 1. Page Type Discovery

The scraper systematically discovers 12 standard page types:
- **homepage**: `/`
- **about**: `/about`, `/company`, `/about-us`
- **product**: `/product`, `/products`, `/platform`
- **careers**: `/careers`, `/jobs`, `/join-us`
- **blog**: `/blog`, `/news`, `/insights`
- **team**: `/team`, `/leadership`, `/people`
- **investors**: `/investors`, `/funding`, `/backed-by`
- **customers**: `/customers`, `/case-studies`
- **press**: `/press`, `/newsroom`, `/media`
- **pricing**: `/pricing`, `/plans`, `/price`
- **partners**: `/partners`, `/integrations`
- **contact**: `/contact`, `/contact-us`

**Discovery Methods**:
1. URL pattern matching (HTTP HEAD requests)
2. Homepage link analysis
3. URL path analysis during crawling

### 2. Priority System

**Priority URLs** (crawled first):
- Jobs pages (`/career`, `/job`)
- News/blog pages (`/blog`, `/news`)
- All 12 standard page types

**Regular URLs** (crawled after):
- About, team, product, pricing, etc.

**Skipped URLs**:
- Legal, privacy, terms
- Signup, login, account
- Search, archive, tags
- PDFs, images, downloads

### 3. Extraction Strategy

**Multi-Source Extraction**:
- **Structured Data**: JSON-LD, microdata, RDFa, Open Graph
- **HTML Patterns**: CSS selectors, text patterns
- **Embedded Data**: Script tags, iframes
- **External APIs**: ATS APIs, RSS feeds

**Fallback Chain**:
1. Try ATS extraction (fast)
2. Try comprehensive extraction (thorough)
3. Try pattern matching (flexible)

### 4. Error Handling

**Error Detection**:
- HTTP status codes (404, 500)
- Error message patterns in HTML
- Short content with error keywords

**Retry Strategy**:
- Client-side errors: Wait longer for JS rendering
- Network errors: Retry with longer timeout
- Failed pages: Marked and skipped in final results

### 5. Deduplication

**Job Deduplication**: By title + URL
**Article Deduplication**: By URL (or title fallback)
**Generic Deduplication**: By any specified field

### 6. Output Structure

```
output_dir/
  company_id/
    run_folder/
      homepage.html
      homepage_clean.txt
      homepage_complete.json
      about.html
      about_clean.txt
      about_complete.json
      ...
      extracted_entities.json
      all_jobs.json
      all_news_articles.json
      complete_extraction.json
      metadata.json
      dashboard_material.json
```

---

## Dependencies

### Core Libraries
- **Playwright**: JavaScript rendering, dynamic content
- **BeautifulSoup**: HTML parsing
- **trafilatura**: Clean text extraction
- **extruct**: Structured data extraction
- **requests**: HTTP requests
- **selectolax**: Fast HTML parsing

### Internal Modules
- **company_profiles**: Company-specific configuration
- **ats_extractor**: ATS job extraction
- **news_extractor**: RSS/news extraction

---

## Performance Optimizations

1. **Reduced Page Limit**: Default 30 pages (vs 200)
2. **Reduced Timeouts**: 15s (vs 30s)
3. **Minimal Waits**: 0.2-0.3s (vs 1-2s)
4. **Priority Crawling**: Jobs/news first
5. **Smart URL Filtering**: Skip low-value pages
6. **ATS API Extraction**: Fast job collection
7. **RSS Feed Extraction**: Fast news collection
8. **Parallel Processing**: Async/await for concurrent operations

---

## Usage Example

```bash
# Scrape all companies
python src/scraper_v2.py

# Scrape specific companies
python src/scraper_v2.py --companies anthropic baseten

# Custom output directory
python src/scraper_v2.py --output-dir /path/to/output

# Increase page limit
python src/scraper_v2.py --max-pages 50

# Verbose logging
python src/scraper_v2.py --verbose
```

---

## Output Files

### Per-Page Files
- `{page_type}.html`: Raw HTML
- `{page_type}_clean.txt`: Clean text
- `{page_type}_complete.json`: Complete page data (no HTML)

### Entity Files
- `extracted_entities.json`: All extracted entities
- `all_jobs.json`: Jobs only
- `all_news_articles.json`: News articles only

### Aggregated Files
- `complete_extraction.json`: All structured data, links, images
- `metadata.json`: Crawl summary, pages array, page types
- `dashboard_material.json`: Dashboard-friendly payload

---

## Error Handling

1. **Page Errors**: Detected and logged, retried if client-side
2. **Network Errors**: Retried with longer timeout
3. **Failed Pages**: Marked with `load_failed: true`, skipped in results
4. **Missing Dependencies**: Graceful fallback (e.g., Playwright warning)

---

## Future Enhancements

Potential improvements:
- Parallel company scraping
- Incremental crawling (only new pages)
- Better error recovery
- More ATS support
- More structured data formats
- Performance metrics tracking

