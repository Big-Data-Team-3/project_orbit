#!/usr/bin/env python3
"""
Forbes AI50 Comprehensive Scraper - Fast & Complete Data Extraction

OPTIMIZED FOR SPEED:
- Default max_pages: 30 (was 200) - focuses on essential pages
- Reduced timeouts: 15s (was 30s) for faster page loads
- Smart URL filtering: Skips low-value pages (legal, docs, etc.)
- Priority crawling: Jobs and news pages first
- Minimal waits: 0.2-0.3s delays (was 1-2s)
- ATS API extraction: Fast job collection via Greenhouse/Lever/Ashby APIs
- RSS feed extraction: Fast news collection via RSS/Atom feeds

Extracts ALL details from company websites:
- All structured data (Schema.org, JSON-LD, microdata, embedded JSON)
- All text content (with semantic structure)
- All links and navigation
- All images and media
- All forms and interactive elements
- All tables and structured content
- All metadata (Open Graph, Twitter Cards, etc.)
- All scripts and embedded data
- Complete page hierarchy and sitemap

NO HARDCODING - Dynamic pattern detection and extraction
"""

import asyncio
import hashlib
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Any, Tuple
from urllib.parse import urlparse, urljoin, parse_qs
from collections import defaultdict
import argparse
# Core libraries
import requests
import trafilatura
from bs4 import BeautifulSoup
from selectolax.parser import HTMLParser
import extruct
import xml.etree.ElementTree as ET

try:
    from company_profiles import get_company_profile
except ImportError:
    from src.company_profiles import get_company_profile

try:
    from ats_extractor import ATSExtractor
    from news_extractor import NewsExtractor
except ImportError:
    from src.ats_extractor import ATSExtractor
    from src.news_extractor import NewsExtractor

# Playwright for JavaScript rendering
try:
    from playwright.async_api import async_playwright, Browser, Page, BrowserContext, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logging.warning("Playwright not available. Install with: pip install playwright && playwright install")

SCRAPER_VERSION = "5.0-enterprise-ats"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Timeout configuration (in milliseconds)
NAVIGATION_TIMEOUT = 60000  # 60 seconds for page navigation
PRIORITY_PAGE_TIMEOUT = 60000  # 60 seconds for priority pages
CAREERS_PAGE_TIMEOUT = 60000  # 60 seconds for careers pages (can be slow)
JOB_PAGE_TIMEOUT = 40000  # 40 seconds for individual job pages
NETWORK_IDLE_TIMEOUT = 20000  # 20 seconds for network idle wait

# Page patterns - All 12 page types from scraper.py
PAGE_PATTERNS = {
    "homepage": ["/"],
    "about": ["/about", "/company", "/about-us", "/who-we-are", "/our-story"],
    "product": ["/product", "/products", "/platform", "/solutions", "/features"],
    "careers": ["/careers", "/jobs", "/join-us", "/work-with-us"],
    "blog": ["/blog", "/news", "/press", "/newsroom", "/insights", "/resources"],
    "team": ["/team", "/leadership", "/about/team", "/about/leadership", "/people", "/our-team"],
    "investors": ["/investors", "/funding", "/about/investors", "/backed-by", "/backers"],
    "customers": ["/customers", "/case-studies", "/success-stories", "/testimonials", "/customer-stories"],
    "press": ["/press", "/newsroom", "/media", "/news-and-press", "/press-releases"],
    "pricing": ["/pricing", "/plans", "/price", "/buy", "/purchase"],
    "partners": ["/partners", "/integrations", "/ecosystem", "/partner", "/integration"],
    "contact": ["/contact", "/contact-us", "/get-in-touch", "/reach-us"]
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)


# ============================================================================
# ATS DOMAIN DETECTION
# ============================================================================

def is_ats_domain(url: str) -> bool:
    """Check if URL is from a known ATS domain (allow crawling external ATS)"""
    ats_domains = [
        'greenhouse.io', 'lever.co', 'workable.com', 'ashbyhq.com', 'bamboohr.com',
        'icims.com', 'workday.com', 'oracle.com', 'taleo.net', 'smartrecruiters.com',
        'jobvite.com', 'recruiterbox.com', 'zoho.com', 'bullhorn.com', 'jobscore.com',
        'recruitee.com', 'personio.com', 'bamboohr.com', 'paycom.com', 'adp.com'
    ]
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    return any(ats_domain in netloc for ats_domain in ats_domains)


# ============================================================================
# COMPREHENSIVE DATA EXTRACTION FUNCTIONS
# ============================================================================

def extract_all_structured_data(html: str, url: str) -> Dict[str, Any]:
    """Extract ALL structured data formats"""
    structured = {
        "json_ld": [],
        "microdata": [],
        "rdfa": [],
        "opengraph": {},
        "twitter_cards": {},
        "schema_org": [],
        "embedded_json": []
    }
    
    try:
        # Use extruct for standard formats
        data = extruct.extract(html, base_url=url, syntaxes=['json-ld', 'microdata', 'rdfa'], errors='ignore')
        structured["json_ld"] = data.get('json-ld', [])
        structured["microdata"] = data.get('microdata', [])
        structured["rdfa"] = data.get('rdfa', [])
        
        # Extract Schema.org types
        for item in structured["json_ld"]:
            if isinstance(item, dict) and '@type' in item:
                structured["schema_org"].append(item)
        
        # Extract Open Graph
        soup = BeautifulSoup(html, 'lxml')
        for meta in soup.find_all('meta', property=lambda x: x and x.startswith('og:')):
            key = meta.get('property', '').replace('og:', '')
            structured["opengraph"][key] = meta.get('content', '')
        
        # Extract Twitter Cards
        for meta in soup.find_all('meta', attrs={'name': re.compile(r'^twitter:')}):
            key = meta.get('name', '').replace('twitter:', '')
            structured["twitter_cards"][key] = meta.get('content', '')
        
        # Extract embedded JSON from script tags
        for script in soup.find_all('script', type='application/json'):
            try:
                if script.string:
                    data = json.loads(script.string)
                    structured["embedded_json"].append(data)
            except:
                pass
        
        # Try to extract JSON from other script tags
        for script in soup.find_all('script'):
            if not script.string:
                continue
            script_text = script.string.strip()
            if script_text.startswith('{') or script_text.startswith('['):
                try:
                    data = json.loads(script_text)
                    structured["embedded_json"].append(data)
                except:
                    pass
        
    except Exception as e:
        logger.debug(f"Structured data extraction error: {e}")
    
    return structured


def extract_all_links(html: str, base_url: str) -> List[Dict[str, Any]]:
    """Extract ALL links with metadata"""
    links = []
    soup = BeautifulSoup(html, 'lxml')
    parsed_base = urlparse(base_url)
    
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        
        link_data = {
            "href": href,
            "full_url": full_url,
            "text": link.get_text(strip=True),
            "title": link.get('title', ''),
            "is_external": parsed.netloc != parsed_base.netloc if parsed.netloc else False,
            "is_same_domain": parsed.netloc == parsed_base.netloc if parsed.netloc else True,
            "anchor_text": link.get_text(strip=True),
            "rel": link.get('rel', []),
            "target": link.get('target', ''),
            "classes": link.get('class', [])
        }
        
        # Categorize link
        href_lower = href.lower()
        if any(kw in href_lower for kw in ['/career', '/job', '/join']):
            link_data["category"] = "careers"
        elif any(kw in href_lower for kw in ['/about', '/company']):
            link_data["category"] = "about"
        elif any(kw in href_lower for kw in ['/blog', '/news', '/post']):
            link_data["category"] = "blog"
        elif any(kw in href_lower for kw in ['/team', '/leadership']):
            link_data["category"] = "team"
        elif any(kw in href_lower for kw in ['/product', '/platform']):
            link_data["category"] = "product"
        elif any(kw in href_lower for kw in ['/pricing', '/plans']):
            link_data["category"] = "pricing"
        elif any(kw in href_lower for kw in ['/contact']):
            link_data["category"] = "contact"
        else:
            link_data["category"] = "other"
        
        links.append(link_data)
    
    return links


def extract_all_images(html: str, base_url: str) -> List[Dict[str, Any]]:
    """Extract ALL images with metadata"""
    images = []
    soup = BeautifulSoup(html, 'lxml')
    
    for img in soup.find_all('img'):
        src = img.get('src', '') or img.get('data-src', '') or img.get('data-lazy-src', '')
        if not src:
            continue
        
        full_url = urljoin(base_url, src)
        
        image_data = {
            "src": src,
            "full_url": full_url,
            "alt": img.get('alt', ''),
            "title": img.get('title', ''),
            "width": img.get('width', ''),
            "height": img.get('height', ''),
            "loading": img.get('loading', ''),
            "classes": img.get('class', []),
            "is_logo": any(kw in (img.get('alt', '') + ' ' + ' '.join(img.get('class', []))).lower() 
                          for kw in ['logo', 'brand', 'company'])
        }
        images.append(image_data)
    
    return images


def extract_all_forms(html: str, base_url: str) -> List[Dict[str, Any]]:
    """Extract ALL forms with fields"""
    forms = []
    soup = BeautifulSoup(html, 'lxml')
    
    for form in soup.find_all('form'):
        form_data = {
            "action": form.get('action', ''),
            "method": form.get('method', 'GET').upper(),
            "id": form.get('id', ''),
            "name": form.get('name', ''),
            "classes": form.get('class', []),
            "fields": []
        }
        
        # Extract all input fields
        for input_elem in form.find_all(['input', 'textarea', 'select']):
            field_data = {
                "type": input_elem.get('type', input_elem.name),
                "name": input_elem.get('name', ''),
                "id": input_elem.get('id', ''),
                "placeholder": input_elem.get('placeholder', ''),
                "label": '',
                "required": input_elem.has_attr('required'),
                "value": input_elem.get('value', '')
            }
            
            # Try to find associated label
            if field_data["id"]:
                label = soup.find('label', {'for': field_data["id"]})
                if label:
                    field_data["label"] = label.get_text(strip=True)
            
            form_data["fields"].append(field_data)
        
        forms.append(form_data)
    
    return forms


def extract_all_tables(html: str) -> List[Dict[str, Any]]:
    """Extract ALL tables with data"""
    tables = []
    soup = BeautifulSoup(html, 'lxml')
    
    for table in soup.find_all('table'):
        table_data = {
            "headers": [],
            "rows": [],
            "caption": '',
            "id": table.get('id', ''),
            "classes": table.get('class', [])
        }
        
        # Extract caption
        caption = table.find('caption')
        if caption:
            table_data["caption"] = caption.get_text(strip=True)
        
        # Extract headers
        thead = table.find('thead')
        first_row = None
        has_thead = thead is not None
        
        if thead:
            for th in thead.find_all(['th', 'td']):
                table_data["headers"].append(th.get_text(strip=True))
        else:
            # Try first row as headers
            first_row = table.find('tr')
            if first_row:
                for th in first_row.find_all(['th', 'td']):
                    table_data["headers"].append(th.get_text(strip=True))
        
        # Extract rows
        tbody = table.find('tbody') or table
        for tr in tbody.find_all('tr'):
            # Skip header row if we used first_row as header (and no thead exists)
            if not has_thead and first_row is not None:
                try:
                    if tr == first_row:
                        continue  # Skip header row
                except:
                    pass  # If comparison fails, just continue
            row = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
            if row:
                table_data["rows"].append(row)
        
        if table_data["rows"]:
            tables.append(table_data)
    
    return tables


def extract_all_metadata(html: str) -> Dict[str, Any]:
    """Extract ALL metadata"""
    metadata = {
        "title": "",
        "description": "",
        "keywords": [],
        "author": "",
        "language": "",
        "viewport": "",
        "charset": "",
        "canonical": "",
        "robots": "",
        "meta_tags": {}
    }
    
    soup = BeautifulSoup(html, 'lxml')
    
    # Title
    title_tag = soup.find('title')
    if title_tag:
        metadata["title"] = title_tag.get_text(strip=True)
    
    # Meta tags
    for meta in soup.find_all('meta'):
        name = meta.get('name', '') or meta.get('property', '') or meta.get('http-equiv', '')
        content = meta.get('content', '')
        
        if name:
            if name.lower() == 'description':
                metadata["description"] = content
            elif name.lower() == 'keywords':
                metadata["keywords"] = [k.strip() for k in content.split(',')]
            elif name.lower() == 'author':
                metadata["author"] = content
            elif name.lower() == 'viewport':
                metadata["viewport"] = content
            elif name.lower() == 'robots':
                metadata["robots"] = content
            else:
                metadata["meta_tags"][name] = content
    
    # Language
    html_tag = soup.find('html')
    if html_tag:
        metadata["language"] = html_tag.get('lang', '')
    
    # Charset
    charset_tag = soup.find('meta', charset=True)
    if charset_tag:
        metadata["charset"] = charset_tag.get('charset', '')
    
    # Canonical
    canonical = soup.find('link', rel='canonical')
    if canonical:
        metadata["canonical"] = canonical.get('href', '')
    
    return metadata


def extract_all_text_content(html: str) -> Dict[str, Any]:
    """Extract all text content with structure"""
    text_data = {
        "full_text": "",
        "headings": [],
        "paragraphs": [],
        "lists": [],
        "quotes": [],
        "code_blocks": []
    }
    
    try:
        # Use trafilatura for clean text extraction
        clean_text = trafilatura.extract(html, include_comments=False, include_tables=True)
        if clean_text:
            text_data["full_text"] = clean_text
    except:
        pass
    
    soup = BeautifulSoup(html, 'lxml')
    
    # Extract headings with hierarchy
    for level in range(1, 7):
        for heading in soup.find_all(f'h{level}'):
            text_data["headings"].append({
                "level": level,
                "text": heading.get_text(strip=True),
                "id": heading.get('id', ''),
                "classes": heading.get('class', [])
            })
    
    # Extract paragraphs
    for p in soup.find_all('p'):
        text = p.get_text(strip=True)
        if text and len(text) > 10:
            text_data["paragraphs"].append(text)
    
    # Extract lists
    for ul in soup.find_all(['ul', 'ol']):
        items = [li.get_text(strip=True) for li in ul.find_all('li')]
        if items:
            text_data["lists"].append({
                "type": ul.name,
                "items": items
            })
    
    # Extract quotes
    for blockquote in soup.find_all('blockquote'):
        text_data["quotes"].append(blockquote.get_text(strip=True))
    
    # Extract code blocks
    for code in soup.find_all(['code', 'pre']):
        text_data["code_blocks"].append(code.get_text())
    
    return text_data


def extract_embedded_json_recursive(data: Any, results: List[Dict] = None) -> List[Dict]:
    """Recursively extract all JSON objects that might contain structured data"""
    if results is None:
        results = []
    
    if isinstance(data, dict):
        # Check if this looks like structured data
        if any(key in data for key in ['title', 'name', 'description', 'url', 'type', '@type']):
            results.append(data)
        
        # Recurse
        for value in data.values():
            extract_embedded_json_recursive(value, results)
    
    elif isinstance(data, list):
        for item in data:
            extract_embedded_json_recursive(item, results)
    
    return results


def extract_jobs_from_all_sources(html: str, url: str) -> List[Dict[str, Any]]:
    """Comprehensive job extraction from ALL possible sources"""
    jobs = []
    soup = BeautifulSoup(html, 'lxml')
    
    # 1. JSON-LD JobPosting
    structured = extract_all_structured_data(html, url)
    for item in structured["json_ld"]:
        if isinstance(item, dict) and item.get("@type") == "JobPosting":
            job = {
                "title": item.get("title"),
                "description": item.get("description"),
                "location": item.get("jobLocation", {}).get("name") if isinstance(item.get("jobLocation"), dict) else str(item.get("jobLocation", "")),
                "employmentType": item.get("employmentType"),
                "datePosted": item.get("datePosted"),
                "validThrough": item.get("validThrough"),
                "baseSalary": item.get("baseSalary"),
                "hiringOrganization": item.get("hiringOrganization", {}).get("name") if isinstance(item.get("hiringOrganization"), dict) else item.get("hiringOrganization"),
                "source": "json_ld",
                "url": item.get("url") or url
            }
            jobs.append(job)
    
    # 2. Embedded JSON - Greenhouse format
    for script in soup.find_all('script'):
        if not script.string:
            continue
        script_text = script.string.strip()
        
        # Look for Greenhouse data
        if 'greenhouse' in script_text.lower() or 'jobs' in script_text.lower():
            # Try to extract JSON
            try:
                # Find JSON objects
                json_matches = re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', script_text, re.DOTALL)
                for match in json_matches:
                    try:
                        json_data = json.loads(match.group(0))
                        # Recursively search for jobs
                        found_jobs = find_jobs_in_embedded_data(json_data)
                        jobs.extend(found_jobs)
                    except:
                        pass
            except:
                pass
    
    # 3. Embedded JSON - Generic job structures
    for json_data in structured["embedded_json"]:
        found_jobs = find_jobs_in_embedded_data(json_data)
        jobs.extend(found_jobs)
    
    # 4. HTML pattern matching - job cards/listings (MORE AGGRESSIVE)
    tree = HTMLParser(html)
    
    # Common job listing selectors (expanded)
    job_selectors = [
        '.job-listing', '.job-card', '.job-item', '.position',
        '.opening', '.role', '[data-job]', '[data-position]',
        '.careers-item', '.job-post', 'article.job', '.job-opening',
        '[class*="job"]', '[class*="position"]', '[class*="opening"]',
        '[class*="role"]', '[id*="job"]', '[id*="position"]',
        'li[class*="job"]', 'div[class*="job"]', 'article[class*="job"]'
    ]
    
    found_pattern = False
    for selector in job_selectors:
        try:
            elements = tree.css(selector)
            if len(elements) >= 1:  # Even single job element is valid
                for elem in elements:
                    job = extract_job_from_element(elem, url)
                    if job and job.get('title'):
                        jobs.append(job)
                if len(elements) >= 2:  # Found multiple, likely a listing page
                    found_pattern = True
        except:
            continue
    
    # If no pattern found, try more generic approaches
    if not found_pattern and not jobs:
        # Look for any links that might be jobs
        for link in soup.find_all('a', href=True):
            href = link.get('href', '').lower()
            text = link.get_text(strip=True)
            # Check if link text looks like a job title
            if (any(kw in href for kw in ['/job/', '/position/', '/opening/', '/career/', '/role/']) or
                (text and 10 < len(text) < 150 and 
                 any(kw in text.lower() for kw in ['engineer', 'manager', 'developer', 'analyst', 'designer', 'scientist', 'director', 'lead', 'senior', 'junior']))):
                job = {
                    "title": text,
                    "url": urljoin(url, link['href']),
                    "source": "link_heuristic"
                }
                jobs.append(job)
    
    # 5. Table-based job listings
    for table in soup.find_all('table'):
        headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
        if any(h in headers for h in ['title', 'position', 'role', 'location', 'department']):
            for row in table.find_all('tr')[1:]:  # Skip header
                cells = [td.get_text(strip=True) for td in row.find_all('td')]
                if cells and len(cells) >= 2:
                    job = {
                        "title": cells[0] if len(cells) > 0 else None,
                        "location": cells[1] if len(cells) > 1 else None,
                        "department": cells[2] if len(cells) > 2 else None,
                        "source": "table",
                        "url": url
                    }
                    # Try to find link
                    link = row.find('a', href=True)
                    if link:
                        job["url"] = urljoin(url, link['href'])
                    jobs.append(job)
    
    # 6. Link-based extraction (job detail pages)
    url_lower = url.lower()
    if any(kw in url_lower for kw in ['/career', '/job', '/openings', '/positions']):
        for link in soup.find_all('a', href=True):
            href = link.get('href', '').lower()
            link_text = link.get_text(strip=True)
            
            # Check if this looks like a job link
            if any(kw in href for kw in ['/job/', '/position/', '/opening/', '/career/']):
                if link_text and 10 < len(link_text) < 150:
                    job = {
                        "title": link_text,
                        "url": urljoin(url, link['href']),
                        "source": "link_pattern",
                        "page_url": url
                    }
                    jobs.append(job)
    
    return jobs


def find_jobs_in_embedded_data(data: Any, jobs: List[Dict] = None) -> List[Dict]:
    """Recursively find job objects in nested data structures"""
    if jobs is None:
        jobs = []
    
    if isinstance(data, dict):
        # Check if this is a job object (multiple patterns)
        is_job = False
        job = {}
        
        # Pattern 1: Standard job fields
        if 'title' in data and ('location' in data or 'jobLocation' in data):
            is_job = True
            job = {
                "title": data.get("title"),
                "location": data.get("location") or (data.get("jobLocation", {}).get("name") if isinstance(data.get("jobLocation"), dict) else data.get("jobLocation")),
                "department": data.get("department") or (data.get("departments", [{}])[0].get("name") if data.get("departments") else None),
                "url": data.get("url") or data.get("absolute_url") or data.get("jobUrl"),
                "description": data.get("description") or data.get("content"),
                "employmentType": data.get("employmentType") or data.get("type"),
                "datePosted": data.get("datePosted") or data.get("first_published") or data.get("posted_date"),
                "requisition_id": data.get("requisition_id") or data.get("id"),
                "source": "embedded_json"
            }
        
        # Pattern 2: Greenhouse format
        elif data.get("absolute_url") and data.get("title"):
            is_job = True
            location = data.get("location", {})
            job = {
                "title": data.get("title"),
                "location": location.get("name") if isinstance(location, dict) else str(location),
                "department": data.get("departments", [{}])[0].get("name") if data.get("departments") else None,
                "url": data.get("absolute_url"),
                "requisition_id": data.get("id"),
                "datePosted": data.get("first_published"),
                "source": "greenhouse_json"
            }
        
        # Pattern 3: Lever format
        elif data.get("text") and data.get("hostedUrl"):
            is_job = True
            job = {
                "title": data.get("text"),
                "location": data.get("categories", {}).get("location") if isinstance(data.get("categories"), dict) else None,
                "department": data.get("categories", {}).get("team") if isinstance(data.get("categories"), dict) else None,
                "url": data.get("hostedUrl"),
                "source": "lever_json"
            }
        
        if is_job and job.get("title"):
            jobs.append(job)
        
        # Recurse into dict values
        for value in data.values():
            find_jobs_in_embedded_data(value, jobs)
    
    elif isinstance(data, list):
        for item in data:
            find_jobs_in_embedded_data(item, jobs)
    
    return jobs


def extract_job_from_element(elem, base_url: str) -> Optional[Dict]:
    """Extract job data from an HTML element"""
    job = {
        "title": None,
        "location": None,
        "department": None,
        "url": None,
        "description": None,
        "source": "html_element"
    }
    
    # Title
    for selector in ['h2', 'h3', 'h4', '.title', '.job-title', '[class*="title"]', 'strong', 'a']:
        title_elem = elem.css_first(selector)
        if title_elem:
            title_text = title_elem.text().strip()
            if title_text and 5 < len(title_text) < 200:
                job["title"] = title_text
                # Check if it's a link
                if selector == 'a' or title_elem.tag == 'a':
                    job["url"] = urljoin(base_url, title_elem.attributes.get('href', ''))
                break
    
    # Location
    for selector in ['.location', '[class*="location"]', '[data-location]']:
        loc_elem = elem.css_first(selector)
        if loc_elem:
            job["location"] = loc_elem.text().strip()
            break
    
    # Department
    for selector in ['.department', '[class*="department"]', '[class*="team"]']:
        dept_elem = elem.css_first(selector)
        if dept_elem:
            job["department"] = dept_elem.text().strip()
            break
    
    # Description
    desc_elem = elem.css_first('p, .description, [class*="description"]')
    if desc_elem:
        job["description"] = desc_elem.text().strip()[:500]  # Limit length
    
    # URL from link
    link_elem = elem.css_first('a[href]')
    if link_elem and not job["url"]:
        job["url"] = urljoin(base_url, link_elem.attributes.get('href', ''))
    
    return job if job["title"] else None


def extract_news_article(html: str, url: str) -> Dict[str, Any]:
    """Extract complete news/blog article data"""
    article = {
        "url": url,
        "title": "",
        "author": "",
        "date_published": "",
        "date_modified": "",
        "content": "",
        "excerpt": "",
        "categories": [],
        "tags": [],
        "images": [],
        "word_count": 0,
        "reading_time": 0
    }
    
    soup = BeautifulSoup(html, 'lxml')
    
    # 1. Extract from JSON-LD Article
    structured = extract_all_structured_data(html, url)
    for item in structured["json_ld"]:
        if isinstance(item, dict) and item.get("@type") in ["Article", "BlogPosting", "NewsArticle"]:
            article["title"] = item.get("headline") or item.get("name") or article["title"]
            article["author"] = item.get("author", {}).get("name") if isinstance(item.get("author"), dict) else item.get("author", "")
            article["date_published"] = item.get("datePublished", "")
            article["date_modified"] = item.get("dateModified", "")
            article["excerpt"] = item.get("description", "")
            if item.get("image"):
                if isinstance(item["image"], str):
                    article["images"].append(item["image"])
                elif isinstance(item["image"], list):
                    article["images"].extend(item["image"])
    
    # 2. Extract from Open Graph
    if structured["opengraph"]:
        if not article["title"]:
            article["title"] = structured["opengraph"].get("title", "")
        if not article["excerpt"]:
            article["excerpt"] = structured["opengraph"].get("description", "")
        if structured["opengraph"].get("image"):
            article["images"].append(structured["opengraph"]["image"])
    
    # 3. Extract from HTML meta tags
    meta = extract_all_metadata(html)
    if not article["title"]:
        article["title"] = meta["title"]
    if not article["excerpt"]:
        article["excerpt"] = meta["description"]
    
    # 4. Extract article content
    # Try article tag first
    article_tag = soup.find('article')
    if article_tag:
        # Remove script and style tags
        for tag in article_tag.find_all(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        article["content"] = article_tag.get_text(separator='\n', strip=True)
    else:
        # Try common content selectors
        content_selectors = [
            '.post-content', '.article-content', '.entry-content',
            '.blog-content', '.news-content', 'main', '.content'
        ]
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                for tag in content_elem.find_all(['script', 'style']):
                    tag.decompose()
                article["content"] = content_elem.get_text(separator='\n', strip=True)
                break
        
        # Fallback to trafilatura
        if not article["content"]:
            try:
                article["content"] = trafilatura.extract(html, include_tables=True) or ""
            except:
                pass
    
    # 5. Extract author
    if not article["author"]:
        author_selectors = [
            '.author', '[class*="author"]', '[rel="author"]',
            'meta[property="article:author"]', 'meta[name="author"]'
        ]
        for selector in author_selectors:
            author_elem = soup.select_one(selector)
            if author_elem:
                article["author"] = author_elem.get_text(strip=True) or author_elem.get('content', '')
                if article["author"]:
                    break
    
    # 6. Extract date
    if not article["date_published"]:
        date_selectors = [
            'time[datetime]', '.date', '[class*="date"]',
            'meta[property="article:published_time"]'
        ]
        for selector in date_selectors:
            date_elem = soup.select_one(selector)
            if date_elem:
                article["date_published"] = date_elem.get('datetime') or date_elem.get('content') or date_elem.get_text(strip=True)
                if article["date_published"]:
                    break
    
    # 7. Extract categories and tags
    category_links = soup.find_all('a', href=lambda x: x and ('/category/' in x or '/tag/' in x))
    for link in category_links:
        category = link.get_text(strip=True)
        if '/category/' in link.get('href', ''):
            article["categories"].append(category)
        elif '/tag/' in link.get('href', ''):
            article["tags"].append(category)
    
    # 8. Extract images from article
    if article_tag:
        for img in article_tag.find_all('img', src=True):
            src = img.get('src') or img.get('data-src', '')
            if src:
                article["images"].append(urljoin(url, src))
    
    # 9. Calculate statistics
    article["word_count"] = len(article["content"].split())
    article["reading_time"] = max(1, article["word_count"] // 200)  # ~200 words per minute
    
    return article


def extract_all_scripts(html: str) -> List[Dict[str, Any]]:
    """Extract all script tags and their content"""
    scripts = []
    soup = BeautifulSoup(html, 'lxml')
    
    for script in soup.find_all('script'):
        script_data = {
            "src": script.get('src', ''),
            "type": script.get('type', ''),
            "id": script.get('id', ''),
            "async": script.has_attr('async'),
            "defer": script.has_attr('defer'),
            "content_length": len(script.string) if script.string else 0,
            "has_json": False,
            "extracted_json": []
        }
        
        if script.string:
            script_text = script.string.strip()
            
            # Try to extract JSON
            if script_text.startswith('{') or script_text.startswith('['):
                try:
                    json_data = json.loads(script_text)
                    script_data["has_json"] = True
                    script_data["extracted_json"] = extract_embedded_json_recursive(json_data)
                except:
                    pass
            
            # Look for common data patterns
            if any(pattern in script_text for pattern in ['jobs', 'products', 'team', 'funding', 'customers']):
                script_data["likely_contains_data"] = True
        
        scripts.append(script_data)
    
    return scripts


def extract_navigation_structure(html: str, base_url: str) -> Dict[str, Any]:
    """Extract navigation structure"""
    nav_structure = {
        "main_nav": [],
        "footer_links": [],
        "breadcrumbs": [],
        "sitemap_links": []
    }
    
    soup = BeautifulSoup(html, 'lxml')
    
    # Main navigation
    for nav in soup.find_all(['nav', 'header']):
        links = []
        for link in nav.find_all('a', href=True):
            links.append({
                "text": link.get_text(strip=True),
                "href": urljoin(base_url, link.get('href', '')),
                "classes": link.get('class', [])
            })
        if links:
            nav_structure["main_nav"].extend(links)
    
    # Footer links
    footer = soup.find('footer')
    if footer:
        for link in footer.find_all('a', href=True):
            nav_structure["footer_links"].append({
                "text": link.get_text(strip=True),
                "href": urljoin(base_url, link.get('href', '')),
                "category": link.get_text(strip=True).lower()
            })
    
    # Breadcrumbs
    breadcrumb = soup.find(['nav', 'ol', 'ul'], class_=lambda x: x and 'breadcrumb' in ' '.join(x).lower() if x else False)
    if breadcrumb:
        for link in breadcrumb.find_all('a', href=True):
            nav_structure["breadcrumbs"].append({
                "text": link.get_text(strip=True),
                "href": urljoin(base_url, link.get('href', ''))
            })
    
    return nav_structure


# ============================================================================
# FEED & DEDUP UTILITIES
# ============================================================================


def safe_urljoin(base: str, url: str) -> str:
    if not url:
        return url
    return urljoin(base, url)


def is_same_domain(url: str, base_url: str) -> bool:
    if not url:
        return False
    parsed_target = urlparse(url)
    if not parsed_target.netloc:
        return True
    parsed_base = urlparse(base_url)
    return parsed_target.netloc == parsed_base.netloc


def parse_feed_xml(xml_text: str, base_url: str) -> List[Dict[str, str]]:
    """Parse RSS or Atom feed content into a generic structure."""
    entries: List[Dict[str, str]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.debug(f"Feed parse error: {exc}")
        return entries
    
    tag_lower = root.tag.lower()
    if "rss" in tag_lower or root.find("channel") is not None:
        channel = root.find("channel") or root
        for item in channel.findall("item"):
            title = (item.findtext("title") or "").strip()
            link = safe_urljoin(base_url, (item.findtext("link") or "").strip())
            summary = (item.findtext("description") or "").strip()
            published = (item.findtext("pubDate") or "").strip()
            entries.append({
                "title": title,
                "url": link,
                "summary": summary,
                "published": published,
            })
    else:
        # Atom feeds
        namespace = ""
        if root.tag.startswith("{") and "}" in root.tag:
            namespace = root.tag[1: root.tag.find("}")]
        entry_tag = f"{{{namespace}}}entry" if namespace else "entry"
        title_tag = f"{{{namespace}}}title" if namespace else "title"
        summary_tag = f"{{{namespace}}}summary" if namespace else "summary"
        updated_tag = f"{{{namespace}}}updated" if namespace else "updated"
        published_tag = f"{{{namespace}}}published" if namespace else "published"
        link_tag = f"{{{namespace}}}link" if namespace else "link"
        for entry in root.findall(entry_tag):
            title_elem = entry.find(title_tag)
            summary_elem = entry.find(summary_tag)
            updated_elem = entry.find(updated_tag) or entry.find(published_tag)
            link_elem = entry.find(link_tag)
            
            title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
            summary = summary_elem.text.strip() if summary_elem is not None and summary_elem.text else ""
            published = updated_elem.text.strip() if updated_elem is not None and updated_elem.text else ""
            link = ""
            if link_elem is not None:
                link = link_elem.get("href", "").strip() or (link_elem.text.strip() if link_elem.text else "")
            link = safe_urljoin(base_url, link)
            entries.append({
                "title": title,
                "url": link,
                "summary": summary,
                "published": published,
            })
    return entries


def fetch_feed_entries(feed_url: str, limit: int = 25) -> List[Dict[str, str]]:
    """Fetch and parse feed entries from a URL."""
    try:
        response = requests.get(feed_url, timeout=10, headers={"User-Agent": USER_AGENT})
        if response.status_code != 200:
            logger.debug(f"Feed fetch failed ({response.status_code}): {feed_url}")
            return []
    except Exception as exc:
        logger.debug(f"Feed fetch error for {feed_url}: {exc}")
        return []
    
    entries = parse_feed_xml(response.text, feed_url)
    if limit and limit > 0:
        return entries[:limit]
    return entries


def dedupe_jobs_list(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Set[Tuple[str, str]] = set()
    unique: List[Dict[str, Any]] = []
    for job in jobs:
        title = (job.get("title") or "").strip().lower()
        url = (job.get("url") or "").strip().lower()
        key = (title, url)
        if key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


def dedupe_articles_list(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    unique: List[Dict[str, Any]] = []
    for article in articles:
        url = (article.get("url") or "").strip().lower()
        if not url:
            # fallback to title for dedupe
            url = (article.get("title") or "").strip().lower()
        if url not in seen:
            seen.add(url)
            unique.append(article)
    return unique


def dedupe_by_field(items: List[Dict[str, Any]], field: str) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    unique: List[Dict[str, Any]] = []
    for item in items:
        value = item.get(field)
        # Convert to string safely (handles None, int, float, etc.)
        if value is None:
            value_str = ""
        else:
            value_str = str(value).strip().lower()
        key = value_str or json.dumps(item, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


# ============================================================================
# COMPREHENSIVE PAGE EXTRACTION
# ============================================================================

def detect_page_error(html: str, text_content: str = None) -> Optional[str]:
    """Detect if a page contains an error message"""
    if text_content is None:
        # Quick extraction for error detection
        soup = BeautifulSoup(html, 'lxml')
        text_content = soup.get_text(separator=' ', strip=True)
    
    text_lower = text_content.lower()
    
    # Common error patterns
    error_patterns = [
        "application error",
        "client-side exception",
        "something went wrong",
        "an error occurred",
        "error loading page",
        "page not found",
        "404 error",
        "500 error",
        "internal server error",
        "this page isn't working",
        "this site can't be reached",
        "network error",
        "loading error",
        "failed to load",
        "error occurred while rendering"
    ]
    
    for pattern in error_patterns:
        if pattern in text_lower:
            return pattern
    
    # Check for very short content that might indicate an error
    if len(text_content.strip()) < 50 and any(err in html.lower() for err in ["error", "exception", "failed"]):
        return "suspected_error_short_content"
    
    return None


def extract_complete_page_data(html: str, url: str) -> Dict[str, Any]:
    """Extract ALL data from a page"""
    
    page_data = {
        "url": url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "content_hash": hashlib.sha256(html.encode('utf-8')).hexdigest(),
        "metadata": extract_all_metadata(html),
        "structured_data": extract_all_structured_data(html, url),
        "text_content": extract_all_text_content(html),
        "links": extract_all_links(html, url),
        "images": extract_all_images(html, url),
        "forms": extract_all_forms(html, url),
        "tables": extract_all_tables(html),
        "scripts": extract_all_scripts(html),
        "navigation": extract_navigation_structure(html, url),
        "statistics": {
            "total_links": 0,
            "internal_links": 0,
            "external_links": 0,
            "total_images": 0,
            "total_forms": 0,
            "total_tables": 0,
            "word_count": 0
        },
        "error_detected": None
    }
    
    # Detect errors
    error_type = detect_page_error(html, page_data["text_content"]["full_text"])
    if error_type:
        page_data["error_detected"] = error_type
    
    # Calculate statistics
    page_data["statistics"]["total_links"] = len(page_data["links"])
    page_data["statistics"]["internal_links"] = sum(1 for l in page_data["links"] if l["is_same_domain"])
    page_data["statistics"]["external_links"] = sum(1 for l in page_data["links"] if not l["is_same_domain"])
    page_data["statistics"]["total_images"] = len(page_data["images"])
    page_data["statistics"]["total_forms"] = len(page_data["forms"])
    page_data["statistics"]["total_tables"] = len(page_data["tables"])
    page_data["statistics"]["word_count"] = len(page_data["text_content"]["full_text"].split())
    
    return page_data


# ============================================================================
# PLAYWRIGHT CRAWLER
# ============================================================================

class ComprehensiveCrawler:
    """Comprehensive crawler that extracts ALL data"""
    
    def __init__(self, company: Dict, output_dir: Path, run_folder: str, max_pages: int = 50):
        self.company = company
        self.company_id = company["company_id"]
        self.company_name = company["company_name"]
        self.base_url = company["website"].rstrip('/')
        self.output_dir = output_dir / self.company_id / run_folder
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.profile = get_company_profile(self.company_id, self.base_url)
        self.pages_data = []
        self.urls_visited = set()
        self.priority_urls: Set[str] = set()
        self.urls_to_visit: Set[str] = {self.base_url}
        
        # Discovered page URLs for all 12 page types
        self.discovered_pages: Dict[str, Optional[str]] = {
            "homepage": self.base_url,
            "about": None,
            "product": None,
            "careers": None,
            "blog": None,
            "team": None,
            "investors": None,
            "customers": None,
            "press": None,
            "pricing": None,
            "partners": None,
            "contact": None
        }
        
        # Add blog indexes from profile
        for blog_index in self.profile.blog_indexes:
            if is_same_domain(blog_index, self.base_url):
                self.urls_to_visit.add(blog_index)
                self.priority_urls.add(blog_index)
                if not self.discovered_pages["blog"]:
                    self.discovered_pages["blog"] = blog_index

        # Try to find all 12 page types using patterns
        self._discover_all_page_types()

        self.max_pages = max_pages
        self.preloaded_jobs: List[Dict[str, Any]] = []
        self.preloaded_articles: List[Dict[str, Any]] = []
        
        logger.info("=" * 80)
        logger.info(f"🕷️  Comprehensive Scraper: {self.company_name}")
        logger.info(f"🌐 URL: {self.base_url}")
        logger.info("=" * 80)
    
    def _find_page_url(self, page_type: str) -> Optional[str]:
        """Find URL for a page type by trying multiple patterns (like scraper.py)"""
        patterns = PAGE_PATTERNS.get(page_type, [])
        for pattern in patterns:
            url = urljoin(self.base_url, pattern)
            try:
                response = requests.head(url, timeout=5, headers={"User-Agent": USER_AGENT}, allow_redirects=True)
                if response.status_code == 200:
                    return response.url
            except:
                continue
        return None
    
    def _discover_links_from_homepage(self, homepage_html: str) -> Dict[str, str]:
        """Discover page URLs by analyzing homepage links for all 12 page types (from scraper.py)"""
        discovered = {}
        try:
            soup = BeautifulSoup(homepage_html, 'lxml')
            parsed_base = urlparse(self.base_url)
            
            # Get all links
            for link in soup.find_all('a', href=True):
                href = link['href'].lower()
                full_url = urljoin(self.base_url, link['href'])
                
                # Only consider links from same domain
                if urlparse(full_url).netloc != parsed_base.netloc:
                    continue
                
                link_text = link.get_text().lower().strip()
                
                # Match all 12 page types based on URL or link text
                
                # About
                if not discovered.get('about'):
                    if any(x in href for x in ['/about', '/company', '/who-we-are', '/our-story']):
                        discovered['about'] = full_url
                    elif any(x in link_text for x in ['about', 'company', 'who we are', 'our story']):
                        discovered['about'] = full_url
                
                # Product
                if not discovered.get('product'):
                    if any(x in href for x in ['/product', '/platform', '/solution', '/feature']):
                        discovered['product'] = full_url
                    elif any(x in link_text for x in ['product', 'platform', 'solution', 'features']):
                        discovered['product'] = full_url
                
                # Careers
                if not discovered.get('careers'):
                    if any(x in href for x in ['/career', '/job', '/join', '/work-with']):
                        discovered['careers'] = full_url
                    elif any(x in link_text for x in ['career', 'jobs', 'join us', 'work with']):
                        discovered['careers'] = full_url
                
                # Blog
                if not discovered.get('blog'):
                    if any(x in href for x in ['/blog', '/insight', '/resource']):
                        discovered['blog'] = full_url
                    elif any(x in link_text for x in ['blog', 'insights', 'resources']):
                        discovered['blog'] = full_url
                
                # Team
                if not discovered.get('team'):
                    if any(x in href for x in ['/team', '/leadership', '/people', '/our-team']):
                        discovered['team'] = full_url
                    elif any(x in link_text for x in ['team', 'leadership', 'people', 'our team']):
                        discovered['team'] = full_url
                
                # Investors
                if not discovered.get('investors'):
                    if any(x in href for x in ['/investor', '/funding', '/backed-by', '/backer']):
                        discovered['investors'] = full_url
                    elif any(x in link_text for x in ['investors', 'funding', 'backed by', 'backers']):
                        discovered['investors'] = full_url
                
                # Customers
                if not discovered.get('customers'):
                    if any(x in href for x in ['/customer', '/case-stud', '/success-stor', '/testimonial']):
                        discovered['customers'] = full_url
                    elif any(x in link_text for x in ['customers', 'case studies', 'success stories', 'testimonials']):
                        discovered['customers'] = full_url
                
                # Press
                if not discovered.get('press'):
                    if any(x in href for x in ['/press', '/newsroom', '/media', '/news-and-press']):
                        discovered['press'] = full_url
                    elif any(x in link_text for x in ['press', 'newsroom', 'media', 'news']):
                        discovered['press'] = full_url
                
                # Pricing
                if not discovered.get('pricing'):
                    if any(x in href for x in ['/pricing', '/plans', '/price', '/buy']):
                        discovered['pricing'] = full_url
                    elif any(x in link_text for x in ['pricing', 'plans', 'price', 'buy']):
                        discovered['pricing'] = full_url
                
                # Partners
                if not discovered.get('partners'):
                    if any(x in href for x in ['/partner', '/integration', '/ecosystem']):
                        discovered['partners'] = full_url
                    elif any(x in link_text for x in ['partners', 'integrations', 'ecosystem']):
                        discovered['partners'] = full_url
                
                # Contact
                if not discovered.get('contact'):
                    if any(x in href for x in ['/contact', '/get-in-touch', '/reach-us']):
                        discovered['contact'] = full_url
                    elif any(x in link_text for x in ['contact', 'get in touch', 'reach us']):
                        discovered['contact'] = full_url
        
        except Exception as e:
            logger.debug(f"Link discovery failed: {str(e)[:50]}")
        
        return discovered
    
    def _discover_all_page_types(self):
        """Systematically discover all 12 page types using patterns and homepage links"""
        # First, try to find pages using URL patterns (fast HTTP HEAD requests)
        for page_type in PAGE_PATTERNS.keys():
            if page_type == "homepage":
                continue  # Already set
            url = self._find_page_url(page_type)
            if url:
                self.discovered_pages[page_type] = url
                self.urls_to_visit.add(url)
                self.priority_urls.add(url)
                logger.debug(f"  ✓ Found {page_type} page: {url}")
        
        # Then, try to discover from homepage (if we can fetch it quickly)
        try:
            response = requests.get(self.base_url, timeout=5, headers={"User-Agent": USER_AGENT})
            if response.status_code == 200:
                discovered = self._discover_links_from_homepage(response.text)
                for page_type, url in discovered.items():
                    if not self.discovered_pages.get(page_type):
                        self.discovered_pages[page_type] = url
                        self.urls_to_visit.add(url)
                        self.priority_urls.add(url)
                        logger.debug(f"  ✓ Discovered {page_type} from homepage: {url}")
        except:
            pass  # Will discover during crawl
        
        # Log discovered pages
        found_pages = [pt for pt, url in self.discovered_pages.items() if url]
        logger.info(f"  📋 Discovered {len(found_pages)}/12 page types: {', '.join(found_pages)}")
    
    def discover_urls(self, html: str, current_url: str) -> Set[str]:
        """Discover all URLs from a page, prioritizing jobs and news - FAST VERSION"""
        discovered = set()
        links = extract_all_links(html, current_url)
        parsed_base = urlparse(self.base_url)
        
        # Priority URLs (jobs and news)
        priority_urls = []
        regular_urls = []
        
        # Skip patterns for low-value pages - EXPANDED for speed
        skip_patterns = [
            '/legal/', '/privacy', '/terms', '/cookie', '/policy',
            '/signup', '/login', '/register', '/account', '/profile',
            '/search', '/archive', '/tag/', '/category/', '/author/',
            '/page/', '/#', 'javascript:', 'mailto:', 'tel:',
            '.pdf', '.jpg', '.png', '.gif', '.zip', '.exe', '.doc', '.docx',
            '/events/', '/webinar', '/demo', '/contact', '/support',
            '/help', '/faq', '/docs/', '/documentation', '/api/',
            '/download', '/pricing', '/plans', '/trial', '/free',
            '/university', '/training', '/certification', '/learn/',
            '/resources/', '/whitepaper', '/ebook', '/case-study',
            '/customer-stories/', '/partners/', '/integrations',
            '/security/', '/trust/', '/compliance', '/gdpr'
        ]
        
        for link in links:
            url = link["full_url"]
            parsed = urlparse(url)
            
            # Allow same domain OR external ATS domains (for job postings)
            if parsed.netloc and parsed.netloc != parsed_base.netloc:
                # Allow external ATS domains for job extraction
                if not is_ats_domain(url):
                    continue
            
            # Skip fragments, mailto, tel, etc.
            if any(url.startswith(prefix) for prefix in ['mailto:', 'tel:', 'javascript:', '#']):
                continue
            
            # Skip low-value pages early
            url_lower = url.lower()
            if any(skip in url_lower for skip in skip_patterns):
                continue
            
            # Skip if we already have enough pages queued
            if len(self.urls_visited) + len(self.urls_to_visit) >= self.max_pages:
                break
            
            # Prioritize job and news pages
            if any(kw in url_lower for kw in ['/job/', '/position/', '/opening/', '/career/', '/blog/', '/news/', '/post/', '/article/']):
                priority_urls.append(url)
            # Also prioritize external ATS job listing pages
            elif is_ats_domain(url) and any(kw in url_lower for kw in ['/jobs', '/job', '/position', '/opening', '/career']):
                priority_urls.append(url)
            elif len(regular_urls) < 20:  # Limit regular URLs to prevent crawling everything
                # Only add essential pages
                if any(kw in url_lower for kw in ['/about', '/team', '/product', '/pricing', '/customer', '/partner', '/investor']):
                    regular_urls.append(url)
        
        # Add priority URLs first (up to limit)
        top_priority = priority_urls[:30]
        discovered.update(top_priority)  # Limit priority URLs too
        self.priority_urls.update(top_priority)
        discovered.update(regular_urls)
        
        return discovered

    async def fetch_priority_content(self, context: BrowserContext) -> None:
        """Preload high-value pages (all 12 page types + careers + news feeds) before broad crawl."""
        # Initialize ATS extractor
        ats_extractor = ATSExtractor(self.base_url)
        news_extractor = NewsExtractor(self.base_url)
        
        # FIRST: Crawl all 12 page types systematically (like scraper.py)
        # Ensure homepage is crawled FIRST to discover more pages
        logger.info("  🔍 Crawling all 12 page types...")
        
        # Sort pages to ensure homepage is first
        page_types_to_crawl = []
        if self.discovered_pages.get("homepage"):
            page_types_to_crawl.append(("homepage", self.discovered_pages["homepage"]))
        for page_type, page_url in self.discovered_pages.items():
            if page_type != "homepage" and page_url:
                page_types_to_crawl.append((page_type, page_url))
        
        crawled_page_types = []
        for page_type, page_url in page_types_to_crawl:
            # Skip if already visited (but still try if it's a critical page type)
            if page_url in self.urls_visited and page_type != "homepage":
                logger.debug(f"  ⏭️  Skipping {page_type} (already visited): {page_url}")
                continue
            
            # Check page limit
            if len(self.urls_visited) >= self.max_pages:
                logger.warning(f"  ⚠️  Page limit reached, skipping remaining page types")
                break
            
            try:
                page = await context.new_page()
                logger.info(f"  📄 Crawling {page_type} page: {page_url}")
                await page.goto(page_url, wait_until='domcontentloaded', timeout=PRIORITY_PAGE_TIMEOUT)
                await asyncio.sleep(0.2)  # Reduced wait for faster scraping
                html = await page.content()
                await page.close()
                
                # Extract complete page data
                page_data = extract_complete_page_data(html, page_url)
                page_data["raw_html"] = html
                page_data["page_type"] = page_type  # Store page type for later use
                
                # Apply structured extraction based on page type
                if page_type == "investors":
                    # Extract funding information
                    investors_data = self._parse_investors_page(html)
                    if investors_data:
                        page_data["extracted_investors"] = investors_data
                        logger.info(f"  💰 Found {len(investors_data)} investor/funding items")
                elif page_type == "press":
                    # Extract press releases and funding announcements
                    press_data = self._parse_press_page(html)
                    if press_data:
                        page_data["extracted_press"] = press_data
                        logger.info(f"  📰 Found {len(press_data)} press releases")
                elif page_type == "pricing":
                    # Extract pricing information
                    pricing_data = self._parse_pricing_page(html)
                    if pricing_data:
                        page_data["extracted_pricing"] = pricing_data
                        logger.info(f"  💵 Found pricing model: {pricing_data.get('pricing_model')}, {len(pricing_data.get('tiers', []))} tiers")
                elif page_type == "customers":
                    # Extract customer names
                    customers_data = self._parse_customers_page(html)
                    if customers_data:
                        page_data["extracted_customers"] = customers_data
                        logger.info(f"  👥 Found {len(customers_data)} customers")
                elif page_type == "partners":
                    # Extract partner names
                    partners_data = self._parse_partners_page(html)
                    if partners_data:
                        page_data["extracted_partners"] = partners_data
                        logger.info(f"  🤝 Found {len(partners_data)} partners")
                
                self.pages_data.append(page_data)
                self.urls_visited.add(page_url)
                self.priority_urls.discard(page_url)
                crawled_page_types.append(page_type)
                
                # If this is homepage, discover more pages from it
                if page_type == "homepage":
                    discovered = self._discover_links_from_homepage(html)
                    for discovered_type, discovered_url in discovered.items():
                        if not self.discovered_pages.get(discovered_type):
                            self.discovered_pages[discovered_type] = discovered_url
                            self.urls_to_visit.add(discovered_url)
                            self.priority_urls.add(discovered_url)
                            logger.info(f"  ➕ Discovered {discovered_type} from homepage: {discovered_url}")
                
                # Discover more URLs from this page
                new_urls = self.discover_urls(html, page_url)
                for new_url in new_urls:
                    if is_same_domain(new_url, self.base_url) and new_url not in self.urls_visited:
                        if len(self.urls_visited) + len(self.urls_to_visit) < self.max_pages:
                            self.urls_to_visit.add(new_url)
                
            except Exception as exc:
                logger.warning(f"  ⚠️  Failed to crawl {page_type} page ({page_url}): {exc}")
        
        logger.info(f"  ✅ Crawled {len(crawled_page_types)}/12 page types: {', '.join(crawled_page_types)}")
        
        # Log which page types were NOT found/crawled
        missing_types = [pt for pt in PAGE_PATTERNS.keys() if pt not in crawled_page_types]
        if missing_types:
            logger.warning(f"  ⚠️  Missing page types: {', '.join(missing_types)}")
        
        # Careers pages for jobs - USE ATS EXTRACTION
        # Also check for external ATS domains in iframes
        for idx, careers_url in enumerate(self.profile.careers_urls):
            if idx >= self.profile.max_jobs_pages:
                break
            # Allow external ATS domains
            if not is_same_domain(careers_url, self.base_url) and not is_ats_domain(careers_url):
                continue
            if careers_url in self.urls_visited:
                continue
            try:
                page = await context.new_page()
                logger.info(f"  🎯 Preloading careers page: {careers_url}")
                # Increased timeout for slow-loading ATS pages
                try:
                    await page.goto(careers_url, wait_until='domcontentloaded', timeout=CAREERS_PAGE_TIMEOUT)
                except PlaywrightTimeout:
                    logger.warning(f"  ⏱️  Timeout on initial load, trying networkidle: {careers_url}")
                    try:
                        await page.wait_for_load_state('networkidle', timeout=NETWORK_IDLE_TIMEOUT)
                    except PlaywrightTimeout:
                        logger.warning(f"  ⏱️  Network idle timeout, continuing anyway: {careers_url}")
                html = await page.content()
            except Exception as exc:
                logger.warning(f"  ⚠️  Careers preload failed ({careers_url}): {exc}")
                try:
                    await page.close()
                except Exception:
                    pass
                continue
            
            # Wait for dynamic ATS content to load (reduced for faster scraping)
            await asyncio.sleep(1)  # Reduced from 3s
            try:
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await asyncio.sleep(0.5)  # Reduced from 2s
                await page.evaluate('window.scrollTo(0, 0)')  # Scroll back up
                await asyncio.sleep(0.3)  # Reduced from 1s
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')  # Scroll down again
                await asyncio.sleep(0.5)  # Reduced from 2s
            except Exception as scroll_err:
                # Handle navigation errors gracefully
                if "Execution context was destroyed" in str(scroll_err) or "Target closed" in str(scroll_err):
                    logger.debug(f"  ⚠️  Page navigated during ATS scroll, continuing...")
                else:
                    logger.debug(f"  ⚠️  ATS scroll error: {scroll_err}")
            
            # Check for iframes with external ATS and extract from them
            iframes = await page.query_selector_all('iframe')
            for iframe in iframes:
                try:
                    iframe_src = await iframe.get_attribute('src')
                    if iframe_src and is_ats_domain(iframe_src):
                        logger.info(f"  🔍 Found ATS iframe: {iframe_src}")
                        # Try to get iframe content
                        try:
                            iframe_content = await iframe.content_frame()
                            if iframe_content:
                                iframe_html = await iframe_content.content()
                                iframe_jobs = ats_extractor.extract_jobs(iframe_html, iframe_src)[1]
                                if iframe_jobs:
                                    self.preloaded_jobs.extend(iframe_jobs)
                                    logger.info(f"  ✅ Extracted {len(iframe_jobs)} jobs from iframe")
                        except Exception as e:
                            logger.debug(f"  ⚠️  Could not extract from iframe: {e}")
                            # Fallback: try to navigate to iframe URL directly
                            try:
                                iframe_page = await context.new_page()
                                await iframe_page.goto(iframe_src, wait_until='domcontentloaded', timeout=NAVIGATION_TIMEOUT)
                                await asyncio.sleep(0.5)  # Reduced wait for faster scraping
                                iframe_html = await iframe_page.content()
                                iframe_jobs = ats_extractor.extract_jobs(iframe_html, iframe_src)[1]
                                if iframe_jobs:
                                    self.preloaded_jobs.extend(iframe_jobs)
                                    logger.info(f"  ✅ Extracted {len(iframe_jobs)} jobs from iframe URL")
                                await iframe_page.close()
                            except Exception as e2:
                                logger.debug(f"  ⚠️  Could not navigate to iframe URL: {e2}")
                except Exception as e:
                    logger.debug(f"  ⚠️  Error checking iframe: {e}")
            try:
                await page.evaluate('window.scrollTo(0, 0)')
                await asyncio.sleep(1)
            except Exception as scroll_err:
                # Handle navigation errors gracefully
                if "Execution context was destroyed" in str(scroll_err) or "Target closed" in str(scroll_err):
                    logger.debug(f"  ⚠️  Page navigated during scroll, continuing...")
                else:
                    logger.debug(f"  ⚠️  Scroll error: {scroll_err}")
            
            # Try clicking "Load More" or "Show All" buttons multiple times (increased attempts)
            for attempt in range(5):  # Increased from 3 to 5
                try:
                    load_more = page.locator('button:has-text("Load More"), button:has-text("Show More"), button:has-text("View All"), a:has-text("View All Jobs")').first
                    if await load_more.count() > 0:
                        await load_more.click(timeout=2000)
                        await asyncio.sleep(1)
                except:
                    break
            
            # Get updated HTML after dynamic loading
            html = await page.content()
            
            # Use ATS extraction for fast job collection
            ats_type, ats_jobs = ats_extractor.extract_jobs(html, careers_url)
            if ats_jobs:
                self.preloaded_jobs.extend(ats_jobs)
                logger.info(f"  ✅ {ats_type.upper()} ATS: {len(ats_jobs)} jobs extracted")
            elif ats_type:
                logger.warning(f"  ⚠️  {ats_type.upper()} ATS detected but no jobs found - trying comprehensive extraction")
            
            # ALWAYS use comprehensive extraction as fallback (even if ATS found jobs)
            page_data = extract_complete_page_data(html, careers_url)
            page_data["raw_html"] = html
            
            # Check for errors and retry if needed
            if page_data.get("error_detected"):
                logger.warning(f"  ⚠️  Error detected ({page_data['error_detected']}) on careers page: {careers_url}")
                if "client-side" in page_data["error_detected"] or "application error" in page_data["error_detected"]:
                    logger.info(f"  🔄 Retrying careers page with longer wait...")
                    try:
                        await page.wait_for_load_state('networkidle', timeout=NETWORK_IDLE_TIMEOUT)
                        await asyncio.sleep(2)  # Reduced wait for faster scraping
                        try:
                            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                            await asyncio.sleep(2)
                        except Exception as scroll_err:
                            # Handle navigation errors gracefully
                            if "Execution context was destroyed" in str(scroll_err) or "Target closed" in str(scroll_err):
                                logger.debug(f"  ⚠️  Page navigated during ATS retry scroll, continuing...")
                            else:
                                logger.debug(f"  ⚠️  ATS retry scroll error: {scroll_err}")
                        html = await page.content()
                        page_data = extract_complete_page_data(html, careers_url)
                        page_data["raw_html"] = html
                        if page_data.get("error_detected"):
                            logger.warning(f"  ❌ Careers page still has error after retry")
                            page_data["load_failed"] = True
                        else:
                            logger.info(f"  ✅ Careers page retry successful")
                    except Exception as retry_exc:
                        logger.debug(f"  ⚠️  Careers page retry failed: {retry_exc}")
                        page_data["load_failed"] = True
            
            jobs = extract_jobs_from_all_sources(html, careers_url)
            if jobs:
                # Merge with ATS jobs (deduplicate)
                existing_titles = {j.get('title', '').lower() for j in self.preloaded_jobs}
                new_jobs = []
                for job in jobs:
                    if job.get('title', '').lower() not in existing_titles:
                        self.preloaded_jobs.append(job)
                        new_jobs.append(job)
                        existing_titles.add(job.get('title', '').lower())
                if new_jobs:
                    logger.info(f"  💼 Comprehensive extraction: {len(new_jobs)} additional jobs found")
                page_data["extracted_jobs"] = jobs
                logger.info(f"  💼 Total jobs: {len(self.preloaded_jobs)}")
            elif not ats_jobs and ats_type:
                logger.warning(f"  ❌ No jobs found via {ats_type.upper()} ATS or comprehensive extraction")
            
            # Try to extract from iframes (for embedded ATS like Ashby)
            try:
                iframes = await page.query_selector_all('iframe')
                for iframe in iframes:
                    try:
                        iframe_src = await iframe.get_attribute('src')
                        if iframe_src and ('ashbyhq.com' in iframe_src or 'greenhouse.io' in iframe_src or 
                                          'lever.co' in iframe_src or 'workable.com' in iframe_src):
                            # Navigate to iframe content
                            frame = await iframe.content_frame()
                            if frame:
                                await frame.wait_for_load_state('networkidle', timeout=5000)
                                iframe_html = await frame.content()
                                iframe_jobs = extract_jobs_from_all_sources(iframe_html, iframe_src)
                                if iframe_jobs:
                                    existing_titles = {j.get('title', '').lower() for j in self.preloaded_jobs}
                                    for job in iframe_jobs:
                                        if job.get('title', '').lower() not in existing_titles:
                                            self.preloaded_jobs.append(job)
                                            existing_titles.add(job.get('title', '').lower())
                                    logger.info(f"  💼 Found {len(iframe_jobs)} jobs in iframe")
                    except Exception as exc:
                        logger.debug(f"  ⚠️  Iframe extraction failed: {exc}")
            except Exception as exc:
                logger.debug(f"  ⚠️  Iframe check failed: {exc}")
            
            # Visit individual job detail pages to get full descriptions
            # Also allow external ATS domains for job URLs
            job_urls_to_visit = []
            for job in self.preloaded_jobs:
                job_url = job.get('url')
                if job_url:
                    # Allow same domain OR external ATS domains
                    if (is_same_domain(job_url, self.base_url) or is_ats_domain(job_url)):
                        if job_url not in self.urls_visited and job_url not in self.priority_urls:
                            job_urls_to_visit.append(job_url)
            
            # Visit up to 50 job detail pages (increased from 20)
            for job_url in job_urls_to_visit[:50]:
                try:
                    job_page = await context.new_page()
                    logger.debug(f"  🔍 Visiting job detail: {job_url[:80]}...")
                    await job_page.goto(job_url, wait_until='domcontentloaded', timeout=JOB_PAGE_TIMEOUT)
                    await asyncio.sleep(0.5)  # Reduced wait for faster scraping
                    job_html = await job_page.content()
                    await job_page.close()
                    
                    # Extract full job details
                    job_data = extract_complete_page_data(job_html, job_url)
                    job_jobs = extract_jobs_from_all_sources(job_html, job_url)
                    
                    # Update job with full description if found
                    for found_job in job_jobs:
                        for existing_job in self.preloaded_jobs:
                            if (existing_job.get('url', '').lower() == job_url.lower() or
                                existing_job.get('title', '').lower() == found_job.get('title', '').lower()):
                                if found_job.get('description') and not existing_job.get('description'):
                                    existing_job['description'] = found_job.get('description')
                                if found_job.get('location') and not existing_job.get('location'):
                                    existing_job['location'] = found_job.get('location')
                                break
                    
                    # Also check if this page has links to other jobs (job listing page)
                    if job_jobs and len(job_jobs) > 1:
                        # This might be a listing page, add other jobs
                        for found_job in job_jobs:
                            existing_titles = {j.get('title', '').lower() for j in self.preloaded_jobs}
                            if found_job.get('title', '').lower() not in existing_titles:
                                self.preloaded_jobs.append(found_job)
                                logger.debug(f"  ➕ Found additional job: {found_job.get('title', '')[:50]}")
                    
                    self.urls_visited.add(job_url)
                except Exception as exc:
                    logger.debug(f"  ⚠️  Job detail page failed ({job_url}): {exc}")
            
            self.pages_data.append(page_data)
            self.urls_visited.add(careers_url)
            self.priority_urls.add(careers_url)
            new_urls = self.discover_urls(html, careers_url)
            for new_url in new_urls:
                if not is_same_domain(new_url, self.base_url):
                    continue
                if len(self.urls_visited) + len(self.urls_to_visit) >= self.max_pages:
                    break
                if new_url not in self.urls_visited:
                    self.urls_to_visit.add(new_url)
            try:
                await page.close()
            except Exception:
                pass
        
        # Fetch articles from RSS feeds - USE NEWS EXTRACTOR
        total_articles = 0
        
        # First, try to find RSS feeds from homepage/blog index
        try:
            homepage_page = await context.new_page()
            await homepage_page.goto(self.base_url, wait_until='domcontentloaded', timeout=NAVIGATION_TIMEOUT)
            homepage_html = await homepage_page.content()
            await homepage_page.close()
            
            # Find RSS feeds
            rss_feeds = news_extractor.find_rss_feeds(homepage_html)
            for feed_url in rss_feeds:
                if total_articles >= self.profile.max_articles:
                    break
                articles = news_extractor.extract_from_rss(feed_url)
                for article in articles:
                    if total_articles >= self.profile.max_articles:
                        break
                    article_url = article.get('url', '')
                    if not article_url or not is_same_domain(article_url, self.base_url):
                        continue
                    if article_url in self.urls_visited or article_url in self.priority_urls:
                        continue
                    
                    # Fetch full article content
                    try:
                        article_page = await context.new_page()
                        await article_page.goto(article_url, wait_until='domcontentloaded', timeout=PRIORITY_PAGE_TIMEOUT)
                        try:
                            await article_page.wait_for_load_state('networkidle', timeout=5000)
                        except PlaywrightTimeout:
                            pass
                        article_html = await article_page.content()
                        await article_page.close()
                        
                        # Extract full content
                        full_article = news_extractor.extract_article_content(article_html, article_url)
                        # Merge with RSS data
                        full_article['title'] = article.get('title') or full_article.get('title', '')
                        full_article['author'] = article.get('author') or full_article.get('author', '')
                        full_article['date_published'] = article.get('date_published') or full_article.get('date_published', '')
                        full_article['excerpt'] = article.get('excerpt') or full_article.get('excerpt', '')
                        full_article['categories'] = article.get('categories', [])
                        
                        self.preloaded_articles.append(full_article)
                        
                        page_data = extract_complete_page_data(article_html, article_url)
                        page_data["raw_html"] = article_html
                        page_data["extracted_article"] = full_article
                        self.pages_data.append(page_data)
                        self.urls_visited.add(article_url)
                        self.priority_urls.add(article_url)
                        total_articles += 1
                    except Exception as exc:
                        logger.debug(f"  ⚠️  Article fetch failed ({article_url}): {exc}")
        except Exception as exc:
            logger.debug(f"RSS feed discovery failed: {exc}")
        
        # Fallback: Use profile blog feeds
        for feed_url in self.profile.blog_feeds:
            if total_articles >= self.profile.max_articles:
                break
            entries = fetch_feed_entries(feed_url, self.profile.max_articles - total_articles)
            if not entries:
                continue
            logger.info(f"  📰 Feed discovered {len(entries)} entries from {feed_url}")
            for entry in entries:
                article_url = entry.get("url") or ""
                if not article_url or not is_same_domain(article_url, self.base_url):
                    continue
                if article_url in self.urls_visited or article_url in self.priority_urls:
                    continue
                try:
                    page = await context.new_page()
                    await page.goto(article_url, wait_until='domcontentloaded', timeout=PRIORITY_PAGE_TIMEOUT)
                    try:
                        await page.wait_for_load_state('networkidle', timeout=NETWORK_IDLE_TIMEOUT)
                    except PlaywrightTimeout:
                        pass
                    html = await page.content()
                    await page.close()
                except Exception as exc:
                    logger.debug(f"  ⚠️  Article preload failed ({article_url}): {exc}")
                    continue
                
                page_data = extract_complete_page_data(html, article_url)
                page_data["raw_html"] = html
                article = extract_news_article(html, article_url)
                if entry.get("title") and not article.get("title"):
                    article["title"] = entry["title"]
                if entry.get("published") and not article.get("date_published"):
                    article["date_published"] = entry["published"]
                if entry.get("summary") and not article.get("excerpt"):
                    article["excerpt"] = entry["summary"]
                self.preloaded_articles.append(article)
                page_data["extracted_article"] = article
                self.pages_data.append(page_data)
                self.urls_visited.add(article_url)
                self.priority_urls.add(article_url)
                total_articles += 1
                
                if total_articles >= self.profile.max_articles:
                    break
        
        # Ensure blog index pages are queued
        for blog_index in self.profile.blog_indexes:
            if not is_same_domain(blog_index, self.base_url):
                continue
            if len(self.urls_visited) + len(self.urls_to_visit) >= self.max_pages:
                break
            if blog_index not in self.urls_visited:
                self.urls_to_visit.add(blog_index)
    
    async def crawl_page(self, page: Page, url: str) -> Optional[Dict[str, Any]]:
        """Crawl a single page comprehensively"""
        
        if url in self.urls_visited:
            return None
        
        if len(self.urls_visited) >= self.max_pages:
            return None
        
        # Skip robots.txt checking - crawl everything for comprehensive data extraction
        
        try:
            logger.info(f"  📄 Crawling: {url[:80]}...")
            
            # Navigate with increased timeout for slow-loading pages
            response = await page.goto(url, wait_until='domcontentloaded', timeout=NAVIGATION_TIMEOUT)
            
            if response and response.status >= 400:
                logger.warning(f"  ⚠️  HTTP {response.status}: {url}")
                return None
            
            # Skip PDFs and downloads
            if response:
                headers = response.headers
                content_type = headers.get("content-type", "").lower()
                if any(binary in content_type for binary in ["application/pdf", "application/octet-stream", "application/zip"]):
                    logger.info(f"  ⚠️  Skipping binary content: {url}")
                    return None
                content_disposition = headers.get("content-disposition", "").lower()
                if "attachment" in content_disposition:
                    logger.info(f"  ⚠️  Skipping downloadable attachment: {url}")
                    return None
            
            # Also check URL for PDFs
            if url.lower().endswith('.pdf'):
                logger.info(f"  ⚠️  Skipping PDF: {url}")
                return None
            
            # Only wait/scroll for priority pages (jobs/news) - skip for others
            url_lower = url.lower()
            is_priority_page = any(kw in url_lower for kw in ['/career', '/job', '/blog/', '/news/', '/post/', '/article/'])
            
            if is_priority_page:
                # Quick scroll to load lazy content (with error handling for navigation)
                try:
                    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    await asyncio.sleep(0.3)
                except Exception as scroll_err:
                    # Handle navigation errors gracefully
                    if "Execution context was destroyed" in str(scroll_err) or "Target closed" in str(scroll_err):
                        logger.debug(f"  ⚠️  Page navigated during scroll, continuing...")
                    else:
                        logger.debug(f"  ⚠️  Scroll error: {scroll_err}")
                
                # Try clicking "Load More" buttons (only once, fast)
                try:
                    load_more = page.locator('button:has-text("Load More"), button:has-text("Show More")').first
                    if await load_more.count() > 0:
                        await load_more.click(timeout=1000)
                        await asyncio.sleep(0.3)
                except Exception:
                    pass
            else:
                # For non-priority pages, minimal wait
                await asyncio.sleep(0.2)
            
            # Get HTML
            html = await page.content()
            
            # Extract ALL data
            page_data = extract_complete_page_data(html, url)
            page_data["raw_html"] = html  # Store HTML for saving
            
            # Check for errors and retry if needed (especially for Next.js/React apps)
            if page_data.get("error_detected"):
                logger.warning(f"  ⚠️  Error detected ({page_data['error_detected']}): {url}")
                # For client-side errors, try waiting longer for JavaScript to render
                if "client-side" in page_data["error_detected"] or "application error" in page_data["error_detected"]:
                    logger.info(f"  🔄 Retrying with longer wait for JS rendering...")
                    try:
                        await page.wait_for_load_state('networkidle', timeout=NETWORK_IDLE_TIMEOUT)
                        await asyncio.sleep(1)  # Reduced wait for faster scraping
                        try:
                            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                            await asyncio.sleep(1)
                        except Exception as scroll_err:
                            # Handle navigation errors gracefully
                            if "Execution context was destroyed" in str(scroll_err) or "Target closed" in str(scroll_err):
                                logger.debug(f"  ⚠️  Page navigated during retry scroll, continuing...")
                            else:
                                logger.debug(f"  ⚠️  Retry scroll error: {scroll_err}")
                        html = await page.content()
                        page_data = extract_complete_page_data(html, url)
                        page_data["raw_html"] = html
                        if page_data.get("error_detected"):
                            logger.warning(f"  ❌ Still has error after retry, marking as failed: {url}")
                            # Mark as failed but still save for debugging
                            page_data["load_failed"] = True
                        else:
                            logger.info(f"  ✅ Retry successful, error resolved")
                    except Exception as retry_exc:
                        logger.debug(f"  ⚠️  Retry failed: {retry_exc}")
                        page_data["load_failed"] = True
                else:
                    # For other errors, mark as failed
                    page_data["load_failed"] = True
            
            # Extract jobs if this is a careers/jobs page - USE ATS EXTRACTION
            url_lower = url.lower()
            if any(kw in url_lower for kw in ['/career', '/job', '/opening', '/position']):
                # Use ATS extractor for fast extraction
                ats_extractor = ATSExtractor(self.base_url)
                ats_type, ats_jobs = ats_extractor.extract_jobs(html, url)
                if ats_jobs:
                    page_data["extracted_jobs"] = ats_jobs
                    logger.info(f"  💼 {ats_type.upper() if ats_type else 'Generic'}: {len(ats_jobs)} jobs")
                
                # Also use comprehensive extraction as fallback
                comprehensive_jobs = extract_jobs_from_all_sources(html, url)
                if comprehensive_jobs:
                    # Merge jobs (deduplicate)
                    existing = {j.get('title', '').lower() for j in (page_data.get("extracted_jobs") or [])}
                    new_jobs = [j for j in comprehensive_jobs if j.get('title', '').lower() not in existing]
                    if new_jobs:
                        if "extracted_jobs" not in page_data:
                            page_data["extracted_jobs"] = []
                        page_data["extracted_jobs"].extend(new_jobs)
                        logger.info(f"  💼 Additional jobs: {len(new_jobs)} (total: {len(page_data['extracted_jobs'])})")
            
            # Extract news article if this is a blog/news page - USE NEWS EXTRACTOR
            if any(kw in url_lower for kw in ['/blog/', '/news/', '/post/', '/article/']):
                news_extractor = NewsExtractor(self.base_url)
                article = news_extractor.extract_article_content(html, url)
                if article.get("title") or article.get("content"):
                    page_data["extracted_article"] = article
                    logger.info(f"  📰 Extracted article: {article.get('title', 'Untitled')[:60]}...")
            
            # Discover new URLs
            new_urls = self.discover_urls(html, url)
            
            # If this is the homepage, also discover page types from links
            if url.rstrip('/') == self.base_url.rstrip('/'):
                discovered = self._discover_links_from_homepage(html)
                for page_type, discovered_url in discovered.items():
                    if not self.discovered_pages.get(page_type):
                        self.discovered_pages[page_type] = discovered_url
                        self.urls_to_visit.add(discovered_url)
                        self.priority_urls.add(discovered_url)
                        logger.debug(f"  ✓ Discovered {page_type} from homepage: {discovered_url}")
            
            for new_url in new_urls:
                if new_url in self.urls_visited or new_url in self.priority_urls:
                    continue
                # Allow same domain OR external ATS domains
                if not is_same_domain(new_url, self.base_url) and not is_ats_domain(new_url):
                    continue
                if len(self.urls_visited) + len(self.urls_to_visit) >= self.max_pages:
                    break
                if new_url not in self.urls_visited:
                    self.urls_to_visit.add(new_url)
            
            # Also discover job listing/pagination links from the page
            if any(kw in url_lower for kw in ['/career', '/job', '/opening', '/position']) or is_ats_domain(url):
                soup = BeautifulSoup(html, 'lxml')
                # Find pagination links, "View All Jobs", etc.
                pagination_links = soup.find_all('a', href=True, string=re.compile(r'view all|all jobs|next|page|\d+', re.I))
                pagination_links.extend(soup.find_all('a', href=re.compile(r'/jobs|/job|/page|pagination', re.I)))
                for link in pagination_links[:10]:  # Limit to 10 pagination links
                    href = link.get('href', '')
                    if not href:
                        continue
                    full_url = urljoin(url, href)
                    # Allow same domain or external ATS
                    if (is_same_domain(full_url, self.base_url) or is_ats_domain(full_url)):
                        if full_url not in self.urls_visited and full_url not in self.priority_urls:
                            if len(self.urls_visited) + len(self.urls_to_visit) >= self.max_pages:
                                break
                            self.urls_to_visit.add(full_url)
                            logger.debug(f"  🔗 Discovered job listing page: {full_url}")
            
            self.urls_visited.add(url)
            self.pages_data.append(page_data)
            
            logger.info(f"  ✅ Extracted: {page_data['statistics']['word_count']} words, "
                       f"{page_data['statistics']['total_links']} links, "
                       f"{len(page_data['structured_data']['json_ld'])} JSON-LD items")
            
            return page_data
            
        except PlaywrightTimeout:
            logger.warning(f"  ⏱️  Timeout: {url}")
            return None
        except Exception as e:
            logger.error(f"  ❌ Error crawling {url}: {str(e)[:100]}")
            return None
    
    async def crawl(self):
        """Main crawl loop"""
        
        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not available!")
            return {
                "company_name": self.company_name,
                "company_id": self.company_id,
                "status": "error",
                "error": "Playwright not available"
            }
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1920, "height": 1080}
            )
            await self.fetch_priority_content(context)
            
            if len(self.urls_visited) >= self.max_pages:
                logger.info("  📌 Page limit reached during priority preload")
                await context.close()
                await browser.close()
                self.save_results()
                return {
                    "company_name": self.company_name,
                    "company_id": self.company_id,
                    "status": "success",
                    "pages_crawled": len(self.pages_data),
                    "urls_visited": len(self.urls_visited)
                }
            
            page = await context.new_page()
            
            # SECOND: Ensure any remaining discovered page types are crawled (in case they weren't in priority)
            remaining_page_types = []
            for page_type, page_url in self.discovered_pages.items():
                if page_url and page_url not in self.urls_visited:
                    remaining_page_types.append((page_type, page_url))
                    # Add to priority to ensure they're crawled
                    self.priority_urls.add(page_url)
                    self.urls_to_visit.discard(page_url)
            
            if remaining_page_types:
                logger.info(f"  🔍 Ensuring {len(remaining_page_types)} remaining discovered page types are crawled...")
            
            # THIRD: Crawl all other discovered URLs (blog posts, job detail pages, etc.)
            while (self.urls_to_visit or self.priority_urls) and len(self.urls_visited) < self.max_pages:
                if self.priority_urls:
                    url = self.priority_urls.pop()
                    self.urls_to_visit.discard(url)
                else:
                    url = self.urls_to_visit.pop()
                
                if url in self.urls_visited:
                    continue
                if not is_same_domain(url, self.base_url):
                    continue
                await self.crawl_page(page, url)
                
                # Rate limiting (minimal for speed)
                await asyncio.sleep(0.2)
            
            # Final summary of page types extracted
            extracted_page_types = set()
            for page_data in self.pages_data:
                page_type = page_data.get("page_type")
                if page_type:
                    extracted_page_types.add(page_type)
                else:
                    # Try to infer from URL
                    url = page_data.get("url", "")
                    url_lower = url.lower()
                    if url_lower.rstrip('/') == self.base_url.lower().rstrip('/'):
                        extracted_page_types.add("homepage")
                    elif any(kw in url_lower for kw in ['/about', '/company']):
                        extracted_page_types.add("about")
                    elif any(kw in url_lower for kw in ['/career', '/job']):
                        extracted_page_types.add("careers")
                    elif any(kw in url_lower for kw in ['/blog', '/news']):
                        extracted_page_types.add("blog")
                    elif any(kw in url_lower for kw in ['/team', '/leadership']):
                        extracted_page_types.add("team")
                    elif any(kw in url_lower for kw in ['/investor', '/funding']):
                        extracted_page_types.add("investors")
                    elif any(kw in url_lower for kw in ['/customer', '/client']):
                        extracted_page_types.add("customers")
                    elif any(kw in url_lower for kw in ['/press', '/newsroom']):
                        extracted_page_types.add("press")
                    elif any(kw in url_lower for kw in ['/pricing', '/plans']):
                        extracted_page_types.add("pricing")
                    elif any(kw in url_lower for kw in ['/partner', '/integration']):
                        extracted_page_types.add("partners")
                    elif any(kw in url_lower for kw in ['/contact']):
                        extracted_page_types.add("contact")
                    elif any(kw in url_lower for kw in ['/product', '/platform']):
                        extracted_page_types.add("product")
            
            logger.info(f"  📊 Final summary: Extracted {len(extracted_page_types)}/12 page types: {', '.join(sorted(extracted_page_types))}")
            missing_final = [pt for pt in PAGE_PATTERNS.keys() if pt not in extracted_page_types]
            if missing_final:
                logger.warning(f"  ⚠️  Page types NOT extracted: {', '.join(missing_final)}")
            
            await browser.close()
        
        # Save all data
        self.save_results()
        
        return {
            "company_name": self.company_name,
            "company_id": self.company_id,
            "status": "success",
            "pages_crawled": len(self.pages_data),
            "urls_visited": len(self.urls_visited)
        }
    
    def extract_entities_from_data(self) -> Dict[str, Any]:
        """Extract entities (jobs, team, products, news articles, etc.) from all collected data - COMPREHENSIVE"""
        entities = {
            "jobs": [],
            "team_members": [],
            "products": [],
            "customers": [],
            "partners": [],
            "investors": [],
            "funding_events": [],
            "events": [],
            "press_releases": [],
            "news_articles": [],
            "company_info": {
                "legal_name": None,
                "brand_name": None,
                "founded_year": None,
                "headquarters": None,
                "hq_city": None,
                "hq_state": None,
                "hq_country": None,
                "description": None,
                "categories": [],
                "related_companies": []
            },
            "pricing": {
                "model": None,
                "tiers": []
            },
            "snapshot_data": {
                "headcount_total": None,
                "headcount_growth_pct": None,
                "job_openings_count": None,
                "engineering_openings": None,
                "sales_openings": None,
                "hiring_focus": [],
                "geo_presence": []
            },
            "visibility_data": {
                "github_stars": None,
                "glassdoor_rating": None
            }
        }
        
        # Extract from all page data
        for page_data in self.pages_data:
            # 1. Extract jobs that were already extracted from pages
            if "extracted_jobs" in page_data:
                entities["jobs"].extend(page_data["extracted_jobs"])
            
            # 2. Extract news articles
            if "extracted_article" in page_data:
                article = page_data["extracted_article"]
                if article.get("title") or article.get("content"):
                    entities["news_articles"].append(article)
            
            # 3. Extract from JSON-LD
            for item in page_data["structured_data"]["json_ld"]:
                if isinstance(item, dict):
                    item_type = item.get("@type", "")
                    
                    if item_type == "JobPosting":
                        job = {
                            "title": item.get("title"),
                            "description": item.get("description"),
                            "location": item.get("jobLocation", {}).get("name") if isinstance(item.get("jobLocation"), dict) else str(item.get("jobLocation", "")),
                            "employmentType": item.get("employmentType"),
                            "datePosted": item.get("datePosted"),
                            "source": "json_ld",
                            "url": item.get("url") or page_data["url"]
                        }
                        entities["jobs"].append(job)
                    elif item_type == "Person":
                        entities["team_members"].append({
                            "name": item.get("name"),
                            "jobTitle": item.get("jobTitle"),
                            "description": item.get("description"),
                            "sameAs": item.get("sameAs"),
                            "source": "json_ld",
                            "url": page_data["url"]
                        })
                    elif item_type == "Product":
                        entities["products"].append({
                            "name": item.get("name"),
                            "description": item.get("description"),
                            "brand": item.get("brand", {}).get("name") if isinstance(item.get("brand"), dict) else item.get("brand"),
                            "source": "json_ld",
                            "url": page_data["url"]
                        })
                    elif item_type == "Organization":
                        # Could be customer, partner, or investor
                        org_name = item.get("name")
                        org_url = item.get("url")
                        context = page_data["url"].lower()
                        
                        if any(kw in context for kw in ["customer", "client", "case-study"]):
                            entities["customers"].append({"name": org_name, "url": org_url, "source": "json_ld"})
                        elif any(kw in context for kw in ["partner", "integration"]):
                            entities["partners"].append({"name": org_name, "url": org_url, "source": "json_ld"})
                        elif any(kw in context for kw in ["investor", "backer", "funding"]):
                            entities["investors"].append({"name": org_name, "url": org_url, "source": "json_ld"})
            
            # 4. Extract from embedded JSON (if not already extracted)
            for json_data in page_data["structured_data"]["embedded_json"]:
                found_jobs = find_jobs_in_embedded_data(json_data)
                entities["jobs"].extend(found_jobs)
            
            # 4.5. Extract team members from HTML (ALL PAGES - not just team/about pages)
            url_lower = page_data["url"].lower()
            html = page_data.get("raw_html", "")
            
            # Extract team members from ALL pages (prioritize team/about pages but check all)
            if html:
                # Only extract if we haven't found many team members yet, OR if this is a team/about page
                is_team_page = any(kw in url_lower for kw in ['/team', '/about', '/leadership', '/people'])
                if is_team_page or len(entities["team_members"]) < 5:
                    team_members_html = self._extract_team_from_html(html, page_data["url"])
                    entities["team_members"].extend(team_members_html)
            
            # 4.6. Extract products from HTML (ALL PAGES - not just product pages)
            if html:
                # Only extract if we haven't found many products yet, OR if this is a product page
                is_product_page = any(kw in url_lower for kw in ['/product', '/products', '/platform', '/solutions'])
                if is_product_page or len(entities["products"]) < 3:
                    products_html = self._extract_products_from_html(html, page_data["url"])
                    entities["products"].extend(products_html)
            
            # 4.7. Extract company info from HTML (ALL PAGES - prioritize about pages)
            if html:
                # Always try to extract company info, but prioritize about pages
                is_about_page = any(kw in url_lower for kw in ['/about', '/company'])
                company_info_html = self._extract_company_info_from_html(html, page_data["url"])
                
                # Only update if we don't have the info yet, OR if this is an about page (overwrite)
                if company_info_html.get("founded_year"):
                    if not entities["company_info"]["founded_year"] or is_about_page:
                        entities["company_info"]["founded_year"] = company_info_html["founded_year"]
                
                # Brand name
                if company_info_html.get("brand_name"):
                    if not entities["company_info"]["brand_name"] or is_about_page:
                        entities["company_info"]["brand_name"] = company_info_html["brand_name"]
                
                # Legal name
                if company_info_html.get("legal_name"):
                    if not entities["company_info"]["legal_name"] or is_about_page:
                        entities["company_info"]["legal_name"] = company_info_html["legal_name"]
                
                def _invalid_hq(value: Any) -> bool:
                    if not value:
                        return True
                    if isinstance(value, str):
                        return value.lower().startswith(("http://", "https://"))
                    if isinstance(value, list):
                        return all(_invalid_hq(v) for v in value)
                    return False
                
                new_hq = company_info_html.get("headquarters")
                if new_hq:
                    if (not entities["company_info"]["headquarters"] or _invalid_hq(entities["company_info"]["headquarters"]) or is_about_page):
                        entities["company_info"]["headquarters"] = new_hq
                
                # HQ city, state, country separately
                if company_info_html.get("hq_city"):
                    if not entities["company_info"]["hq_city"] or is_about_page:
                        entities["company_info"]["hq_city"] = company_info_html["hq_city"]
                if company_info_html.get("hq_state"):
                    if not entities["company_info"]["hq_state"] or is_about_page:
                        entities["company_info"]["hq_state"] = company_info_html["hq_state"]
                if company_info_html.get("hq_country"):
                    if not entities["company_info"]["hq_country"] or is_about_page:
                        entities["company_info"]["hq_country"] = company_info_html["hq_country"]
                
                if company_info_html.get("description"):
                    if not entities["company_info"]["description"] or is_about_page:
                        entities["company_info"]["description"] = company_info_html["description"]
                
                if company_info_html.get("categories"):
                    if not isinstance(entities["company_info"]["categories"], list):
                        entities["company_info"]["categories"] = []
                    entities["company_info"]["categories"].extend(company_info_html["categories"])
                
                # Related companies
                if company_info_html.get("related_companies"):
                    if not isinstance(entities["company_info"]["related_companies"], list):
                        entities["company_info"]["related_companies"] = []
                    entities["company_info"]["related_companies"].extend(company_info_html["related_companies"])
            
            # 4.8. Extract customers/partners from HTML and structured pages
            if "extracted_customers" in page_data:
                for customer_name in page_data["extracted_customers"]:
                    entities["customers"].append({
                        "name": customer_name,
                        "source": "customers_page",
                        "url": page_data["url"]
                    })
            
            if "extracted_partners" in page_data:
                for partner_name in page_data["extracted_partners"]:
                    entities["partners"].append({
                        "name": partner_name,
                        "source": "partners_page",
                        "url": page_data["url"]
                    })
            
            if html:
                if any(kw in url_lower for kw in ['/customer', '/client', '/case-study']):
                    customers_html = self._extract_customers_from_html(html, page_data["url"])
                    entities["customers"].extend(customers_html)
                elif any(kw in url_lower for kw in ['/partner', '/integration']):
                    partners_html = self._extract_partners_from_html(html, page_data["url"])
                    entities["partners"].extend(partners_html)
            
            # 5. Extract company info from structured data
            for item in page_data["structured_data"]["json_ld"]:
                if isinstance(item, dict) and item.get("@type") == "Organization":
                    # Legal name and brand name
                    if not entities["company_info"]["legal_name"]:
                        entities["company_info"]["legal_name"] = item.get("legalName")
                    if not entities["company_info"]["brand_name"]:
                        entities["company_info"]["brand_name"] = item.get("name")
                    
                    if not entities["company_info"]["founded_year"]:
                        # Try to extract founded year
                        founding_date = item.get("foundingDate")
                        if founding_date:
                            year_match = re.search(r'\d{4}', str(founding_date))
                            if year_match:
                                entities["company_info"]["founded_year"] = int(year_match.group(0))
                    
                    # Extract HQ details (city, state, country separately)
                    if not entities["company_info"]["headquarters"]:
                        address = item.get("address")
                        if isinstance(address, dict):
                            city = address.get("addressLocality")
                            state = address.get("addressRegion")
                            country = address.get("addressCountry")
                            # Convert to strings if they're not already
                            city = str(city) if city else None
                            state = str(state) if state else None
                            country = str(country) if country else None
                            
                            # Store separately
                            if city:
                                entities["company_info"]["hq_city"] = city
                            if state:
                                entities["company_info"]["hq_state"] = state
                            if country:
                                entities["company_info"]["hq_country"] = country
                            
                            # Also store combined
                            if city:
                                hq_parts = [p for p in [city, state, country] if p]
                                entities["company_info"]["headquarters"] = ", ".join(hq_parts)
                    
                    if not entities["company_info"]["description"]:
                        entities["company_info"]["description"] = item.get("description")
                    
                    # Categories
                    if item.get("industry"):
                        industry = item["industry"]
                        if isinstance(industry, list):
                            entities["company_info"]["categories"].extend(industry)
                        else:
                            entities["company_info"]["categories"].append(industry)
            
            # 6. Extract funding events from text content AND from structured investors/press pages
            # First check if this page has extracted investors/press data
            if "extracted_investors" in page_data:
                for investor_item in page_data["extracted_investors"]:
                    if investor_item.get("type") == "funding_mention":
                        snippet = investor_item.get("snippet", "")
                        # Try to extract amount from snippet
                        amount = self._parse_amount(snippet)
                        if amount and amount >= 100000:
                            entities["funding_events"].append({
                                "amount_usd": amount,
                                "description": snippet,
                                "source": "investors_page",
                                "url": page_data["url"]
                            })
            
            if "extracted_press" in page_data:
                for press_item in page_data["extracted_press"]:
                    title = press_item.get("title", "")
                    # Check if title mentions funding
                    if any(kw in title.lower() for kw in ['funding', 'raised', 'investment', 'series', 'round']):
                        # Try to extract amount from title
                        amount = self._parse_amount(title)
                        if amount and amount >= 100000:
                            entities["funding_events"].append({
                                "amount_usd": amount,
                                "description": title,
                                "date": press_item.get("date"),
                                "source": "press_page",
                                "url": press_item.get("url") or page_data["url"]
                            })
            
            # Also extract from text content (improved patterns with dates)
            text_content = page_data.get("text_content", {}).get("full_text", "")
            if text_content:
                # Look for funding announcements (more comprehensive patterns)
                funding_patterns = [
                    r'(?:raised|raising|secured|closed|landed|announced|bagged|snagged)\s+(?:an\s+|a\s+|about\s+|around\s+|approximately\s+|nearly\s+|over\s+|more than\s+|up to\s+|almost\s+)?(\$[\d\.,]+(?:\s*(?:billion|million|thousand|bn|mn|m|k))?)',
                    r'(?:series\s+[A-Z][^$]{0,60}?)(\$[\d\.,]+(?:\s*(?:billion|million|thousand|bn|mn|m|k))?)',
                    r'(\$[\d\.,]+(?:\s*(?:billion|million|thousand|bn|mn|m|k))?)\s+(?:financing|funding|investment|round|raise)',
                    r'investment\s+of\s+(?:approximately\s+|about\s+|around\s+|over\s+|up to\s+|nearly\s+)?(\$[\d\.,]+(?:\s*(?:billion|million|thousand|bn|mn|m|k))?)',
                ]
                for pattern in funding_patterns:
                    matches = re.finditer(pattern, text_content, re.IGNORECASE)
                    for match in matches:
                        amount_str = match.group(1)
                        # Convert to number
                        amount = self._parse_amount(amount_str)
                        if amount and amount >= 100000:  # Only significant amounts (>= $100K)
                            # Extract round name if available
                            context_start = max(0, match.start()-200)
                            context_end = min(len(text_content), match.end()+200)
                            context = text_content[context_start:context_end]
                            
                            # Try to find round name (Series A, Seed, etc.)
                            round_match = re.search(r'(series\s+[A-Z]|seed|pre-seed|angel|bridge)', context, re.IGNORECASE)
                            round_name = round_match.group(0) if round_match else None
                            
                            # Try to extract date from context or page metadata
                            date_str = None
                            # Look for dates in context (various formats)
                            date_patterns = [
                                r'([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})',  # November 18, 2022
                                r'(\d{4}-\d{2}-\d{2})',  # 2022-11-18
                                r'([A-Z][a-z]+\s+\d{4})',  # November 2022
                                r'(\d{1,2}/\d{1,2}/\d{4})',  # 11/18/2022
                            ]
                            for date_pattern in date_patterns:
                                date_match = re.search(date_pattern, context)
                                if date_match:
                                    date_str = date_match.group(1)
                                    break
                            
                            # If no date in context, try page metadata
                            if not date_str:
                                page_metadata = page_data.get("metadata", {})
                                # Check if page has date in title or description
                                title = page_metadata.get("title", "")
                                desc = page_metadata.get("description", "")
                                for date_pattern in date_patterns:
                                    for text in [title, desc]:
                                        date_match = re.search(date_pattern, text)
                                        if date_match:
                                            date_str = date_match.group(1)
                                            break
                                    if date_str:
                                        break
                            
                            # If still no date, use page timestamp (but mark as approximate)
                            if not date_str:
                                page_timestamp = page_data.get("timestamp", "")
                                if page_timestamp:
                                    try:
                                        from dateutil import parser as date_parser
                                        dt = date_parser.parse(page_timestamp)
                                        date_str = dt.strftime("%Y-%m-%d")
                                    except:
                                        pass
                            
                            funding_event = {
                                "amount_usd": amount,
                                "round_name": round_name,
                                "description": context,
                                "source": "text_extraction",
                                "url": page_data["url"]
                            }
                            
                            # Add date if found
                            if date_str:
                                funding_event["date"] = date_str
                                funding_event["occurred_on"] = date_str  # Also add for compatibility
                            
                            entities["funding_events"].append(funding_event)
            
            # 7. Extract pricing from pricing pages (use structured extraction if available)
            if "extracted_pricing" in page_data:
                pricing_data = page_data["extracted_pricing"]
                if pricing_data.get("pricing_model"):
                    entities["pricing"]["model"] = pricing_data["pricing_model"]
                if pricing_data.get("tiers"):
                    entities["pricing"]["tiers"] = pricing_data["tiers"]
            
            # Also extract from text content
            url_lower = page_data["url"].lower()
            if any(kw in url_lower for kw in ["/pricing", "/plans", "/prices"]):
                # Look for pricing tiers
                pricing_text = page_data.get("text_content", {}).get("full_text", "")
                # Common pricing patterns
                tier_patterns = [
                    r'(?:free|basic|starter|pro|enterprise|premium|business|team|individual)',
                    r'\$\d+[\/\s]?(?:month|year|user|seat)',
                ]
                for pattern in tier_patterns:
                    matches = re.finditer(pattern, pricing_text, re.IGNORECASE)
                    for match in matches:
                        tier = match.group(0)
                        if tier not in entities["pricing"]["tiers"]:
                            entities["pricing"]["tiers"].append(tier)
                
                # Extract pricing model (seat-based, usage-based, tiered)
                if not entities["pricing"]["model"]:
                    pricing_lower = pricing_text.lower()
                    if any(kw in pricing_lower for kw in ['per seat', 'per user', 'per employee']):
                        entities["pricing"]["model"] = "seat"
                    elif any(kw in pricing_lower for kw in ['per api call', 'per request', 'usage-based', 'pay as you go']):
                        entities["pricing"]["model"] = "usage"
                    elif any(kw in pricing_lower for kw in ['tier', 'plan', 'package']):
                        entities["pricing"]["model"] = "tiered"
            
            # 8. Extract snapshot data (headcount, job openings, geo presence) from ALL pages
            text_content = page_data.get("text_content", {}).get("full_text", "")
            if text_content:
                # Headcount
                if not entities["snapshot_data"]["headcount_total"]:
                    headcount_patterns = [
                        r'(\d+)\+?\s+employees',
                        r'team\s+of\s+(\d+)',
                        r'(\d+)\s+people',
                        r'headcount[:\s]+(\d+)',
                        r'(\d+)\s+team\s+members',
                    ]
                    for pattern in headcount_patterns:
                        match = re.search(pattern, text_content, re.IGNORECASE)
                        if match:
                            try:
                                headcount = int(match.group(1))
                                if 10 <= headcount <= 100000:
                                    entities["snapshot_data"]["headcount_total"] = headcount
                                    break
                            except:
                                pass
                
                # Job openings count
                if not entities["snapshot_data"]["job_openings_count"]:
                    job_patterns = [
                        r'(\d+)\s+open\s+(?:positions|roles|jobs)',
                        r'(\d+)\s+(?:positions|roles|jobs)\s+available',
                        r'hiring\s+for\s+(\d+)\s+(?:positions|roles)',
                        r'(\d+)\s+openings',
                    ]
                    for pattern in job_patterns:
                        match = re.search(pattern, text_content, re.IGNORECASE)
                        if match:
                            try:
                                count = int(match.group(1))
                                if 1 <= count <= 1000:
                                    entities["snapshot_data"]["job_openings_count"] = count
                                    break
                            except:
                                pass
                
                # Engineering openings
                if not entities["snapshot_data"]["engineering_openings"]:
                    eng_patterns = [
                        r'(\d+)\s+engineering\s+(?:positions|roles|openings)',
                        r'(\d+)\s+(?:software|backend|frontend|fullstack)\s+engineer',
                    ]
                    for pattern in eng_patterns:
                        match = re.search(pattern, text_content, re.IGNORECASE)
                        if match:
                            try:
                                count = int(match.group(1))
                                if 1 <= count <= 500:
                                    entities["snapshot_data"]["engineering_openings"] = count
                                    break
                            except:
                                pass
                
                # Sales openings
                if not entities["snapshot_data"]["sales_openings"]:
                    sales_patterns = [
                        r'(\d+)\s+sales\s+(?:positions|roles|openings)',
                        r'(\d+)\s+(?:account\s+executive|sales\s+rep)',
                    ]
                    for pattern in sales_patterns:
                        match = re.search(pattern, text_content, re.IGNORECASE)
                        if match:
                            try:
                                count = int(match.group(1))
                                if 1 <= count <= 500:
                                    entities["snapshot_data"]["sales_openings"] = count
                                    break
                            except:
                                pass
                
                # Hiring focus (departments)
                hiring_focus_keywords = ['engineering', 'sales', 'marketing', 'product', 'design', 'ml', 'ai', 'security', 'operations', 'customer success']
                for keyword in hiring_focus_keywords:
                    if keyword in text_content.lower() and keyword not in entities["snapshot_data"]["hiring_focus"]:
                        # Check if it's in context of hiring
                        context_pattern = rf'(?:hiring|looking for|seeking|open roles?)\s+.*?{keyword}'
                        if re.search(context_pattern, text_content, re.IGNORECASE):
                            entities["snapshot_data"]["hiring_focus"].append(keyword)
                
                # Geo presence (office locations)
                geo_patterns = [
                    r'(?:office|location|headquarters?)\s+(?:in|at)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
                    r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+office',
                ]
                for pattern in geo_patterns:
                    matches = re.finditer(pattern, text_content, re.IGNORECASE)
                    for match in matches:
                        location = match.group(1).strip()
                        if len(location) < 50 and location not in entities["snapshot_data"]["geo_presence"]:
                            entities["snapshot_data"]["geo_presence"].append(location)
            
            # 9. Extract visibility data (GitHub stars, Glassdoor rating)
            html = page_data.get("raw_html", "")
            if html:
                soup = BeautifulSoup(html, 'lxml')
                
                # GitHub stars
                if not entities["visibility_data"]["github_stars"]:
                    github_links = soup.find_all('a', href=lambda x: x and 'github.com' in str(x).lower() if x else False)
                    for link in github_links:
                        # Try to find star count near the link
                        parent = link.parent
                        if parent:
                            text = parent.get_text()
                            star_match = re.search(r'(\d+(?:,\d+)?)\s*(?:stars?|⭐)', text, re.IGNORECASE)
                            if star_match:
                                try:
                                    stars = int(star_match.group(1).replace(',', ''))
                                    if stars > 0:
                                        entities["visibility_data"]["github_stars"] = stars
                                        break
                                except:
                                    pass
                
                # Glassdoor rating
                if not entities["visibility_data"]["glassdoor_rating"]:
                    glassdoor_patterns = [
                        r'glassdoor[:\s]+(\d+\.?\d*)',
                        r'(\d+\.?\d*)\s+(?:stars?|rating)\s+on\s+glassdoor',
                        r'rated\s+(\d+\.?\d*)\s+on\s+glassdoor',
                    ]
                    text_content = page_data.get("text_content", {}).get("full_text", "")
                    for pattern in glassdoor_patterns:
                        match = re.search(pattern, text_content, re.IGNORECASE)
                        if match:
                            try:
                                rating = float(match.group(1))
                                if 0 <= rating <= 5:
                                    entities["visibility_data"]["glassdoor_rating"] = rating
                                    break
                            except:
                                pass
        
        entities["jobs"] = dedupe_jobs_list(entities["jobs"])
        entities["team_members"] = dedupe_by_field(entities["team_members"], "name")
        entities["products"] = dedupe_by_field(entities["products"], "name")
        entities["news_articles"] = dedupe_articles_list(entities["news_articles"])
        entities["funding_events"] = dedupe_by_field(entities["funding_events"], "amount_usd")
        
        # Clean company info values
        hq_value = entities["company_info"].get("headquarters")
        if isinstance(hq_value, list):
            filtered = [
                str(item).strip()
                for item in hq_value
                if isinstance(item, str) and not item.lower().startswith(("http://", "https://"))
            ]
            entities["company_info"]["headquarters"] = ", ".join(filtered) if filtered else None
        elif isinstance(hq_value, str):
            if hq_value.lower().startswith(("http://", "https://")):
                entities["company_info"]["headquarters"] = None
            else:
                entities["company_info"]["headquarters"] = hq_value.strip()
        
        # Deduplicate categories (convert to strings and remove duplicates)
        if entities["company_info"]["categories"]:
            categories = []
            for cat in entities["company_info"]["categories"]:
                if isinstance(cat, str):
                    categories.append(cat)
                elif isinstance(cat, list):
                    categories.extend([str(c) for c in cat if c])
                else:
                    categories.append(str(cat))
            entities["company_info"]["categories"] = list(dict.fromkeys(categories))  # Preserve order, remove duplicates
            filtered = []
            for cat in entities["company_info"]["categories"]:
                cat_norm = cat.strip()
                lower = cat_norm.lower()
                if not cat_norm:
                    continue
                if len(cat_norm) > 50:
                    continue
                if any(lower.startswith(prefix) for prefix in ['find ', 'see ', 'explore ', 'discover ', 'solution', 'solutions', 'products', 'product', 'resources', 'pricing']):
                    continue
                filtered.append(cat_norm)
            entities["company_info"]["categories"] = filtered
        
        return entities
    
    def _parse_amount(self, amount_str: str) -> Optional[float]:
        """Parse amount string like $10M, $5.5B, $100K to float"""
        try:
            if not amount_str:
                return None
            normalized = amount_str.lower().strip()
            # Remove qualifiers
            normalized = re.sub(r'^(about|around|approximately|nearly|over|more than|up to|almost)\s+', '', normalized)
            normalized = normalized.replace('usd', '').replace('us$', '').strip()
            normalized = normalized.replace('~', '')
            
            # Remove dollar sign and commas later
            normalized = normalized.replace('$', '').replace(',', '').strip()

            multiplier = 1
            if any(token in normalized for token in ['billion', 'bn']):
                multiplier = 1_000_000_000
            elif any(token in normalized for token in ['million', 'mn', 'm']):
                multiplier = 1_000_000
            elif any(token in normalized for token in ['thousand', 'k']):
                multiplier = 1_000
            
            normalized = re.sub(r'(billion|million|thousand|bn|mn|m|k)', '', normalized)
            normalized = normalized.strip()
            if not normalized:
                return None
            value = float(normalized)
            return value * multiplier
        except Exception:
            return None
    
    def _extract_team_from_html(self, html: str, url: str) -> List[Dict]:
        """Extract team members from HTML with strict filtering"""
        team_members = []
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # Common team member selectors
            member_selectors = [
                '.team-member', '.person', '.employee', '.leadership-member',
                '[class*="team"]', '[class*="member"]', '[class*="person"]',
                'article[class*="team"]', 'div[class*="team"]'
            ]
            
            # Exclude patterns (false positives)
            exclude_keywords = [
                'office', 'location', 'benefits', 'pto', 'perks', 'roles', 'open roles',
                'unlimited', 'comprehensive', 'medical', 'dental', 'vision', 'insurance',
                'stipend', 'global family', 'about us', 'for business', 'seoul', 'ljubljana',
                'san francisco', 'korea', 'brooklyn', 'marketing', 'ops teams', 'engineering office'
            ]
            
            def is_valid_team_member(name: str, role: str = None) -> bool:
                """Check if this looks like a real team member"""
                if not name or len(name) < 3:
                    return False
                name_lower = name.lower()
                role_lower = (role or '').lower()
                
                # Must have at least one space (first + last name)
                if ' ' not in name:
                    return False
                
                # Exclude if matches exclude patterns
                if any(exclude in name_lower for exclude in exclude_keywords):
                    return False
                if role and any(exclude in role_lower for exclude in exclude_keywords):
                    return False
                
                # Exclude if it's clearly a location (starts with city/country name)
                if any(name_lower.startswith(loc) for loc in ['speak ', 'office', 'location']):
                    return False
                
                # Exclude if it's a benefit/perk
                if name_lower in ['unlimited pto', 'open roles', 'perks', 'benefits']:
                    return False
                
                # Must look like a person name (has capital letters, not all caps)
                words = name.split()
                if len(words) < 2 or len(words) > 4:
                    return False
                
                # Check if first word is capitalized (person name pattern)
                if not words[0][0].isupper():
                    return False
                
                return True
            
            for selector in member_selectors:
                members = soup.select(selector)
                if len(members) > 1:  # Found a pattern
                    for member in members[:30]:  # Limit to 30
                        member_data = {
                            "name": None,
                            "jobTitle": None,
                            "description": None,
                            "sameAs": None,
                            "source": "html_extraction",
                            "url": url
                        }
                        
                        # Extract name (try multiple tags)
                        name_tag = member.find(['h1', 'h2', 'h3', 'h4', 'h5', 'strong', 'span'], class_=lambda x: x and 'name' in str(x).lower() if x else False)
                        if not name_tag:
                            name_tag = member.find(['h2', 'h3', 'h4', 'strong'])
                        if name_tag:
                            member_data["name"] = name_tag.get_text().strip()
                        
                        # Extract role/title
                        role_classes = ['role', 'title', 'position', 'job-title', 'jobTitle']
                        for cls in role_classes:
                            role_tag = member.find(class_=lambda x: x and cls.lower() in str(x).lower() if x else False)
                            if role_tag:
                                member_data["jobTitle"] = role_tag.get_text().strip()
                                break
                        
                        # If no role found, try first p tag
                        if not member_data["jobTitle"]:
                            p_tags = member.find_all('p')
                            if len(p_tags) > 0:
                                first_p = p_tags[0].get_text().strip()
                                if len(first_p) < 150 and not first_p.lower().startswith('http'):
                                    member_data["jobTitle"] = first_p
                        
                        # Validate before adding
                        if member_data["name"] and is_valid_team_member(member_data["name"], member_data["jobTitle"]):
                            # Extract bio/description
                            bio_tag = member.find('p', class_=lambda x: x and 'bio' in str(x).lower() if x else False)
                            if not bio_tag:
                                p_tags = member.find_all('p')
                                if len(p_tags) > 1:
                                    member_data["description"] = p_tags[1].get_text().strip()[:500]
                            
                            # Extract LinkedIn
                            linkedin_link = member.find('a', href=lambda x: x and 'linkedin.com' in str(x).lower() if x else False)
                            if linkedin_link:
                                member_data["sameAs"] = linkedin_link.get('href')
                                member_data["linkedin"] = linkedin_link.get('href')
                            
                            # Extract education
                            education_patterns = [
                                r'(?:education|studied|degree|graduated)[:\s]+([A-Z][A-Za-z\s&,\.]+(?:University|College|Institute|School))',
                                r'([A-Z][A-Za-z\s&,\.]+(?:University|College|Institute|School))',
                            ]
                            member_text = member.get_text()
                            for pattern in education_patterns:
                                match = re.search(pattern, member_text)
                                if match:
                                    education = match.group(1).strip()
                                    if len(education) < 100:
                                        member_data["education"] = education
                                        break
                            
                            # Extract previous affiliation
                            prev_affiliation_patterns = [
                                r'(?:previously|formerly|prior to|before)[:\s]+([A-Z][A-Za-z0-9\s&,\.]+)',
                                r'(?:worked at|was at|joined from)[:\s]+([A-Z][A-Za-z0-9\s&,\.]+)',
                            ]
                            for pattern in prev_affiliation_patterns:
                                match = re.search(pattern, member_text, re.IGNORECASE)
                                if match:
                                    prev_aff = match.group(1).strip()
                                    if len(prev_aff) < 100:
                                        member_data["previous_affiliation"] = prev_aff
                                        break
                            
                            # Extract start/end dates
                            date_patterns = [
                                r'(?:joined|started|since)[:\s]+(\d{4})',
                                r'(\d{4})\s+[–-]\s+(?:present|current)',
                            ]
                            for pattern in date_patterns:
                                match = re.search(pattern, member_text, re.IGNORECASE)
                                if match:
                                    year = int(match.group(1))
                                    if 1990 <= year <= 2025:
                                        member_data["start_date"] = f"{year}-01-01"
                                        break
                            
                            # Check if founder
                            if 'founder' in member_text.lower() or 'co-founder' in member_text.lower():
                                member_data["is_founder"] = True
                            
                            team_members.append(member_data)
                    
                    if team_members:
                        break
            
            # Fallback: parse plain text sections such as "Executive team"
            if not team_members:
                text = soup.get_text(separator='\n')
                lines = [line.strip().strip('•').strip('-').strip('–') for line in text.split('\n')]
                lines = [line for line in lines if line]
                
                name_pattern = re.compile(r"^[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ'’`.-]+(?:\s+[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ'’`.-]+)+(?:\s+[IVX]{1,4})?$")
                title_keywords = [
                    'chief', 'ceo', 'cto', 'cfo', 'coo', 'cro', 'cpo', 'cmo', 'cio',
                    'founder', 'president', 'director', 'officer', 'head', 'lead',
                    'manager', 'partner', 'vp', 'svp', 'evp', 'executive', 'legal',
                    'people', 'finance', 'revenue', 'engineering', 'marketing',
                    'product', 'operations', 'policy', 'affairs', 'design', 'advisor',
                    'board', 'chair', 'chairman', 'chairperson'
                ]
                section_keywords = [
                    'executive team', 'leadership team', 'leadership', 'founders',
                    'management team', 'executive leadership', 'board of directors',
                    'senior leadership', 'our leaders'
                ]
                section_end_keywords = [
                    'news and insights', 'careers', 'products', 'solutions', 'resources',
                    'recent updates', 'locations', 'contact', 'investors', 'join us',
                    'born in', 'building worldwide'
                ]
                
                def is_name(value: str) -> bool:
                    if not value or len(value.split()) > 7:
                        return False
                    lower = value.lower()
                    if any(keyword in lower for keyword in title_keywords):
                        return False
                    if name_pattern.match(value):
                        return True
                    # Accept short names like "Tim Cook"
                    words = value.split()
                    if 1 < len(words) <= 4 and all(word and word[0].isupper() for word in words):
                        return True
                    return False
                
                def is_title(value: str) -> bool:
                    lower = value.lower()
                    if any(keyword in lower for keyword in title_keywords):
                        return True
                    words = value.split()
                    if 1 < len(words) <= 10 and any(ch.islower() for ch in value):
                        # If it's not a typical name and has lowercase words, treat as title
                        if not name_pattern.match(value):
                            return True
                    return False
                
                in_section = False
                pending_name: Optional[str] = None
                pending_title: Optional[str] = None
                
                for line in lines:
                    lower = line.lower()
                    
                    if any(k in lower for k in section_keywords):
                        in_section = True
                        pending_name = None
                        pending_title = None
                        continue
                    
                    if in_section and any(k in lower for k in section_end_keywords):
                        in_section = False
                        pending_name = None
                        pending_title = None
                        continue
                    
                    if not in_section:
                        continue
                    
                    if pending_name and is_title(line):
                        if not any(tm["name"].lower() == pending_name.lower() for tm in team_members):
                            team_members.append({
                                "name": pending_name,
                                "jobTitle": line,
                                "source": "html_pattern_section",
                                "url": url
                            })
                        pending_name = None
                        if len(team_members) >= 40:
                            break
                        continue
                    
                    if is_title(line) and not is_name(line):
                        pending_title = line
                        continue
                    
                    if is_name(line):
                        # Validate using the same function
                        if not is_valid_team_member(line, pending_title):
                            pending_name = None
                            pending_title = None
                            continue
                        
                        # If we have a pending title from previous line (title-first pattern)
                        if pending_title and not any(tm["name"].lower() == line.lower() for tm in team_members):
                            team_members.append({
                                "name": line,
                                "jobTitle": pending_title,
                                "source": "html_pattern_section",
                                "url": url
                            })
                            pending_title = None
                            continue
                        
                        # Otherwise store the name and wait for next title
                        pending_name = line
                        continue
                    
                if pending_name and is_valid_team_member(pending_name, pending_title) and not any(tm["name"].lower() == pending_name.lower() for tm in team_members):
                    team_members.append({
                        "name": pending_name,
                        "jobTitle": pending_title,
                        "source": "html_pattern_section",
                        "url": url
                    })
                
        except Exception as e:
            logger.debug(f"Team extraction failed for {url}: {e}")
        
        return team_members
    
    def _extract_products_from_html(self, html: str, url: str) -> List[Dict]:
        """Extract products from HTML - COMPREHENSIVE (pricing, github, license, customers)"""
        products = []
        try:
            soup = BeautifulSoup(html, 'lxml')
            text = soup.get_text(separator='\n')
            
            # Common product selectors
            product_selectors = [
                '.product', '.product-item', '.solution', '.feature',
                '[class*="product"]', '[class*="solution"]', 'article[class*="product"]'
            ]
            
            for selector in product_selectors:
                product_elements = soup.select(selector)
                if len(product_elements) > 1:  # Found a pattern
                    for elem in product_elements[:20]:  # Limit to 20
                        product_data = {
                            "name": None,
                            "description": None,
                            "pricing_model": None,
                            "pricing_tiers": [],
                            "github_repo": None,
                            "license_type": None,
                            "reference_customers": [],
                            "ga_date": None,
                            "integration_partners": [],
                            "source": "html_extraction",
                            "url": url
                        }
                        
                        # Extract name
                        name_tag = elem.find(['h1', 'h2', 'h3', 'h4', 'strong'])
                        if name_tag:
                            product_data["name"] = name_tag.get_text().strip()
                        
                        # Extract description
                        desc_tag = elem.find('p')
                        if desc_tag:
                            product_data["description"] = desc_tag.get_text().strip()[:500]
                        
                        # Extract GitHub repo
                        github_link = elem.find('a', href=lambda x: x and 'github.com' in str(x).lower() if x else False)
                        if github_link:
                            product_data["github_repo"] = github_link.get('href')
                        
                        # Extract license type
                        license_patterns = [
                            r'license[:\s]+(MIT|Apache|GPL|BSD|AGPL|LGPL|proprietary|commercial)',
                            r'(MIT|Apache|GPL|BSD|AGPL|LGPL)\s+license',
                        ]
                        elem_text = elem.get_text()
                        for pattern in license_patterns:
                            match = re.search(pattern, elem_text, re.IGNORECASE)
                            if match:
                                product_data["license_type"] = match.group(1)
                                break
                        
                        # Extract pricing info from product element
                        elem_text_lower = elem_text.lower()
                        if any(kw in elem_text_lower for kw in ['per seat', 'per user']):
                            product_data["pricing_model"] = "seat"
                        elif any(kw in elem_text_lower for kw in ['per api', 'usage-based', 'pay as you go']):
                            product_data["pricing_model"] = "usage"
                        elif any(kw in elem_text_lower for kw in ['tier', 'plan', 'package']):
                            product_data["pricing_model"] = "tiered"
                        
                        # Extract pricing tiers
                        tier_keywords = ['free', 'basic', 'starter', 'pro', 'enterprise', 'premium', 'business', 'team']
                        for keyword in tier_keywords:
                            if keyword in elem_text_lower:
                                product_data["pricing_tiers"].append(keyword.capitalize())
                        
                        # Extract integration partners
                        integration_links = elem.find_all('a', href=True)
                        for link in integration_links:
                            href = link.get('href', '')
                            if any(domain in href.lower() for domain in ['slack.com', 'microsoft.com', 'google.com', 'aws.com', 'azure.com', 'salesforce.com']):
                                partner_name = link.get_text().strip() or href
                                if partner_name and partner_name not in product_data["integration_partners"]:
                                    product_data["integration_partners"].append(partner_name)
                        
                        # Extract reference customers
                        customer_keywords = ['used by', 'trusted by', 'powered by', 'customer', 'client']
                        for keyword in customer_keywords:
                            if keyword in elem_text_lower:
                                # Look for company names after these keywords
                                context = elem_text[elem_text_lower.find(keyword):elem_text_lower.find(keyword)+200]
                                # Simple extraction - look for capitalized words
                                customer_matches = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b', context)
                                for match in customer_matches[:3]:  # Limit to 3
                                    if len(match) > 3 and match not in product_data["reference_customers"]:
                                        product_data["reference_customers"].append(match)
                        
                        # Extract GA/launch date
                        date_patterns = [
                            r'launched\s+(?:in\s+)?(\d{4})',
                            r'ga\s+(?:in\s+)?(\d{4})',
                            r'general\s+availability\s+(?:in\s+)?(\d{4})',
                        ]
                        for pattern in date_patterns:
                            match = re.search(pattern, elem_text, re.IGNORECASE)
                            if match:
                                try:
                                    year = int(match.group(1))
                                    if 2000 <= year <= 2025:
                                        product_data["ga_date"] = f"{year}-01-01"  # Approximate
                                        break
                                except:
                                    pass
                        
                        if product_data["name"]:
                            products.append(product_data)
                    
                    if products:
                        break
            
            # Fallback: extract from headings on product pages (with strict filtering)
            if not products:
                # Only use fallback on actual product pages
                url_lower = url.lower()
                is_product_page = any(kw in url_lower for kw in ['/product', '/products', '/platform', '/solutions', '/features'])
                
                if is_product_page:
                    headings = soup.find_all(['h1', 'h2', 'h3'])
                    # Filter out non-product headings
                    exclude_keywords = [
                        'products', 'solutions', 'features', 'overview', 'about', 'contact',
                        'careers', 'jobs', 'team', 'blog', 'news', 'press', 'resources',
                        'pricing', 'plans', 'sign up', 'login', 'get started', 'learn more',
                        'join', 'open roles', 'perks', 'benefits', 'life at', 'start learning',
                        'come build', 'explore', 'reinvent', 'global family', 'office'
                    ]
                    
                    for heading in headings[:15]:
                        text = heading.get_text().strip()
                        text_lower = text.lower()
                        
                        # Skip if it's a generic heading or matches exclude list
                        if not text or len(text) > 100:
                            continue
                        if any(exclude in text_lower for exclude in exclude_keywords):
                            continue
                        # Skip if it looks like a sentence (has lowercase words and is too long)
                        if len(text.split()) > 8:
                            continue
                        # Skip if it's clearly not a product name
                        if any(phrase in text_lower for phrase in ['click', 'read', 'view', 'see', 'learn', 'get', 'try']):
                            continue
                        
                        products.append({
                            "name": text,
                            "source": "html_heading",
                            "url": url
                        })
        
        except Exception as e:
            logger.debug(f"Product extraction failed for {url}: {e}")
        
        return products
    
    def _extract_company_info_from_html(self, html: str, url: str) -> Dict:
        """Extract company info (founded year, headquarters, description, brand_name, legal_name, related_companies) from HTML - COMPREHENSIVE"""
        info: Dict[str, Any] = {}
        try:
            soup = BeautifulSoup(html, 'lxml')
            text = soup.get_text(separator='\n')
            
            # Extract brand name (usually in h1 or title)
            brand_name = None
            h1_tag = soup.find('h1')
            if h1_tag:
                brand_name = h1_tag.get_text().strip()
                if len(brand_name) < 100:  # Reasonable brand name length
                    info["brand_name"] = brand_name
            
            # Extract legal name (often in footer or "Legal Name:" pattern)
            legal_name = None
            legal_patterns = [
                r'legal\s+name[:\s]+([A-Za-z0-9\s,&\.]+)',
                r'incorporated\s+as[:\s]+([A-Za-z0-9\s,&\.]+)',
                r'doing\s+business\s+as[:\s]+([A-Za-z0-9\s,&\.]+)',
            ]
            for pattern in legal_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    legal_name = match.group(1).strip()
                    if len(legal_name) < 200:
                        info["legal_name"] = legal_name
                        break
            
            # Extract related companies (competitors, alternatives, similar companies)
            related_companies = []
            related_patterns = [
                r'(?:competitor|alternative|similar|compared to|vs\.?|versus)\s+([A-Z][A-Za-z0-9\s&\.]+)',
                r'like\s+([A-Z][A-Za-z0-9\s&\.]+)',
            ]
            for pattern in related_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    company_name = match.group(1).strip()
                    # Filter out common false positives
                    if len(company_name) < 50 and company_name.lower() not in ['the', 'a', 'an', 'this', 'that']:
                        related_companies.append(company_name)
            
            if related_companies:
                info["related_companies"] = list(set(related_companies))[:10]  # Limit to 10
            
            # Extract founded year
            founded_patterns = [
                r'founded\s+(?:in\s+)?(\d{4})',
                r'established\s+(?:in\s+)?(\d{4})',
                r'started\s+(?:in\s+)?(\d{4})',
                r'(\d{4})\s+[–-]\s+founded',
            ]
            for pattern in founded_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    year = int(match.group(1))
                    if 1900 <= year <= 2030:  # Sanity check
                        info["founded_year"] = year
                        break
            
            # Extract headquarters (with better filtering) - also extract city/state/country separately
            hq_patterns = [
                r'headquarters?[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:,\s*[A-Z]{2})?(?:,\s*[A-Z][a-z]+)?)',
                r'based\s+in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:,\s*[A-Z]{2})?(?:,\s*[A-Z][a-z]+)?)',
                r'located\s+in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:,\s*[A-Z]{2})?(?:,\s*[A-Z][a-z]+)?)',
                r'headquartered\s+in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:,\s*[A-Z]{2})?(?:,\s*[A-Z][a-z]+)?)',
            ]
            for pattern in hq_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    hq = match.group(1).strip()
                    hq_lower = hq.lower()
                    
                    # Filter out invalid HQ values
                    invalid_patterns = [
                        'and international', 'can be found', 'offices', 'office',
                        'locations', 'location', 'where', 'here', 'there',
                        'contact', 'email', 'phone', 'address', 'visit'
                    ]
                    
                    if any(invalid in hq_lower for invalid in invalid_patterns):
                        continue
                    
                    # Must look like a city/state/country (not a sentence)
                    if len(hq.split()) > 5:
                        continue
                    
                    if len(hq) < 100 and len(hq) > 3:
                        info["headquarters"] = hq
                        
                        # Parse city, state, country from HQ string
                        hq_parts = [p.strip() for p in hq.split(',')]
                        if len(hq_parts) >= 1:
                            info["hq_city"] = hq_parts[0]
                        if len(hq_parts) >= 2:
                            # Check if it's a state abbreviation (2 letters) or state name
                            state_part = hq_parts[1]
                            if len(state_part) == 2 and state_part.isupper():
                                info["hq_state"] = state_part
                            elif len(state_part) > 2:
                                info["hq_state"] = state_part
                        if len(hq_parts) >= 3:
                            info["hq_country"] = hq_parts[2]
                        elif len(hq_parts) == 2 and not (len(hq_parts[1]) == 2 and hq_parts[1].isupper()):
                            # If only 2 parts and second isn't a state code, treat as country
                            info["hq_country"] = hq_parts[1]
                        
                        break
            
            if not info.get("headquarters"):
                # Look for lines that start with "Location" or "HQ"
                for line in text.split('\n'):
                    line_clean = line.strip()
                    if not line_clean:
                        continue
                    if re.match(r'^(hq|location|global hq)[:\s]+', line_clean, re.IGNORECASE):
                        hq = re.sub(r'^(hq|location|global hq)[:\s]+', '', line_clean, flags=re.IGNORECASE).strip()
                        if hq and not hq.lower().startswith('http') and len(hq) < 100:
                            info["headquarters"] = hq
                            break
            
            if not info.get("headquarters"):
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                for idx, line in enumerate(lines):
                    lower = line.lower()
                    if 'born in' in lower:
                        country = line.split('in', 1)[-1]
                        country = re.sub(r'[^A-Za-z\s]', '', country).strip()
                        city = None
                        for next_line in lines[idx+1:idx+6]:
                            candidate = re.sub(r'[^A-Za-z\s-]', '', next_line).strip()
                            if not candidate:
                                continue
                            if 'building' in candidate.lower():
                                continue
                            if len(candidate.split()) <= 4 and candidate[0].isupper():
                                city = candidate
                                break
                        if city:
                            info["headquarters"] = f"{city}, {country}" if country else city
                            break
                        elif country:
                            info["headquarters"] = country
                            break
            
            # Extract description (first substantial paragraph)
            desc_tag = soup.find('p', class_=lambda x: x and 'description' in str(x).lower() if x else False)
            if not desc_tag:
                desc_tag = soup.find('div', class_=lambda x: x and 'description' in str(x).lower() if x else False)
            if desc_tag:
                desc = desc_tag.get_text().strip()
                if 50 < len(desc) < 1000:
                    info["description"] = desc
            
            if not info.get("description"):
                # Fallback to meta description
                meta_desc = soup.find('meta', attrs={'name': 'description'})
                if not meta_desc:
                    meta_desc = soup.find('meta', attrs={'property': 'og:description'})
                if meta_desc and meta_desc.get('content'):
                    desc = meta_desc['content'].strip()
                    if len(desc) >= 40:
                        info["description"] = desc[:1000]
            
            # Extract categories from meta keywords (with strict filtering)
            categories: List[str] = []
            meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
            if meta_keywords and meta_keywords.get('content'):
                for kw in meta_keywords['content'].split(','):
                    kw_clean = kw.strip()
                    # Filter out sentence fragments
                    if kw_clean and len(kw_clean) < 50 and len(kw_clean) > 2:
                        kw_lower = kw_clean.lower()
                        # Exclude common false positives
                        if not any(exclude in kw_lower for exclude in [
                            'most', 'profoundly', 'transformed', 'agnostic', 'has a number',
                            'particularly', 'compelling', 'use cases', 'specification',
                            'case studies', 'and', 'the', 'is', 'are', 'was', 'were',
                            'language', 'learning', 'education', 'tutor', 'app', 'platform'
                        ]):
                            # Exclude single words that are too generic
                            if len(kw_clean.split()) == 1 and kw_lower in ['agnostic', 'specification', 'studies', 'cases']:
                                continue
                            # Must be a single word or short phrase (not a sentence)
                            if len(kw_clean.split()) <= 3:
                                categories.append(kw_clean)
            
            # Look for inline labels like "Industry: ..." (with better filtering)
            if not categories:
                category_pattern = re.compile(r'(?:industry|sector|category)[:\s]+([A-Za-z &/,-]{3,40})', re.IGNORECASE)
                for match in category_pattern.finditer(text):
                    value = match.group(1).strip()
                    value_lower = value.lower()
                    
                    # Filter out sentence fragments
                    if value and len(value) < 40 and len(value) > 2:
                        # Exclude if it looks like a sentence (has common sentence words)
                        if not any(sentence_word in value_lower for sentence_word in [
                            'most', 'profoundly', 'transformed', 'has a', 'number of',
                            'particularly', 'compelling', 'use cases', 'and', 'the', 'is', 'are'
                        ]):
                            # Must be short (1-3 words typically)
                            if len(value.split()) <= 3:
                                categories.append(value)
            
            if categories:
                info["categories"] = categories
        
        except Exception as e:
            logger.debug(f"Company info extraction failed for {url}: {e}")
        
        return info
    
    def _extract_customers_from_html(self, html: str, url: str) -> List[Dict]:
        """Extract customer names from HTML"""
        customers = []
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # Look for customer logos or names
            customer_selectors = [
                '.customer', '.client', '.case-study',
                '[class*="customer"]', '[class*="client"]', '[alt*="customer"]', '[alt*="client"]'
            ]
            
            for selector in customer_selectors:
                elements = soup.select(selector)
                for elem in elements[:30]:
                    # Try to get name from alt text, title, or text content
                    name = elem.get('alt') or elem.get('title') or elem.get_text().strip()
                    if name and len(name) < 100 and name.lower() not in ['customer', 'client', 'logo']:
                        customers.append({
                            "name": name,
                            "source": "html_extraction",
                            "url": url
                        })
        
        except Exception as e:
            logger.debug(f"Customer extraction failed for {url}: {e}")
        
        return customers
    
    def _extract_partners_from_html(self, html: str, url: str) -> List[Dict]:
        """Extract partner names from HTML"""
        partners = []
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # Look for partner logos or names
            partner_selectors = [
                '.partner', '.integration',
                '[class*="partner"]', '[alt*="partner"]'
            ]
            
            for selector in partner_selectors:
                elements = soup.select(selector)
                for elem in elements[:30]:
                    name = elem.get('alt') or elem.get('title') or elem.get_text().strip()
                    if name and len(name) < 100 and name.lower() not in ['partner', 'integration', 'logo']:
                        partners.append({
                            "name": name,
                            "source": "html_extraction",
                            "url": url
                        })
        
        except Exception as e:
            logger.debug(f"Partner extraction failed for {url}: {e}")
        
        return partners
    
    def _parse_investors_page(self, html: str) -> List[Dict]:
        """Extract investor and funding information (from scraper.py)"""
        investors_data = []
        try:
            soup = BeautifulSoup(html, 'lxml')
            text = soup.get_text()
            
            # Look for funding round mentions
            funding_patterns = [
                r'(seed|series [a-z]|series [0-9])\s+round',
                r'raised\s+\$?([\d.]+)\s*(million|billion|m|b)',
                r'\$?([\d.]+)\s*(million|billion|m|b)\s+in\s+funding'
            ]
            
            for pattern in funding_patterns:
                matches = re.finditer(pattern, text.lower())
                for match in matches:
                    investors_data.append({
                        "snippet": match.group(0),
                        "type": "funding_mention"
                    })
            
            # Extract investor names
            investor_containers = soup.find_all(['ul', 'div'], class_=lambda x: x and ('investor' in x.lower() or 'backer' in x.lower()) if x else False)
            for container in investor_containers:
                items = container.find_all(['li', 'div'])
                for item in items:
                    investor_name = item.get_text().strip()
                    if investor_name and len(investor_name) < 100:
                        investors_data.append({
                            "name": investor_name,
                            "type": "investor"
                        })
        
        except Exception as e:
            logger.debug(f"Investors parsing failed: {e}")
        
        return investors_data
    
    def _parse_press_page(self, html: str) -> List[Dict]:
        """Extract press releases and funding announcements"""
        press_data = []
        try:
            soup = BeautifulSoup(html, 'lxml')
            text = soup.get_text()
            
            # Look for press release titles and dates
            # Common press release patterns
            press_selectors = [
                '.press-release', '.news-item', '.article',
                '[class*="press"]', '[class*="release"]', '[class*="news"]'
            ]
            
            for selector in press_selectors:
                items = soup.select(selector)
                if len(items) > 0:
                    for item in items[:20]:  # Limit to 20
                        press_item = {
                            "title": None,
                            "date": None,
                            "url": None,
                            "type": "press_release"
                        }
                        
                        # Extract title
                        title_tag = item.find(['h2', 'h3', 'h4', 'a'])
                        if title_tag:
                            press_item["title"] = title_tag.get_text().strip()
                            if title_tag.name == 'a':
                                press_item["url"] = urljoin(self.base_url, title_tag.get('href', ''))
                        
                        # Extract date
                        date_tag = item.find(['time', 'span'], class_=lambda x: x and 'date' in str(x).lower() if x else False)
                        if date_tag:
                            press_item["date"] = date_tag.get('datetime') or date_tag.get_text().strip()
                        
                        if press_item["title"]:
                            press_data.append(press_item)
                    
                    if press_data:
                        break
        
        except Exception as e:
            logger.debug(f"Press parsing failed: {e}")
        
        return press_data
    
    def _parse_pricing_page(self, html: str) -> Dict:
        """Extract pricing information (from scraper.py)"""
        pricing_data = {
            "pricing_model": None,
            "tiers": []
        }
        try:
            soup = BeautifulSoup(html, 'lxml')
            text = soup.get_text().lower()
            
            # Detect pricing model
            if 'per seat' in text or 'per user' in text:
                pricing_data["pricing_model"] = "per-seat"
            elif 'usage-based' in text or 'pay as you go' in text:
                pricing_data["pricing_model"] = "usage-based"
            elif 'enterprise' in text and 'contact' in text:
                pricing_data["pricing_model"] = "enterprise"
            
            # Extract tier names
            tier_patterns = ['free', 'starter', 'basic', 'pro', 'professional', 'business', 'enterprise', 'premium', 'plus']
            
            # Look for pricing cards/sections
            pricing_cards = soup.find_all(['div', 'section'], class_=lambda x: x and ('price' in x.lower() or 'tier' in x.lower() or 'plan' in x.lower()) if x else False)
            
            for card in pricing_cards:
                card_text = card.get_text().lower()
                for tier_name in tier_patterns:
                    if tier_name in card_text:
                        # Try to find price
                        price_match = re.search(r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)', card.get_text())
                        price = price_match.group(0) if price_match else None
                        
                        pricing_data["tiers"].append({
                            "name": tier_name.capitalize(),
                            "price": price
                        })
                        break
            
            # If no tiers found, look for tier names in headings
            if not pricing_data["tiers"]:
                headings = soup.find_all(['h2', 'h3', 'h4'])
                for heading in headings:
                    heading_text = heading.get_text().lower()
                    for tier_name in tier_patterns:
                        if tier_name in heading_text:
                            pricing_data["tiers"].append({
                                "name": tier_name.capitalize(),
                                "price": None
                            })
                            break
        
        except Exception as e:
            logger.debug(f"Pricing parsing failed: {e}")
        
        return pricing_data
    
    def _parse_customers_page(self, html: str) -> List[str]:
        """Extract customer/client names (from scraper.py)"""
        customers = []
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # Look for customer logos
            customer_imgs = soup.find_all('img', alt=True)
            for img in customer_imgs:
                alt_text = img.get('alt', '').strip()
                if alt_text and len(alt_text) < 100 and 'logo' not in alt_text.lower():
                    customers.append(alt_text)
            
            # Look for customer lists
            customer_sections = soup.find_all(['ul', 'div'], class_=lambda x: x and ('customer' in x.lower() or 'client' in x.lower()) if x else False)
            for section in customer_sections:
                items = section.find_all(['li', 'div'])
                for item in items:
                    customer_name = item.get_text().strip()
                    if customer_name and len(customer_name) < 100:
                        customers.append(customer_name)
        
        except Exception as e:
            logger.debug(f"Customers parsing failed: {e}")
        
        return list(set(customers))[:50]
    
    def _parse_partners_page(self, html: str) -> List[str]:
        """Extract integration partner names (from scraper.py)"""
        partners = []
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # Look for partner logos with alt text
            partner_imgs = soup.find_all('img', alt=True)
            for img in partner_imgs:
                alt_text = img.get('alt', '').strip()
                if alt_text and len(alt_text) < 100:
                    partners.append(alt_text)
            
            # Look for partner lists
            partner_sections = soup.find_all(['ul', 'div'], class_=lambda x: x and ('partner' in x.lower() or 'integration' in x.lower()) if x else False)
            for section in partner_sections:
                items = section.find_all(['li', 'a'])
                for item in items:
                    partner_name = item.get_text().strip()
                    if partner_name and len(partner_name) < 100:
                        partners.append(partner_name)
        
        except Exception as e:
            logger.debug(f"Partners parsing failed: {e}")
        
        return list(set(partners))[:50]
    
    def save_results(self):
        """Save all extracted data"""
        
        # Merge preloaded jobs and articles
        if self.preloaded_jobs:
            logger.info(f"  📊 Merging {len(self.preloaded_jobs)} preloaded jobs")
        if self.preloaded_articles:
            logger.info(f"  📊 Merging {len(self.preloaded_articles)} preloaded articles")
        
        # Extract entities
        entities = self.extract_entities_from_data()
        
        # Add preloaded jobs and articles
        if self.preloaded_jobs:
            # Deduplicate
            existing_job_titles = {j.get('title', '').lower() for j in entities['jobs']}
            for job in self.preloaded_jobs:
                if job.get('title', '').lower() not in existing_job_titles:
                    entities['jobs'].append(job)
                    existing_job_titles.add(job.get('title', '').lower())
        
        if self.preloaded_articles:
            # Deduplicate
            existing_article_urls = {a.get('url', '') for a in entities['news_articles']}
            for article in self.preloaded_articles:
                if article.get('url', '') not in existing_article_urls:
                    entities['news_articles'].append(article)
                    existing_article_urls.add(article.get('url', ''))
        
        # Helper function to determine standard page type
        def determine_standard_page_type(url: str) -> str:
            """Determine standard 12 page type from URL, checking discovered_pages first"""
            url_lower = url.lower()
            parsed = urlparse(url)
            path_fragment = parsed.path.strip('/')
            
            # FIRST: Check if URL matches any discovered page (most accurate)
            for page_type, discovered_url in self.discovered_pages.items():
                if discovered_url and url_lower == discovered_url.lower():
                    return page_type
            
            # SECOND: Check URL patterns for standard 12 page types (order matters - more specific first)
            if url_lower.rstrip('/') == self.base_url.lower().rstrip('/'):
                return "homepage"
            # Check path fragment first for exact matches
            elif path_fragment in ['company', 'about-us', 'who-we-are', 'our-story']:
                return "about"
            elif path_fragment in ['news', 'articles', 'updates', 'insights']:
                return "blog"
            elif path_fragment in ['open-positions', 'jobs', 'careers']:
                return "careers"
            # Then check URL patterns (more specific patterns first)
            elif '/open-position' in url_lower or '/open-positions' in url_lower:
                return "careers"
            elif '/career' in url_lower or '/job' in url_lower or '/join-us' in url_lower or '/work-with' in url_lower:
                return "careers"
            elif '/about' in url_lower or '/company' in url_lower or '/who-we-are' in url_lower or '/our-story' in url_lower:
                return "about"
            elif '/team' in url_lower or '/leadership' in url_lower or '/people' in url_lower or '/our-team' in url_lower:
                return "team"
            elif '/blog/' in url_lower or '/news/' in url_lower or '/insights/' in url_lower or '/resources/' in url_lower or '/article/' in url_lower:
                # All blog posts should be categorized as "blog"
                return "blog"
            elif '/blog' in url_lower or '/news' in url_lower or '/insights' in url_lower or '/resources' in url_lower or '/articles' in url_lower:
                # Blog index pages or news pages
                return "blog"
            elif '/product' in url_lower or '/products' in url_lower or '/platform' in url_lower or '/solutions' in url_lower or '/features' in url_lower:
                return "product"
            elif '/pricing' in url_lower or '/plans' in url_lower or '/price' in url_lower or '/buy' in url_lower:
                return "pricing"
            elif '/press' in url_lower or '/newsroom' in url_lower or '/media' in url_lower or '/news-and-press' in url_lower:
                return "press"
            elif '/investor' in url_lower or '/funding' in url_lower or '/backed-by' in url_lower or '/backers' in url_lower:
                return "investors"
            elif '/customer' in url_lower or '/client' in url_lower or '/case-stud' in url_lower or '/success-stor' in url_lower or '/testimonial' in url_lower:
                return "customers"
            elif '/partner' in url_lower or '/integration' in url_lower or '/ecosystem' in url_lower or '/partnership' in url_lower:
                return "partners"
            elif '/contact' in url_lower or '/get-in-touch' in url_lower or '/reach-us' in url_lower or '/contact-sales' in url_lower:
                return "contact"
            else:
                # Fallback: use path fragment but limit to 80 chars
                path = path_fragment.replace('/', '_') or f"page_{len(self.pages_data)}"
                return path[:80]
        
        # Save complete page data
        for i, page_data in enumerate(self.pages_data):
            # Determine page type using standard 12 types
            url = page_data["url"]
            page_type = determine_standard_page_type(url)
            
            # Save HTML
            html = page_data.get("raw_html", "")
            if html:
                html_file = self.output_dir / f"{page_type}.html"
                html_file.write_text(html, encoding='utf-8')
            
            # Save clean text
            clean_text = page_data["text_content"]["full_text"]
            if clean_text:
                txt_file = self.output_dir / f"{page_type}_clean.txt"
                txt_file.write_text(clean_text, encoding='utf-8')
            
            # Skip saving error pages (unless they're marked for debugging)
            if page_data.get("error_detected") and not page_data.get("load_failed"):
                # Error was detected but might be recoverable, save with warning
                logger.debug(f"  ⚠️  Saving page with detected error: {page_type}")
            elif page_data.get("load_failed"):
                # Page failed to load properly, skip saving to avoid bad data
                logger.warning(f"  ⚠️  Skipping failed page: {page_type} ({page_data.get('error_detected', 'unknown error')})")
                continue
            
            # Save complete JSON (without raw HTML to save space)
            page_data_copy = page_data.copy()
            page_data_copy.pop("raw_html", None)  # Remove HTML from JSON
            page_file = self.output_dir / f"{page_type}_complete.json"
            page_file.write_text(json.dumps(page_data_copy, indent=2, default=str), encoding='utf-8')
        
        # Save entities
        entities_file = self.output_dir / "extracted_entities.json"
        entities_file.write_text(json.dumps(entities, indent=2, default=str), encoding='utf-8')
        
        # Save jobs separately for easy access
        if entities["jobs"]:
            jobs_file = self.output_dir / "all_jobs.json"
            jobs_file.write_text(json.dumps({
                "total_jobs": len(entities["jobs"]),
                "jobs": entities["jobs"],
                "extraction_timestamp": datetime.now(timezone.utc).isoformat()
            }, indent=2, default=str), encoding='utf-8')
            logger.info(f"  💼 Saved {len(entities['jobs'])} jobs to all_jobs.json")
        
        # Save news articles separately
        if entities["news_articles"]:
            # Ensure categories/tags are flattened (no nested lists)
            cleaned_articles = []
            for article in entities["news_articles"]:
                cleaned_article = article.copy()
                # Flatten categories if it's a list of lists
                if "categories" in cleaned_article:
                    cats = cleaned_article["categories"]
                    if isinstance(cats, list):
                        flattened = []
                        for cat in cats:
                            if isinstance(cat, list):
                                flattened.extend([str(c) for c in cat if c])
                            else:
                                flattened.append(str(cat))
                        cleaned_article["categories"] = flattened
                    else:
                        cleaned_article["categories"] = [str(cats)] if cats else []
                # Flatten tags if it's a list of lists
                if "tags" in cleaned_article:
                    tags = cleaned_article["tags"]
                    if isinstance(tags, list):
                        flattened = []
                        for tag in tags:
                            if isinstance(tag, list):
                                flattened.extend([str(t) for t in tag if t])
                            else:
                                flattened.append(str(tag))
                        cleaned_article["tags"] = flattened
                    else:
                        cleaned_article["tags"] = [str(tags)] if tags else []
                cleaned_articles.append(cleaned_article)
            
            news_file = self.output_dir / "all_news_articles.json"
            news_file.write_text(json.dumps({
                "total_articles": len(cleaned_articles),
                "articles": cleaned_articles,
                "extraction_timestamp": datetime.now(timezone.utc).isoformat()
            }, indent=2, default=str), encoding='utf-8')
            logger.info(f"  📰 Saved {len(cleaned_articles)} news articles to all_news_articles.json")
        
        # Save aggregated data
        aggregated = {
            "company_name": self.company_name,
            "company_id": self.company_id,
            "scrape_timestamp": datetime.now(timezone.utc).isoformat(),
            "scraper_version": SCRAPER_VERSION,
            "base_url": self.base_url,
            "total_pages": len(self.pages_data),
            "all_structured_data": [],
            "all_links": [],
            "all_images": [],
            "all_metadata": [],
            "entities": entities
        }
        
        # Aggregate structured data
        for page_data in self.pages_data:
            aggregated["all_structured_data"].extend(page_data["structured_data"]["json_ld"])
            aggregated["all_links"].extend(page_data["links"])
            aggregated["all_images"].extend(page_data["images"])
            if page_data["metadata"]["title"]:
                aggregated["all_metadata"].append(page_data["metadata"])
        
        # Save aggregated
        aggregated_file = self.output_dir / "complete_extraction.json"
        aggregated_file.write_text(json.dumps(aggregated, indent=2, default=str), encoding='utf-8')
        
        # Build pages array for metadata (required by structured_extraction_v2.py)
        # Exclude failed pages from the pages array
        pages_array = []
        for page_data in self.pages_data:
            # Skip failed pages
            if page_data.get("load_failed"):
                continue
                
            url = page_data["url"]
            
            # Use same page type determination logic as save_results
            # (determine_standard_page_type is defined above in save_results)
            page_type = determine_standard_page_type(url)
            
            # Get crawled_at from page_data timestamp
            crawled_at = page_data.get("timestamp", datetime.now(timezone.utc).isoformat())
            
            # Determine status code based on error detection
            status_code = 200
            if page_data.get("error_detected"):
                if "404" in page_data["error_detected"]:
                    status_code = 404
                elif "500" in page_data["error_detected"]:
                    status_code = 500
                else:
                    status_code = 200  # Client-side errors still return 200 HTTP status
            
            pages_array.append({
                "page_type": page_type,
                "source_url": url,
                "crawled_at": crawled_at,
                "found": True,
                "status_code": status_code
            })
        
        # Also add blog post URLs from news_articles
        for article in entities.get("news_articles", []):
            article_url = article.get("url")
            if article_url and article_url not in [p["source_url"] for p in pages_array]:
                # Determine if it's a blog post
                url_lower = article_url.lower()
                if any(kw in url_lower for kw in ['/blog/', '/news/', '/post/', '/article/']):
                    parsed = urlparse(article_url)
                    path_fragment = parsed.path.strip('/')
                    if path_fragment:
                        page_type = path_fragment.replace('/', '_')[:80]
                    else:
                        page_type = "blog"
                    
                    pages_array.append({
                        "page_type": page_type,
                        "source_url": article_url,
                        "crawled_at": article.get("date_published") or article.get("date_modified") or datetime.now(timezone.utc).isoformat(),
                        "found": True,
                        "status_code": 200
                    })
        
        # Calculate which page types were successfully extracted
        extracted_page_types = set()
        for page_data in self.pages_data:
            page_type = page_data.get("page_type")
            if page_type:
                extracted_page_types.add(page_type)
            else:
                # Infer from URL
                url = page_data.get("url", "")
                url_lower = url.lower()
                if url_lower.rstrip('/') == self.base_url.lower().rstrip('/'):
                    extracted_page_types.add("homepage")
                elif any(kw in url_lower for kw in ['/about', '/company']):
                    extracted_page_types.add("about")
                elif any(kw in url_lower for kw in ['/career', '/job']):
                    extracted_page_types.add("careers")
                elif any(kw in url_lower for kw in ['/blog', '/news']):
                    extracted_page_types.add("blog")
                elif any(kw in url_lower for kw in ['/team', '/leadership']):
                    extracted_page_types.add("team")
                elif any(kw in url_lower for kw in ['/investor', '/funding']):
                    extracted_page_types.add("investors")
                elif any(kw in url_lower for kw in ['/customer', '/client']):
                    extracted_page_types.add("customers")
                elif any(kw in url_lower for kw in ['/press', '/newsroom']):
                    extracted_page_types.add("press")
                elif any(kw in url_lower for kw in ['/pricing', '/plans']):
                    extracted_page_types.add("pricing")
                elif any(kw in url_lower for kw in ['/partner', '/integration']):
                    extracted_page_types.add("partners")
                elif any(kw in url_lower for kw in ['/contact']):
                    extracted_page_types.add("contact")
                elif any(kw in url_lower for kw in ['/product', '/platform']):
                    extracted_page_types.add("product")
        
        # Save metadata
        metadata = {
            "company_name": self.company_name,
            "company_id": self.company_id,
            "scrape_timestamp": datetime.now(timezone.utc).isoformat(),
            "scraper_version": SCRAPER_VERSION,
            "pages_crawled": len(self.pages_data),
            "urls_visited": sorted(list(self.urls_visited)),
            "total_structured_items": len(aggregated["all_structured_data"]),
            "total_links": len(aggregated["all_links"]),
            "total_images": len(aggregated["all_images"]),
            "pages": pages_array,  # CRITICAL: Add pages array for structured_extraction_v2.py
            "page_types_extracted": sorted(list(extracted_page_types)),  # NEW: Track which page types were extracted
            "page_types_discovered": {pt: url for pt, url in self.discovered_pages.items() if url},  # NEW: Track discovered pages
            "entities_summary": {
                "jobs": len(entities["jobs"]),
                "team_members": len(entities["team_members"]),
                "products": len(entities["products"]),
                "customers": len(entities["customers"]),
                "partners": len(entities["partners"]),
                "investors": len(entities["investors"]),
                "news_articles": len(entities["news_articles"])
            }
        }
        
        metadata_file = self.output_dir / "metadata.json"
        metadata_file.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        
        # Dashboard-friendly payload
        dashboard_payload = {
            "company_name": self.company_name,
            "company_id": self.company_id,
            "scraped_at": metadata["scrape_timestamp"],
            "summary": metadata["entities_summary"],
            "jobs": entities["jobs"],
            "news_articles": entities["news_articles"],
            "team_members": entities["team_members"],
            "products": entities["products"],
            "key_pages": list(self.urls_visited),
        }
        dashboard_file = self.output_dir / "dashboard_material.json"
        dashboard_file.write_text(json.dumps(dashboard_payload, indent=2, default=str), encoding='utf-8')
        
        logger.info(f"  💾 Saved {len(self.pages_data)} pages with complete data")
        logger.info(f"  📊 Extracted: {len(entities['jobs'])} jobs, {len(entities['team_members'])} team members, "
                   f"{len(entities['products'])} products, {len(entities['news_articles'])} news articles")
        logger.info(f"  📋 Page types extracted: {len(extracted_page_types)}/12 - {', '.join(sorted(extracted_page_types))}")
        missing_types = [pt for pt in PAGE_PATTERNS.keys() if pt not in extracted_page_types]
        if missing_types:
            logger.warning(f"  ⚠️  Missing page types: {', '.join(missing_types)}")


# ============================================================================
# MAIN
# ============================================================================

async def scrape_company(company: Dict, output_dir: Path, run_folder: str, max_pages: int = 200) -> Dict:
    """Scrape one company comprehensively"""
    crawler = ComprehensiveCrawler(company, output_dir, run_folder, max_pages=max_pages)
    return await crawler.crawl()


def load_companies(seed_file: Path, company_ids: Optional[List[str]] = None) -> List[Dict]:
    """Load companies"""
    with open(seed_file, 'r') as f:
        all_companies = json.load(f)
    
    for company in all_companies:
        domain = urlparse(company["website"]).netloc
        company["company_id"] = domain.replace("www.", "").split(".")[0]
    
    if company_ids:
        all_companies = [c for c in all_companies if c["company_id"] in company_ids]
    
    return all_companies


async def main_async(args):
    """Async main"""
    companies = load_companies(args.seed_file, args.companies)
    logger.info(f"✅ Loaded {len(companies)} companies\n")
    
    results = []
    
    for i, company in enumerate(companies, 1):
        logger.info(f"\n[{i}/{len(companies)}] {company['company_name']}")
        
        try:
            result = await scrape_company(company, args.output_dir, args.run_folder, max_pages=args.max_pages)
            results.append(result)
            logger.info(f"✅ Done: {result.get('pages_crawled', 0)} pages\n")
        except Exception as e:
            logger.error(f"❌ Error: {str(e)[:200]}")
            results.append({"company_name": company['company_name'], "status": "error", "error": str(e)[:200]})
    
    return results


def main():
    """CLI entry"""
    parser = argparse.ArgumentParser(description="Comprehensive Scraper V4.0 - Extracts ALL Data")
    parser.add_argument('--seed-file', type=Path, default=Path(__file__).parent.parent / "data/forbes_ai50_seed.json")
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).parent.parent / "data/raw")
    parser.add_argument('--run-folder', type=str, default='comprehensive_extraction')
    parser.add_argument('--companies', nargs='+', help='Specific company IDs to scrape')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--max-pages', type=int, default=30, help='Maximum pages to crawl per company (default: 30 for speed)')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    import time
    start = time.time()
    results = asyncio.run(main_async(args))
    elapsed = time.time() - start
    
    successful = [r for r in results if r.get('status') == 'success']
    total_pages = sum(r.get('pages_crawled', 0) for r in results)
    
    logger.info("\n" + "=" * 80)
    logger.info("🎉 COMPREHENSIVE SCRAPING COMPLETE")
    logger.info("=" * 80)
    logger.info(f"✅ Companies: {len(successful)}/{len(results)}")
    logger.info(f"📄 Total pages: {total_pages}")
    logger.info(f"⏱️  Time: {elapsed/60:.1f} min")
    logger.info("=" * 80)
    
    # Save summary
    summary = args.output_dir.parent / f"comprehensive_summary.json"
    summary.write_text(json.dumps({
        "date": datetime.now(timezone.utc).isoformat(),
        "version": SCRAPER_VERSION,
        "total_pages": total_pages,
        "results": results
    }, indent=2), encoding='utf-8')
    
    logger.info(f"💾 Summary: {summary}\n")


if __name__ == "__main__":
    main()
