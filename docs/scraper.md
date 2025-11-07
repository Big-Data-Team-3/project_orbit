# Forbes AI50 Deep Web Scraper

A production-ready web scraper designed to extract comprehensive data from company websites. Built for scraping Forbes AI50 companies with support for 12 page types, blog post extraction, and structured data parsing.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
  - [Command Line Interface](#command-line-interface)
  - [Programmatic Usage](#programmatic-usage)
- [Configuration](#configuration)
- [Output Structure](#output-structure)
- [Page Types](#page-types)
- [Structured Data Extraction](#structured-data-extraction)
- [API Reference](#api-reference)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)

## Overview

The scraper is designed to systematically extract data from company websites, focusing on Forbes AI50 companies. It uses a smart HTTP-first approach with Playwright fallback for JavaScript-heavy sites, automatically discovers page URLs, and extracts both raw content and structured data.

### Key Capabilities

- **12 Page Types**: Homepage, About, Product, Careers, Blog, Team, Investors, Customers, Press, Pricing, Partners, Contact
- **Blog Post Extraction**: Automatically discovers and scrapes up to 20 individual blog posts per company
- **Structured Data Parsing**: Extracts HQ location, team members, investors, customers, pricing tiers, and partners
- **Change Detection**: Computes content hashes for tracking page changes over time
- **Smart Fallback**: HTTP requests first, automatically falls back to Playwright for blocked or JS-heavy sites
- **Rate Limiting**: Built-in rate limiting to respect server resources

## Features

### Performance
- **HTTP-First Approach**: Fast HTTP requests for most sites
- **Playwright Fallback**: Automatic fallback for JavaScript-heavy or blocked sites
- **Rate Limiting**: Configurable delays between requests (default: 2 seconds)
- **Retry Logic**: Automatic retries with exponential backoff

###  Smart Discovery
- **URL Pattern Matching**: Tries multiple common URL patterns for each page type
- **Homepage Link Analysis**: Discovers page URLs by analyzing homepage links
- **Blog Post Detection**: Automatically finds and extracts individual blog post URLs

### Data Extraction
- **Raw HTML**: Saves original HTML for each page
- **Clean Text**: Extracts readable text using trafilatura and BeautifulSoup
- **Structured Data**: Parses specific information (team, investors, pricing, etc.)
- **Content Hashing**: SHA256 hashes for change detection

### Reliability
- **Error Handling**: Graceful handling of missing pages, timeouts, and errors
- **Robots.txt Support**: Optional robots.txt checking
- **Timeout Management**: Configurable timeouts for requests
- **Comprehensive Logging**: Detailed logging for debugging and monitoring

## Installation

### Prerequisites

- Python 3.8+
- pip or uv package manager

### Required Dependencies

```bash
pip install requests beautifulsoup4 trafilatura lxml
```

### Optional Dependencies

For JavaScript-heavy sites, install Playwright:

```bash
pip install playwright
playwright install chromium
```

The scraper will work without Playwright, but will automatically fall back to it when needed (if installed).

### Verify Installation

```bash
python src/scraper.py --help
```

## Quick Start

### Basic Usage

Scrape all companies from the default seed file:

```bash
python src/scraper.py
```

### Scrape Specific Companies

```bash
python src/scraper.py --companies abridge anthropic harvey
```

### Custom Output Directory

```bash
python src/scraper.py --output-dir /path/to/output --run-folder daily_2025-01-15
```

## Usage

### Command Line Interface

The scraper provides a comprehensive CLI with multiple options:

#### Basic Options

```bash
python src/scraper.py [OPTIONS]
```

#### Available Options

| Option | Description | Default |
|--------|-------------|---------|
| `--seed-file` | Path to company seed file (JSON) | `data/forbes_ai50_seed.json` |
| `--output-dir` | Output directory for scraped data | `data/raw` |
| `--run-folder` | Subfolder name for this run | `initial_pull` |
| `--companies` | Specific company IDs to scrape (space-separated) | All companies |
| `--force-playwright` | Use Playwright for all requests | HTTP-first |
| `--respect-robots` | Respect robots.txt | Bypass (for academic use) |
| `--no-blog-posts` | Skip scraping individual blog posts | Enabled |
| `--max-blog-posts` | Maximum blog posts per company | 20 |
| `--verbose` | Enable verbose logging | INFO level |


### Programmatic Usage

You can also use the scraper as a Python module:

```python
from pathlib import Path
from src.scraper import scrape_company, load_companies

# Load companies
seed_file = Path("data/forbes_ai50_seed.json")
companies = load_companies(seed_file, company_ids=["abridge", "anthropic"])

# Scrape a company
output_dir = Path("data/raw")
for company in companies:
    result = scrape_company(
        company=company,
        output_dir=output_dir,
        run_folder="initial_pull",
        force_playwright=False,
        respect_robots=True,
        scrape_blog_posts=True,
        max_blog_posts=20
    )
    print(f"{company['company_name']}: {result['pages_scraped']} pages scraped")
```

## Configuration

### Seed File Format

The seed file should be a JSON array of company objects:

```json
[
  {
    "company_name": "Abridge",
    "website": "https://www.abridge.com"
  },
  {
    "company_name": "Anthropic",
    "website": "https://www.anthropic.com"
  }
]
```

The scraper automatically generates `company_id` from the website domain (e.g., "abridge" from "www.abridge.com").

### Scraper Configuration

You can modify these constants in `src/scraper.py`:

```python
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
REQUEST_DELAY = 2          # Seconds between requests per domain
REQUEST_TIMEOUT = 10        # HTTP request timeout (seconds)
MAX_RETRIES = 3             # Maximum retry attempts
PLAYWRIGHT_TIMEOUT = 15000  # Playwright timeout (milliseconds)
```

### Page Patterns

The scraper uses predefined URL patterns for each page type. You can modify `PAGE_PATTERNS` in `src/scraper.py` to add custom patterns:

```python
PAGE_PATTERNS = {
    "homepage": ["/"],
    "about": ["/about", "/company", "/about-us", "/who-we-are"],
    "product": ["/product", "/products", "/platform", "/solutions"],
    # ... add more patterns
}
```

## Output Structure

The scraper organizes output in a hierarchical directory structure:

```
data/raw/
├── abridge/
│   └── initial_pull/
│       ├── homepage.html
│       ├── homepage_clean.txt
│       ├── about.html
│       ├── about_clean.txt
│       ├── about_structured.json
│       ├── product.html
│       ├── product_clean.txt
│       ├── blog.html
│       ├── blog_clean.txt
│       ├── blog_posts/
│       │   ├── post_abc123.html
│       │   ├── post_abc123_clean.txt
│       │   ├── post_def456.html
│       │   └── post_def456_clean.txt
│       ├── team.html
│       ├── team_clean.txt
│       ├── team_structured.json
│       ├── investors.html
│       ├── investors_structured.json
│       ├── customers.html
│       ├── customers_structured.json
│       ├── pricing.html
│       ├── pricing_structured.json
│       ├── partners.html
│       ├── partners_structured.json
│       └── metadata.json
└── anthropic/
    └── initial_pull/
        └── ...
```

### File Types

- **`*.html`**: Raw HTML content for each page
- **`*_clean.txt`**: Extracted clean text (readable, no HTML)
- **`*_structured.json`**: Parsed structured data (for specific page types)
- **`metadata.json`**: Scraping metadata including timestamps, hashes, and status

### Metadata File

Each company directory contains a `metadata.json` file with scraping information:

```json
{
  "company_name": "Abridge",
  "company_id": "abridge",
  "scrape_timestamp": "2025-01-15T10:30:00Z",
  "scraper_version": "3.0-airflow",
  "run_folder": "initial_pull",
  "force_playwright": false,
  "respect_robots": true,
  "pages": [
    {
      "page_type": "homepage",
      "source_url": "https://www.abridge.com",
      "crawled_at": "2025-01-15T10:30:05Z",
      "status_code": 200,
      "content_length": 125430,
      "content_hash": "a1b2c3d4...",
      "found": true,
      "note": "HTTP Success",
      "method": "http",
      "has_structured_data": false
    }
  ]
}
```

### Results Summary

After scraping completes, a summary file is created:

```
data/scraping_results_initial_pull.json
```

This file contains:
- Overall statistics (total companies, successful, failed)
- Total pages/posts scraped
- Average pages per company
- Elapsed time
- Per-company results

## Page Types

The scraper attempts to scrape 12 different page types for each company:

| Page Type | Description | Structured Data |
|-----------|-------------|-----------------|
| `homepage` | Company homepage | No |
| `about` | About/Company page | HQ location, founding year |
| `product` | Product/Platform page | No |
| `careers` | Careers/Jobs page | No |
| `blog` | Blog/News index page | No |
| `team` | Team/Leadership page | Team members (name, role, bio, LinkedIn) |
| `investors` | Investors/Funding page | Investor names, funding rounds |
| `customers` | Customers/Case studies | Customer names |
| `press` | Press/Newsroom page | No |
| `pricing` | Pricing/Plans page | Pricing model, tiers |
| `partners` | Partners/Integrations | Partner names |
| `contact` | Contact page | HQ location |

### Blog Posts

When a blog page is found, the scraper:
1. Extracts individual blog post URLs from the blog index page
2. Scrapes up to 20 most recent posts (configurable)
3. Saves each post as `post_{hash}.html` and `post_{hash}_clean.txt` in the `blog_posts/` subdirectory

## Structured Data Extraction

The scraper automatically extracts structured data from specific page types:

### About/Contact Pages
- **HQ Location**: City, state, country
- **Founded Year**: Year the company was founded

### Team Page
- **Team Members**: Array of objects with:
  - `name`: Team member name
  - `role`: Job title/role
  - `bio`: Biography text
  - `linkedin`: LinkedIn profile URL

### Investors Page
- **Funding Rounds**: Mentions of seed, Series A/B/C, etc.
- **Funding Amounts**: Extracted funding amounts
- **Investor Names**: List of investor/backer names

### Customers Page
- **Customer Names**: List of customer/client company names

### Pricing Page
- **Pricing Model**: `per-seat`, `usage-based`, or `enterprise`
- **Tiers**: Array of pricing tiers with names and prices

### Partners Page
- **Partner Names**: List of integration/partner company names

## API Reference

### Main Functions

#### `scrape_company(company, output_dir, run_folder, ...)`

Main scraping function for a single company.

**Parameters:**
- `company` (Dict): Company dict with `company_name`, `website`, `company_id`
- `output_dir` (Path): Base output directory
- `run_folder` (str): Subfolder name for this run
- `force_playwright` (bool): Use Playwright for all requests
- `respect_robots` (bool): Check robots.txt
- `scrape_blog_posts` (bool): Extract and scrape blog posts
- `max_blog_posts` (int): Maximum blog posts to scrape

**Returns:**
- `Dict`: Results with `status`, `pages_scraped`, `pages_total`, etc.

#### `load_companies(seed_file, company_ids=None)`

Load companies from seed file.

**Parameters:**
- `seed_file` (Path): Path to JSON seed file
- `company_ids` (List[str], optional): Filter to specific company IDs

**Returns:**
- `List[Dict]`: List of company dictionaries

#### `fetch_page_smart(url, force_playwright=False)`

Smart page fetching with automatic fallback.

**Parameters:**
- `url` (str): URL to fetch
- `force_playwright` (bool): Force Playwright usage

**Returns:**
- `Tuple[Optional[str], int, str]`: (HTML content, status_code, note)

### Utility Functions

- `compute_content_hash(html)`: Compute SHA256 hash of HTML
- `check_robots_txt(base_url)`: Check if scraping is allowed
- `find_page_url(base_url, page_type)`: Find URL for a page type
- `extract_clean_text(html)`: Extract clean text from HTML
- `discover_links_from_homepage(homepage_html, base_url)`: Discover page URLs from homepage
- `extract_blog_post_links(blog_html, base_url, limit=20)`: Extract blog post URLs

### Parsing Functions

- `parse_footer(html)`: Extract HQ and founding year
- `parse_team_page(html)`: Extract team members
- `parse_investors_page(html)`: Extract investor information
- `parse_customers_page(html)`: Extract customer names
- `parse_pricing_page(html)`: Extract pricing information
- `parse_partners_page(html)`: Extract partner names


## Troubleshooting

### Common Issues

#### 1. Playwright Not Available

**Error:** `Playwright not available`

**Solution:**
```bash
pip install playwright
playwright install chromium
```

#### 2. Pages Not Found

**Issue:** Some page types return "Not found"

**Explanation:** This is normal. Not all companies have all 12 page types. The scraper will try multiple URL patterns and link discovery, but some pages may not exist.

**Solution:** Check the `metadata.json` file to see which pages were found and which were not.

#### 3. Rate Limiting / 403 Errors

**Issue:** Getting 403 Forbidden or 429 Too Many Requests

**Solution:**
- Increase `REQUEST_DELAY` in the code (default: 2 seconds)
- Use `--force-playwright` flag (Playwright may bypass some blocks)
- Check if the site requires authentication or has anti-bot measures

#### 4. Timeout Errors

**Issue:** Requests timing out

**Solution:**
- Increase `REQUEST_TIMEOUT` or `PLAYWRIGHT_TIMEOUT` in the code
- Use `--force-playwright` for slow-loading JS sites
- Check your internet connection

#### 5. Missing Dependencies

**Error:** `ModuleNotFoundError`

**Solution:**
```bash
pip install -r requirements.txt
```

#### 6. Robots.txt Blocking

**Issue:** Scraper reports "blocked by robots.txt"

**Solution:**
- Use `--respect-robots` flag is OFF by default (bypasses robots.txt)
- If you need to respect robots.txt, the scraper will skip blocked sites

### Debugging Tips

1. **Enable Verbose Logging:**
   ```bash
   python src/scraper.py --verbose
   ```

2. **Check Metadata Files:**
   - Review `metadata.json` in each company directory
   - Check status codes and error messages

3. **Test Single Company:**
   ```bash
   python src/scraper.py --companies abridge --verbose
   ```

4. **Inspect Output:**
   - Check HTML files to see what was actually scraped
   - Review `*_clean.txt` files for extracted text quality
   - Check `*_structured.json` for parsed data

5. **Check Results Summary:**
   - Review `scraping_results_{run_folder}.json` for overall statistics
   - Identify which companies failed and why

## Contributing

When modifying the scraper:

1. **Add New Page Types:** Update `PAGE_PATTERNS` dictionary
2. **Add Structured Parsing:** Create new `parse_*_page()` function
3. **Modify Discovery:** Update `discover_links_from_homepage()` function
4. **Change Configuration:** Modify constants at the top of the file

## License

See the main repository LICENSE file.

## Support

For issues, questions, or contributions, please open an issue on GitHub.

