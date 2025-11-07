#!/usr/bin/env python3
"""
Forbes AI50 Deep Web Scraper - Production Script

Extracts comprehensive data from company websites including:
- 12 page types (Homepage, About, Product, Careers, Blog, Team, Investors, Customers, Press, Pricing, Partners, Contact)
- Individual blog posts (up to 20 per company)
- Structured data (HQ, team, investors, pricing, customers, partners)

Features:
- HTTP-first with Playwright fallback
- Smart page discovery
- Content hash computation for change detection
- CLI interface for easy integration with Airflow
"""

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
import trafilatura
from bs4 import BeautifulSoup

# Optional: Playwright support (fallback for JS-heavy sites)
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logging.warning("Playwright not available. Install with: pip install playwright && playwright install")

# Configuration
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
REQUEST_DELAY = 2
REQUEST_TIMEOUT = 10
MAX_RETRIES = 3
PLAYWRIGHT_TIMEOUT = 15000
SCRAPER_VERSION = "3.0-airflow"

# Page patterns - Expanded for comprehensive scraping
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

# Track request times for rate limiting
last_request_time = {}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def compute_content_hash(html: str) -> str:
    """
    Compute SHA256 hash of HTML content for change detection.
    
    Args:
        html: Raw HTML content
        
    Returns:
        Hexadecimal hash string
    """
    return hashlib.sha256(html.encode('utf-8')).hexdigest()


def check_robots_txt(base_url: str) -> bool:
    """Check if scraping is allowed by robots.txt"""
    try:
        parsed = urlparse(base_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(USER_AGENT, base_url)
    except:
        return True  # Assume allowed if can't read


def find_page_url(base_url: str, page_type: str) -> Optional[str]:
    """Find URL for a page type by trying multiple patterns"""
    patterns = PAGE_PATTERNS.get(page_type, [])
    for pattern in patterns:
        url = urljoin(base_url, pattern)
        try:
            response = requests.head(url, timeout=5, headers={"User-Agent": USER_AGENT}, allow_redirects=True)
            if response.status_code == 200:
                return response.url
        except:
            continue
    return None


def extract_clean_text(html: str) -> str:
    """Extract clean text from HTML"""
    try:
        clean_text = trafilatura.extract(html, include_comments=False, include_tables=True)
        if clean_text and len(clean_text) > 100:
            return clean_text
    except:
        pass
    
    try:
        soup = BeautifulSoup(html, 'lxml')
        for element in soup(['script', 'style', 'nav', 'footer', 'header']):
            element.decompose()
        text = soup.get_text(separator='\n', strip=True)
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        return '\n'.join(lines)
    except:
        return ""


def save_page_data(company_dir: Path, page_type: str, html: str, clean_text: str) -> Dict[str, int]:
    """Save raw HTML and clean text"""
    html_path = company_dir / f"{page_type}.html"
    txt_path = company_dir / f"{page_type}_clean.txt"
    
    html_path.write_text(html, encoding='utf-8')
    txt_path.write_text(clean_text, encoding='utf-8')
    
    return {"html_size": len(html), "text_size": len(clean_text)}


# ============================================================================
# PAGE DISCOVERY
# ============================================================================

def discover_links_from_homepage(homepage_html: str, base_url: str) -> Dict[str, str]:
    """Discover page URLs by analyzing homepage links for all page types"""
    discovered = {}
    try:
        soup = BeautifulSoup(homepage_html, 'lxml')
        parsed_base = urlparse(base_url)
        
        # Get all links
        for link in soup.find_all('a', href=True):
            href = link['href'].lower()
            full_url = urljoin(base_url, link['href'])
            
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
        logger.warning(f"Link discovery failed: {str(e)[:50]}")
    
    return discovered


# ============================================================================
# BLOG POST EXTRACTION
# ============================================================================

def extract_blog_post_links(blog_html: str, base_url: str, limit: int = 20) -> List[str]:
    """
    Extract individual blog post URLs from blog index page.
    Returns up to 'limit' most recent posts.
    """
    discovered_posts = []
    seen_urls = set()
    
    try:
        soup = BeautifulSoup(blog_html, 'lxml')
        parsed_base = urlparse(base_url)
        
        # Common blog post selectors
        post_selectors = [
            'article a',
            '.post a',
            '.blog-post a',
            '.entry a',
            '[class*="article"] a',
            '[class*="post"] a',
            'h2 a',
            'h3 a'
        ]
        
        # Try each selector
        for selector in post_selectors:
            links = soup.select(selector)
            for link in links:
                if not link.get('href'):
                    continue
                    
                full_url = urljoin(base_url, link['href'])
                parsed_url = urlparse(full_url)
                
                # Only same domain
                if parsed_url.netloc != parsed_base.netloc:
                    continue
                
                # Skip common non-post pages
                skip_patterns = [
                    '/category/', '/tag/', '/author/', '/page/',
                    '/search', '/archive', '#', 'javascript:',
                    '.pdf', '.jpg', '.png', '.gif'
                ]
                if any(pattern in full_url.lower() for pattern in skip_patterns):
                    continue
                
                # Avoid duplicates
                if full_url in seen_urls:
                    continue
                    
                # Look for date patterns or post IDs in URL
                if any(pattern in full_url for pattern in ['/blog/', '/news/', '/post/', '/article/', '/20']):
                    seen_urls.add(full_url)
                    discovered_posts.append(full_url)
                    
                    if len(discovered_posts) >= limit:
                        break
            
            if len(discovered_posts) >= limit:
                break
        
        # If we didn't find enough, try all links that contain the blog path
        if len(discovered_posts) < 5:
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                full_url = urljoin(base_url, link['href'])
                parsed_url = urlparse(full_url)
                
                if parsed_url.netloc != parsed_base.netloc:
                    continue
                    
                path = parsed_url.path.lower()
                if ('/blog/' in path or '/news/' in path) and full_url not in seen_urls:
                    skip_patterns = ['/category/', '/tag/', '/author/', '/page/', '/search', '/archive']
                    if not any(pattern in path for pattern in skip_patterns):
                        discovered_posts.append(full_url)
                        seen_urls.add(full_url)
                        
                        if len(discovered_posts) >= limit:
                            break
    
    except Exception as e:
        logger.warning(f"Blog post extraction failed: {str(e)[:50]}")
    
    return discovered_posts[:limit]


# ============================================================================
# STRUCTURED PARSERS
# ============================================================================

def parse_footer(html: str) -> Dict:
    """Extract HQ location and founding year from footer/about page"""
    result = {
        "hq_city": None,
        "hq_state": None,
        "hq_country": None,
        "founded_year": None
    }
    
    try:
        soup = BeautifulSoup(html, 'lxml')
        text = soup.get_text().lower()
        
        # Find founding year
        year_patterns = [
            r'©\s*(\d{4})',
            r'copyright\s*(\d{4})',
            r'founded\s+in\s+(\d{4})',
            r'established\s+in\s+(\d{4})',
            r'since\s+(\d{4})'
        ]
        for pattern in year_patterns:
            match = re.search(pattern, text)
            if match:
                year = int(match.group(1))
                if 2000 <= year <= 2025:
                    result["founded_year"] = year
                    break
        
        # Find HQ - common AI hubs
        us_cities = {
            'san francisco': ('San Francisco', 'CA', 'US'),
            'palo alto': ('Palo Alto', 'CA', 'US'),
            'mountain view': ('Mountain View', 'CA', 'US'),
            'new york': ('New York', 'NY', 'US'),
            'seattle': ('Seattle', 'WA', 'US'),
            'boston': ('Boston', 'MA', 'US'),
            'cambridge': ('Cambridge', 'MA', 'US'),
            'austin': ('Austin', 'TX', 'US')
        }
        
        for city_key, (city, state, country) in us_cities.items():
            if city_key in text:
                result["hq_city"] = city
                result["hq_state"] = state
                result["hq_country"] = country
                break
        
        # Try to find address tags
        address_tag = soup.find('address')
        if address_tag:
            address_text = address_tag.get_text()
            for city_key, (city, state, country) in us_cities.items():
                if city_key in address_text.lower():
                    result["hq_city"] = city
                    result["hq_state"] = state
                    result["hq_country"] = country
                    break
        
    except Exception as e:
        logger.debug(f"Footer parsing failed: {e}")
    
    return result


def parse_team_page(html: str) -> List[Dict]:
    """Extract team member information"""
    team_members = []
    
    try:
        soup = BeautifulSoup(html, 'lxml')
        
        # Common team member containers
        member_selectors = [
            '.team-member',
            '.person',
            '.employee',
            '[class*="team"]',
            '[class*="member"]',
            'article'
        ]
        
        for selector in member_selectors:
            members = soup.select(selector)
            if len(members) > 1:  # Found a pattern
                for member in members[:20]:  # Limit to top 20
                    member_data = {
                        "name": None,
                        "role": None,
                        "bio": None,
                        "linkedin": None
                    }
                    
                    # Extract name
                    name_tag = member.find(['h2', 'h3', 'h4', 'strong'])
                    if name_tag:
                        member_data["name"] = name_tag.get_text().strip()
                    
                    # Extract role/title
                    role_classes = ['role', 'title', 'position', 'job-title']
                    for cls in role_classes:
                        role_tag = member.find(class_=lambda x: x and cls in x.lower())
                        if role_tag:
                            member_data["role"] = role_tag.get_text().strip()
                            break
                    
                    # If no role found, try p tags
                    if not member_data["role"]:
                        p_tags = member.find_all('p')
                        if len(p_tags) > 0:
                            first_p = p_tags[0].get_text().strip()
                            if len(first_p) < 100:
                                member_data["role"] = first_p
                    
                    # Extract bio
                    bio_tag = member.find('p', class_=lambda x: x and 'bio' in x.lower() if x else False)
                    if bio_tag:
                        member_data["bio"] = bio_tag.get_text().strip()
                    
                    # Extract LinkedIn
                    linkedin_link = member.find('a', href=lambda x: x and 'linkedin.com' in x if x else False)
                    if linkedin_link:
                        member_data["linkedin"] = linkedin_link['href']
                    
                    if member_data["name"]:
                        team_members.append(member_data)
                
                if team_members:
                    break
    
    except Exception as e:
        logger.debug(f"Team parsing failed: {e}")
    
    return team_members


def parse_investors_page(html: str) -> List[Dict]:
    """Extract investor and funding information"""
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


def parse_customers_page(html: str) -> List[str]:
    """Extract customer/client names"""
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


def parse_pricing_page(html: str) -> Dict:
    """Extract pricing information"""
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


def parse_partners_page(html: str) -> List[str]:
    """Extract integration partner names"""
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


# ============================================================================
# FETCHING FUNCTIONS
# ============================================================================

def fetch_with_requests(url: str) -> Tuple[Optional[str], int, str]:
    """Fetch page with requests library (fast)"""
    domain = urlparse(url).netloc
    
    # Rate limiting
    if domain in last_request_time:
        elapsed = time.time() - last_request_time[domain]
        if elapsed < REQUEST_DELAY:
            time.sleep(REQUEST_DELAY - elapsed)
    
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT}, allow_redirects=True)
            last_request_time[domain] = time.time()
            
            if response.status_code == 200:
                return response.text, 200, "HTTP Success"
            elif response.status_code == 404:
                return None, 404, "Not found"
            elif response.status_code in [403, 429]:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
                continue
            else:
                return None, response.status_code, f"HTTP {response.status_code}"
        except requests.Timeout:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
                return None, 0, "Timeout"
        except Exception as e:
            return None, 0, f"Error: {str(e)[:50]}"
    
    return None, 0, "Max retries"


def fetch_with_playwright(url: str) -> Tuple[Optional[str], int, str]:
    """Fetch page with Playwright (handles JS, blocking)"""
    if not PLAYWRIGHT_AVAILABLE:
        return None, 0, "Playwright not available"
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            page = context.new_page()
            
            try:
                response = page.goto(url, timeout=PLAYWRIGHT_TIMEOUT, wait_until="networkidle")
                page.wait_for_timeout(2000)
                html = page.content()
                status_code = response.status if response else 200
                browser.close()
                
                if status_code == 200:
                    return html, 200, "Playwright Success"
                else:
                    return None, status_code, f"Playwright HTTP {status_code}"
            except PlaywrightTimeout:
                browser.close()
                return None, 0, "Playwright timeout"
            except Exception as e:
                browser.close()
                return None, 0, f"Playwright error: {str(e)[:50]}"
    except Exception as e:
        return None, 0, f"Playwright init failed: {str(e)[:50]}"


def fetch_page_smart(url: str, force_playwright: bool = False) -> Tuple[Optional[str], int, str]:
    """Smart fetch with automatic fallback"""
    if force_playwright:
        return fetch_with_playwright(url)
    
    # Try HTTP first (fast)
    html, status_code, note = fetch_with_requests(url)
    
    # If blocked/failed, try Playwright
    if html is None and status_code in [0, 403, 429] and PLAYWRIGHT_AVAILABLE:
        logger.debug(f"Fallback to Playwright for {url}")
        return fetch_with_playwright(url)
    
    return html, status_code, note


# ============================================================================
# MAIN SCRAPER FUNCTION
# ============================================================================

def scrape_company(
    company: Dict,
    output_dir: Path,
    run_folder: str = "initial_pull",
    force_playwright: bool = False,
    respect_robots: bool = True,
    scrape_blog_posts: bool = True,
    max_blog_posts: int = 20
) -> Dict:
    """
    Deep scrape all pages for a company with smart fallbacks and structured parsing.
    
    Args:
        company: Company dict with name, website, company_id
        output_dir: Base output directory (e.g., data/raw)
        run_folder: Subfolder name (e.g., 'initial_pull' or 'daily_2025-11-04')
        force_playwright: If True, use Playwright for all pages
        respect_robots: If False, bypass robots.txt
        scrape_blog_posts: Whether to extract and scrape individual blog posts
        max_blog_posts: Maximum number of blog posts to scrape
    
    Returns:
        Dict with scraping results and statistics
    """
    company_name = company["company_name"]
    company_id = company["company_id"]
    base_url = company["website"]
    
    logger.info(f"=" * 70)
    logger.info(f"Scraping {company_name} ({company_id})")
    logger.info(f"URL: {base_url}")
    logger.info(f"Mode: {'Playwright' if force_playwright else 'HTTP + Playwright fallback'}")
    logger.info(f"=" * 70)
    
    # Create folders
    company_dir = output_dir / company_id / run_folder
    blog_posts_dir = company_dir / "blog_posts"
    company_dir.mkdir(parents=True, exist_ok=True)
    blog_posts_dir.mkdir(parents=True, exist_ok=True)
    
    # Check robots.txt
    if respect_robots and not force_playwright:
        if not check_robots_txt(base_url):
            logger.warning(f"Blocked by robots.txt: {company_name}")
            return {
                "company_name": company_name,
                "company_id": company_id,
                "status": "blocked_by_robots",
                "pages_scraped": 0,
                "pages_total": 12
            }
    
    # Scrape main pages (12 types)
    page_results = []
    pages_scraped = 0
    homepage_html = None
    discovered_links = {}
    all_page_types = ["homepage", "about", "product", "careers", "blog", "team", "investors", "customers", "press", "pricing", "partners", "contact"]
    
    for page_type in all_page_types:
        logger.info(f"  Scraping {page_type}...")
        
        # Find URL
        if page_type == "homepage":
            page_url = base_url
        else:
            # Try predefined patterns first
            page_url = find_page_url(base_url, page_type)
            
            # If not found and we have homepage HTML, try discovering from links
            if not page_url and homepage_html:
                if not discovered_links:
                    discovered_links = discover_links_from_homepage(homepage_html, base_url)
                page_url = discovered_links.get(page_type)
        
        if not page_url:
            logger.debug(f"  {page_type}: Not found")
            page_results.append({
                "page_type": page_type,
                "source_url": None,
                "crawled_at": datetime.now(timezone.utc).isoformat(),
                "status_code": 0,
                "found": False,
                "note": "URL not found",
                "content_hash": None
            })
            continue
        
        # Fetch page
        html, status_code, note = fetch_page_smart(page_url, force_playwright)
        
        # Save homepage HTML for link discovery
        if page_type == "homepage" and html:
            homepage_html = html
        
        if html:
            # Compute hash for change detection
            content_hash = compute_content_hash(html)
            
            clean_text = extract_clean_text(html)
            sizes = save_page_data(company_dir, page_type, html, clean_text)
            logger.info(f"  {page_type}: Success ({sizes['html_size']:,}B / {sizes['text_size']:,}B) hash={content_hash[:8]}")
            
            # Parse structured data for specific page types
            structured_data = None
            if page_type in ["about", "contact"]:
                structured_data = parse_footer(html)
            elif page_type == "team":
                structured_data = parse_team_page(html)
            elif page_type == "investors":
                structured_data = parse_investors_page(html)
            elif page_type == "customers":
                structured_data = parse_customers_page(html)
            elif page_type == "pricing":
                structured_data = parse_pricing_page(html)
            elif page_type == "partners":
                structured_data = parse_partners_page(html)
            elif page_type == "careers":
                structured_data = {"note": "Job openings can be parsed in future"}
            
            # Save structured data if we extracted any
            if structured_data:
                structured_path = company_dir / f"{page_type}_structured.json"
                structured_path.write_text(json.dumps(structured_data, indent=2), encoding='utf-8')
            
            page_results.append({
                "page_type": page_type,
                "source_url": page_url,
                "crawled_at": datetime.now(timezone.utc).isoformat(),
                "status_code": status_code,
                "content_length": sizes['html_size'],
                "content_hash": content_hash,
                "found": True,
                "note": note,
                "method": "playwright" if "Playwright" in note else "http",
                "has_structured_data": structured_data is not None
            })
            pages_scraped += 1
            
            # Extract and scrape blog posts if this is the blog page
            if page_type == "blog" and html and scrape_blog_posts:
                logger.info(f"  Extracting blog posts...")
                blog_post_urls = extract_blog_post_links(html, base_url, limit=max_blog_posts)
                logger.info(f"  Found {len(blog_post_urls)} blog posts")
                
                for i, post_url in enumerate(blog_post_urls):
                    # Create short hash for filename
                    url_hash = hashlib.md5(post_url.encode()).hexdigest()[:8]
                    post_filename = f"post_{url_hash}"
                    
                    # Fetch blog post
                    post_html, post_status, post_note = fetch_page_smart(post_url, force_playwright)
                    
                    if post_html:
                        post_clean_text = extract_clean_text(post_html)
                        
                        # Save to blog_posts subfolder
                        (blog_posts_dir / f"{post_filename}.html").write_text(post_html, encoding='utf-8')
                        (blog_posts_dir / f"{post_filename}_clean.txt").write_text(post_clean_text, encoding='utf-8')
                        
                        pages_scraped += 1
                        
                        if (i + 1) % 5 == 0:
                            logger.info(f"  ... {i+1}/{len(blog_post_urls)} blog posts scraped")
                
                if len(blog_post_urls) > 0:
                    logger.info(f"  {len(blog_post_urls)} blog posts saved to blog_posts/")
        else:
            logger.warning(f"  {page_type}: Failed - {note}")
            page_results.append({
                "page_type": page_type,
                "source_url": page_url,
                "crawled_at": datetime.now(timezone.utc).isoformat(),
                "status_code": status_code,
                "found": False,
                "note": note,
                "content_hash": None
            })
    
    # Save metadata
    metadata = {
        "company_name": company_name,
        "company_id": company_id,
        "scrape_timestamp": datetime.now(timezone.utc).isoformat(),
        "scraper_version": SCRAPER_VERSION,
        "run_folder": run_folder,
        "force_playwright": force_playwright,
        "respect_robots": respect_robots,
        "pages": page_results
    }
    
    metadata_path = company_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    
    logger.info(f"  Total: {pages_scraped} pages/posts scraped")
    
    return {
        "company_name": company_name,
        "company_id": company_id,
        "status": "success" if pages_scraped > 0 else "failed",
        "pages_scraped": pages_scraped,
        "pages_total": 12,
        "blog_posts_found": len([p for p in page_results if p.get("page_type") == "blog" and p.get("found")])
    }


# ============================================================================
# UTILITY FUNCTIONS FOR AIRFLOW
# ============================================================================

def load_companies(seed_file: Path, company_ids: Optional[List[str]] = None) -> List[Dict]:
    """
    Load companies from seed file.
    
    Args:
        seed_file: Path to forbes_ai50_seed.json
        company_ids: Optional list of company IDs to filter
        
    Returns:
        List of company dicts with company_id added
    """
    with open(seed_file, 'r') as f:
        all_companies = json.load(f)
    
    # Add company_id to all
    for company in all_companies:
        domain = urlparse(company["website"]).netloc
        company["company_id"] = domain.replace("www.", "").split(".")[0]
    
    # Filter if requested
    if company_ids:
        all_companies = [c for c in all_companies if c["company_id"] in company_ids]
    
    return all_companies


# ============================================================================
# CLI INTERFACE
# ============================================================================

def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Forbes AI50 Deep Web Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape all companies
  python src/scraper.py
  
  # Scrape specific companies
  python src/scraper.py --companies abridge anthropic
  
  # Use Playwright for all requests
  python src/scraper.py --force-playwright
  
  # Custom output directory
  python src/scraper.py --output-dir /path/to/output
        """
    )
    
    parser.add_argument(
        '--seed-file',
        type=Path,
        default=Path(__file__).parent.parent / "data/forbes_ai50_seed.json",
        help='Path to company seed file (default: data/forbes_ai50_seed.json)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path(__file__).parent.parent / "data/raw",
        help='Output directory for scraped data (default: data/raw)'
    )
    
    parser.add_argument(
        '--run-folder',
        type=str,
        default='initial_pull',
        help='Subfolder name for this run (default: initial_pull)'
    )
    
    parser.add_argument(
        '--companies',
        nargs='+',
        help='Specific company IDs to scrape (space-separated). If not provided, scrapes all.'
    )
    
    parser.add_argument(
        '--force-playwright',
        action='store_true',
        help='Use Playwright for all requests (slower but handles JS)'
    )
    
    parser.add_argument(
        '--respect-robots',
        action='store_true',
        help='Respect robots.txt (default: bypass for academic use)'
    )
    
    parser.add_argument(
        '--no-blog-posts',
        action='store_true',
        help='Skip scraping individual blog posts'
    )
    
    parser.add_argument(
        '--max-blog-posts',
        type=int,
        default=20,
        help='Maximum blog posts to scrape per company (default: 20)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Load companies
    logger.info(f"Loading companies from {args.seed_file}")
    companies = load_companies(args.seed_file, args.companies)
    logger.info(f"Loaded {len(companies)} companies")
    
    if not companies:
        logger.error("No companies to scrape")
        sys.exit(1)
    
    # Scrape companies
    results = []
    start_time = time.time()
    
    for i, company in enumerate(companies, 1):
        logger.info(f"\n[{i}/{len(companies)}] {company['company_name']}...")
        
        try:
            result = scrape_company(
                company=company,
                output_dir=args.output_dir,
                run_folder=args.run_folder,
                force_playwright=args.force_playwright,
                respect_robots=args.respect_robots,
                scrape_blog_posts=not args.no_blog_posts,
                max_blog_posts=args.max_blog_posts
            )
            results.append(result)
        except Exception as e:
            logger.error(f"Error scraping {company['company_name']}: {e}", exc_info=True)
            results.append({
                "company_name": company['company_name'],
                "company_id": company['company_id'],
                "status": "error",
                "error": str(e),
                "pages_scraped": 0,
                "pages_total": 12
            })
    
    # Summary
    elapsed = time.time() - start_time
    successful = [r for r in results if r.get('status') == 'success']
    failed = [r for r in results if r.get('status') != 'success']
    total_pages = sum(r.get('pages_scraped', 0) for r in results)
    
    logger.info("\n" + "=" * 70)
    logger.info("SCRAPING COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Successful: {len(successful)}/{len(companies)} companies")
    logger.info(f"Failed: {len(failed)} companies")
    logger.info(f"Total pages/posts: {total_pages:,}")
    logger.info(f"Average per company: {total_pages/len(companies):.1f}")
    logger.info(f"Total time: {elapsed/60:.1f} minutes")
    logger.info("=" * 70)
    
    if failed:
        logger.warning("\nFailed companies:")
        for r in failed:
            logger.warning(f"  - {r['company_name']}: {r.get('error', r.get('status', 'unknown'))}")
    
    # Export results
    results_file = args.output_dir.parent / f"scraping_results_{args.run_folder}.json"
    results_file.write_text(json.dumps({
        "scrape_date": datetime.now(timezone.utc).isoformat(),
        "scraper_version": SCRAPER_VERSION,
        "run_folder": args.run_folder,
        "total_companies": len(companies),
        "successful": len(successful),
        "failed": len(failed),
        "total_pages_posts": total_pages,
        "average_per_company": round(total_pages / len(companies), 1) if companies else 0,
        "elapsed_seconds": round(elapsed, 1),
        "companies": results
    }, indent=2), encoding='utf-8')
    
    logger.info(f"\nResults exported to: {results_file}")
    
    # Exit code
    sys.exit(0 if len(successful) == len(companies) else 1)


if __name__ == "__main__":
    main()

