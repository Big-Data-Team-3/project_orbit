"""
ATS (Applicant Tracking System) Detection and Extraction Module

Detects and extracts jobs from:
- Greenhouse
- Lever
- Workable
- Ashby
- BambooHR
- Custom/Generic job boards

Uses API endpoints when available for fast, complete extraction.
"""

import json
import re
import logging
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class ATSExtractor:
    """Detects and extracts jobs from various ATS systems"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.parsed_base = urlparse(base_url)
        self.company_slug = self._extract_company_slug()
        
    def _extract_company_slug(self) -> Optional[str]:
        """Extract company slug from domain"""
        domain = self.parsed_base.netloc.replace('www.', '')
        # Try common patterns
        parts = domain.split('.')
        if len(parts) >= 2:
            return parts[0]
        return None
    
    def detect_ats(self, html: str, careers_url: str) -> Optional[str]:
        """Detect which ATS system is being used"""
        html_lower = html.lower()
        url_lower = careers_url.lower()
        
        # Greenhouse
        if 'greenhouse' in html_lower or 'boards.greenhouse.io' in html_lower or 'greenhouse.io' in url_lower:
            return 'greenhouse'
        
        # Lever
        if 'lever.co' in html_lower or 'lever.co/v0/postings' in html_lower or 'lever.co' in url_lower:
            return 'lever'
        
        # Workable
        if 'workable.com' in html_lower or 'workable' in html_lower or 'workable.com' in url_lower:
            return 'workable'
        
        # Ashby
        if 'ashbyhq.com' in html_lower or 'ashby' in html_lower or 'ashbyhq.com' in url_lower:
            return 'ashby'
        
        # BambooHR
        if 'bamboohr.com' in html_lower or 'bamboohr' in html_lower or 'bamboohr.com' in url_lower:
            return 'bamboohr'
        
        # iCIMS
        if 'icims.com' in html_lower or 'icims' in html_lower or 'icims.com' in url_lower:
            return 'icims'
        
        # Workday
        if 'workday.com' in html_lower or 'myworkdayjobs.com' in html_lower or 'workday.com' in url_lower or 'myworkdayjobs.com' in url_lower:
            return 'workday'
        
        # Oracle Taleo
        if 'taleo.net' in html_lower or 'taleo' in html_lower or 'taleo.net' in url_lower or 'oraclecloud.com' in url_lower:
            return 'oracle'
        
        # SmartRecruiters
        if 'smartrecruiters.com' in html_lower or 'smartrecruiters' in html_lower or 'smartrecruiters.com' in url_lower:
            return 'smartrecruiters'
        
        # Jobvite
        if 'jobvite.com' in html_lower or 'jobvite' in html_lower or 'jobvite.com' in url_lower:
            return 'jobvite'
        
        # Check for embedded iframes
        soup = BeautifulSoup(html, 'lxml')
        iframes = soup.find_all('iframe', src=True)
        for iframe in iframes:
            src = iframe.get('src', '').lower()
            if 'greenhouse.io' in src:
                return 'greenhouse'
            elif 'lever.co' in src:
                return 'lever'
            elif 'workable.com' in src:
                return 'workable'
            elif 'ashbyhq.com' in src:
                return 'ashby'
            elif 'icims.com' in src:
                return 'icims'
            elif 'workday.com' in src or 'myworkdayjobs.com' in src:
                return 'workday'
            elif 'taleo.net' in src or 'oraclecloud.com' in src:
                return 'oracle'
            elif 'smartrecruiters.com' in src:
                return 'smartrecruiters'
            elif 'jobvite.com' in src:
                return 'jobvite'
        
        return None
    
    def extract_greenhouse_jobs(self, html: str, careers_url: str) -> List[Dict[str, Any]]:
        """Extract jobs from Greenhouse"""
        jobs = []
        
        try:
            # Method 1: Try Greenhouse API endpoint
            # Extract board token from HTML or URL
            soup = BeautifulSoup(html, 'lxml')
            
            # Look for board token in script tags
            board_token = None
            for script in soup.find_all('script'):
                if script.string and 'boardToken' in script.string:
                    match = re.search(r'boardToken["\']?\s*[:=]\s*["\']([^"\']+)["\']', script.string)
                    if match:
                        board_token = match.group(1)
                        break
            
            # Also check iframe src
            if not board_token:
                for iframe in soup.find_all('iframe', src=True):
                    src = iframe.get('src', '')
                    if 'greenhouse.io' in src:
                        match = re.search(r'for=([^&]+)', src)
                        if match:
                            board_token = match.group(1)
                            break
            
            # Try API endpoint
            if board_token:
                api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
                try:
                    response = requests.get(api_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        for job in data.get('jobs', []):
                            jobs.append({
                                'title': job.get('title'),
                                'location': job.get('location', {}).get('name') if isinstance(job.get('location'), dict) else job.get('location'),
                                'department': job.get('departments', [{}])[0].get('name') if job.get('departments') else None,
                                'url': job.get('absolute_url'),
                                'id': job.get('id'),
                                'date_posted': job.get('updated_at'),
                                'description': job.get('content'),
                                'source': 'greenhouse_api'
                            })
                        logger.info(f"  ✅ Greenhouse API: {len(jobs)} jobs")
                        return jobs
                except Exception as e:
                    logger.debug(f"Greenhouse API failed: {e}")
            
            # Method 2: Extract from embedded JSON
            for script in soup.find_all('script'):
                if not script.string:
                    continue
                script_text = script.string
                
                # Look for job data in script
                if 'jobs' in script_text.lower() or 'positions' in script_text.lower():
                    # Try to find JSON
                    json_matches = re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', script_text, re.DOTALL)
                    for match in json_matches:
                        try:
                            data = json.loads(match.group(0))
                            if isinstance(data, dict) and 'jobs' in data:
                                for job in data['jobs']:
                                    if isinstance(job, dict) and job.get('title'):
                                        jobs.append({
                                            'title': job.get('title'),
                                            'location': job.get('location', {}).get('name') if isinstance(job.get('location'), dict) else job.get('location'),
                                            'department': job.get('departments', [{}])[0].get('name') if job.get('departments') else None,
                                            'url': job.get('absolute_url') or job.get('url'),
                                            'id': job.get('id'),
                                            'source': 'greenhouse_embedded'
                                        })
                        except:
                            pass
            
            # Method 3: Extract from HTML structure
            job_elements = soup.find_all(['div', 'li', 'article'], class_=re.compile(r'job|position|opening|role', re.I))
            for elem in job_elements:
                title_elem = elem.find(['h2', 'h3', 'h4', 'a'], class_=re.compile(r'title|name', re.I))
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if title and 5 < len(title) < 200:
                        job = {
                            'title': title,
                            'source': 'greenhouse_html'
                        }
                        
                        # Location
                        loc_elem = elem.find(class_=re.compile(r'location', re.I))
                        if loc_elem:
                            job['location'] = loc_elem.get_text(strip=True)
                        
                        # URL
                        link = elem.find('a', href=True)
                        if link:
                            job['url'] = urljoin(careers_url, link['href'])
                        
                        jobs.append(job)
            
        except Exception as e:
            logger.error(f"Greenhouse extraction error: {e}")
        
        return jobs
    
    def extract_lever_jobs(self, html: str, careers_url: str) -> List[Dict[str, Any]]:
        """Extract jobs from Lever"""
        jobs = []
        
        try:
            # Method 1: Try Lever API
            # Extract company name from URL or HTML
            company_name = None
            parsed = urlparse(careers_url)
            if 'lever.co' in parsed.netloc:
                # Extract from subdomain or path
                parts = parsed.netloc.split('.')
                if len(parts) >= 3:
                    company_name = parts[0]
            
            if company_name:
                api_url = f"https://api.lever.co/v0/postings/{company_name}?mode=json"
                try:
                    response = requests.get(api_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        for job in data:
                            jobs.append({
                                'title': job.get('text'),
                                'location': job.get('categories', {}).get('location') if isinstance(job.get('categories'), dict) else None,
                                'department': job.get('categories', {}).get('team') if isinstance(job.get('categories'), dict) else None,
                                'url': job.get('hostedUrl') or job.get('applyUrl'),
                                'id': job.get('id'),
                                'date_posted': job.get('createdAt'),
                                'description': job.get('descriptionPlain'),
                                'source': 'lever_api'
                            })
                        logger.info(f"  ✅ Lever API: {len(jobs)} jobs")
                        return jobs
                except Exception as e:
                    logger.debug(f"Lever API failed: {e}")
            
            # Method 2: Extract from HTML/JSON
            soup = BeautifulSoup(html, 'lxml')
            for script in soup.find_all('script'):
                if not script.string:
                    continue
                script_text = script.string
                
                # Look for Lever data
                if 'lever' in script_text.lower() or 'postings' in script_text.lower():
                    # Try to extract JSON
                    json_matches = re.finditer(r'\[[^\]]*\{[^\}]*"text"[^\}]*\}[^\]]*\]', script_text, re.DOTALL)
                    for match in json_matches:
                        try:
                            data = json.loads(match.group(0))
                            if isinstance(data, list):
                                for job in data:
                                    if isinstance(job, dict) and job.get('text'):
                                        jobs.append({
                                            'title': job.get('text'),
                                            'location': job.get('categories', {}).get('location') if isinstance(job.get('categories'), dict) else None,
                                            'url': job.get('hostedUrl'),
                                            'source': 'lever_embedded'
                                        })
                        except:
                            pass
            
        except Exception as e:
            logger.error(f"Lever extraction error: {e}")
        
        return jobs
    
    def extract_workable_jobs(self, html: str, careers_url: str) -> List[Dict[str, Any]]:
        """Extract jobs from Workable"""
        jobs = []
        
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # Method 1: Extract company slug from embedded Workable content (iframes, scripts, links)
            company_slug = None
            parsed = urlparse(careers_url)
            
            # Try to get slug from URL if it's a Workable domain
            if 'workable.com' in parsed.netloc:
                path_parts = [p for p in parsed.path.strip('/').split('/') if p]
                if path_parts:
                    company_slug = path_parts[0]
            
            # If not found, try to extract from embedded content
            if not company_slug:
                # Check iframes
                for iframe in soup.find_all('iframe', src=True):
                    src = iframe.get('src', '')
                    if 'workable.com' in src.lower():
                        # Extract from iframe src (e.g., https://apply.workable.com/company-name/)
                        iframe_parsed = urlparse(src)
                        iframe_parts = [p for p in iframe_parsed.path.strip('/').split('/') if p]
                        if iframe_parts:
                            company_slug = iframe_parts[0]
                            break
                
                # Check scripts for Workable configuration
                if not company_slug:
                    for script in soup.find_all('script'):
                        if not script.string:
                            continue
                        script_text = script.string
                        # Look for Workable company slug patterns
                        patterns = [
                            r'workable\.com/([a-zA-Z0-9-]+)',
                            r'apply\.workable\.com/([a-zA-Z0-9-]+)',
                            r'company["\']?\s*[:=]\s*["\']([a-zA-Z0-9-]+)["\']',
                            r'account["\']?\s*[:=]\s*["\']([a-zA-Z0-9-]+)["\']',
                        ]
                        for pattern in patterns:
                            match = re.search(pattern, script_text, re.I)
                            if match:
                                potential_slug = match.group(1)
                                # Filter out common false positives
                                if potential_slug not in ['api', 'www', 'apply', 'jobs', 'job']:
                                    company_slug = potential_slug
                                    break
                        if company_slug:
                            break
                
                # Check links for Workable URLs
                if not company_slug:
                    for link in soup.find_all('a', href=True):
                        href = link.get('href', '')
                        if 'workable.com' in href.lower():
                            link_parsed = urlparse(href)
                            link_parts = [p for p in link_parsed.path.strip('/').split('/') if p]
                            if link_parts:
                                potential_slug = link_parts[0]
                                if potential_slug not in ['api', 'www', 'apply', 'jobs', 'job']:
                                    company_slug = potential_slug
                                    break
            
            # Try Workable API with extracted slug
            if company_slug:
                # Try multiple API endpoint formats
                api_endpoints = [
                    f"https://apply.workable.com/api/v3/accounts/{company_slug}/jobs",
                    f"https://www.workable.com/api/v3/accounts/{company_slug}/jobs",
                    f"https://apply.workable.com/api/v2/accounts/{company_slug}/jobs",
                ]
                
                for api_url in api_endpoints:
                    try:
                        response = requests.get(api_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                        if response.status_code == 200:
                            data = response.json()
                            if isinstance(data, dict) and 'results' in data:
                                for job in data.get('results', []):
                                    jobs.append({
                                        'title': job.get('title'),
                                        'location': ', '.join(job.get('location', {}).get('city', [])) if isinstance(job.get('location'), dict) else job.get('location'),
                                        'department': job.get('department'),
                                        'url': job.get('url') or job.get('shortlink'),
                                        'id': job.get('id'),
                                        'date_posted': job.get('published_on'),
                                        'description': job.get('description'),
                                        'source': 'workable_api'
                                    })
                                if jobs:
                                    logger.info(f"  ✅ Workable API ({company_slug}): {len(jobs)} jobs")
                                    return jobs
                    except Exception as e:
                        logger.debug(f"Workable API endpoint {api_url} failed: {e}")
                        continue
            
            # Method 2: Extract from window.__INITIAL_STATE__ or other state objects
            for script in soup.find_all('script'):
                if not script.string:
                    continue
                script_text = script.string
                
                # Try multiple patterns for Workable state
                patterns = [
                    r'__INITIAL_STATE__\s*=\s*(\{.*?\})',
                    r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})',
                    r'__NEXT_DATA__\s*=\s*(\{.*?\})',
                    r'jobs["\']?\s*[:=]\s*(\[[^\]]+\])',
                    r'postings["\']?\s*[:=]\s*(\[[^\]]+\])',
                ]
                
                for pattern in patterns:
                    matches = re.finditer(pattern, script_text, re.DOTALL)
                    for match in matches:
                        try:
                            data = json.loads(match.group(1))
                            # Navigate to jobs in state (handle nested structures)
                            if isinstance(data, dict):
                                # Try various paths to jobs
                                jobs_data = (data.get('jobs') or data.get('postings') or 
                                           data.get('props', {}).get('jobs') or 
                                           data.get('props', {}).get('pageProps', {}).get('jobs') or
                                           data.get('initialState', {}).get('jobs') or [])
                                if isinstance(jobs_data, list):
                                    for job in jobs_data:
                                        if isinstance(job, dict) and job.get('title'):
                                            jobs.append({
                                                'title': job.get('title'),
                                                'location': job.get('location') or (job.get('locations', [{}])[0].get('name') if job.get('locations') else None),
                                                'department': job.get('department'),
                                                'url': job.get('url') or job.get('slug') or job.get('shortlink'),
                                                'source': 'workable_embedded'
                                            })
                                    if jobs:
                                        logger.info(f"  ✅ Workable embedded JSON: {len(jobs)} jobs")
                                        return jobs
                        except:
                            pass
            
            # Method 3: Extract from HTML - MORE AGGRESSIVE
            # Workable uses various class patterns
            job_elements = soup.find_all(['div', 'li', 'article'], class_=re.compile(r'job|position|opening|posting|vacancy', re.I))
            job_elements.extend(soup.find_all(['div', 'li'], attrs={'data-job-id': True}))
            job_elements.extend(soup.find_all(['div', 'li'], attrs={'data-position-id': True}))
            job_elements.extend(soup.find_all(['div', 'li'], attrs={'data-workable-id': True}))
            
            # Also try finding all links that look like job links (including Workable external links)
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                href = link.get('href', '').lower()
                text = link.get_text(strip=True)
                full_url = urljoin(careers_url, link.get('href', ''))
                
                # Check if it's a Workable job link
                is_workable_link = 'workable.com' in href or 'apply.workable.com' in href
                # Check if it looks like a job link (internal or external Workable)
                is_job_link = any(kw in href for kw in ['/jobs/', '/job/', '/position/', '/opening/', '/careers/', '/j/'])
                
                if (is_workable_link or is_job_link) and text and 5 < len(text) < 200:
                    # Check if we already have this job
                    if not any(j.get('url', '').lower() == full_url.lower() for j in jobs):
                        jobs.append({
                            'title': text.strip(),
                            'url': full_url,
                            'source': 'workable_link' if is_workable_link else 'workable_html_link'
                        })
            
            for elem in job_elements:
                title_elem = elem.find(['h2', 'h3', 'h4', 'a', 'span'], class_=re.compile(r'title|job-title|position-title', re.I))
                if not title_elem:
                    title_elem = elem.find(['h2', 'h3', 'h4', 'a'])
                
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if title and 5 < len(title) < 200:
                        job = {
                            'title': title,
                            'source': 'workable_html'
                        }
                        
                        link = elem.find('a', href=True)
                        if link:
                            job['url'] = urljoin(careers_url, link['href'])
                        elif title_elem.name == 'a' and title_elem.get('href'):
                            job['url'] = urljoin(careers_url, title_elem['href'])
                        
                        # Location
                        loc_elem = elem.find(class_=re.compile(r'location|city|place', re.I))
                        if loc_elem:
                            job['location'] = loc_elem.get_text(strip=True)
                        
                        jobs.append(job)
            
        except Exception as e:
            logger.error(f"Workable extraction error: {e}")
        
        return jobs
    
    def extract_ashby_jobs(self, html: str, careers_url: str) -> List[Dict[str, Any]]:
        """Extract jobs from Ashby"""
        jobs = []
        
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # Method 1: Try Ashby API - Extract organization slug from HTML/scripts
            org_slug = None
            
            # Check iframe src
            for iframe in soup.find_all('iframe', src=True):
                src = iframe.get('src', '')
                if 'ashbyhq.com' in src:
                    # Extract from URL like https://jobs.ashbyhq.com/cohere
                    match = re.search(r'ashbyhq\.com/([^/?]+)', src)
                    if match:
                        org_slug = match.group(1)
                        break
            
            # Check script tags for Ashby config
            if not org_slug:
                for script in soup.find_all('script'):
                    if not script.string:
                        continue
                    script_text = script.string
                    # Look for organization slug in various patterns
                    patterns = [
                        r'organization["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                        r'org["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                        r'ashbyhq\.com/([^/"?]+)',
                        r'organizationSlug["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                    ]
                    for pattern in patterns:
                        match = re.search(pattern, script_text, re.IGNORECASE)
                        if match:
                            org_slug = match.group(1)
                            break
                    if org_slug:
                        break
            
            # Also try extracting from URL path (for direct Ashby URLs)
            if not org_slug:
                parsed = urlparse(careers_url)
                if 'ashbyhq.com' in parsed.netloc:
                    parts = parsed.path.strip('/').split('/')
                    if parts and parts[0]:
                        org_slug = parts[0]
            
            # Try API if we found org slug
            if org_slug:
                api_url = f"https://api.ashbyhq.com/public/job_postings?organization_slug={org_slug}"
                try:
                    response = requests.get(api_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        if isinstance(data, dict) and 'jobPostings' in data:
                            for job in data.get('jobPostings', []):
                                jobs.append({
                                    'title': job.get('title'),
                                    'location': job.get('locationName'),
                                    'department': job.get('team', {}).get('name') if isinstance(job.get('team'), dict) else None,
                                    'url': job.get('publishedJobUrl'),
                                    'id': job.get('id'),
                                    'date_posted': job.get('publishedAt'),
                                    'description': job.get('descriptionPlain'),
                                    'source': 'ashby_api'
                                })
                            logger.info(f"  ✅ Ashby API ({org_slug}): {len(jobs)} jobs")
                            return jobs
                except Exception as e:
                    logger.debug(f"Ashby API failed for {org_slug}: {e}")
            
            # Method 2: Extract from embedded JSON in scripts
            for script in soup.find_all('script'):
                if not script.string:
                    continue
                script_text = script.string
                
                # Look for job data in various formats
                if 'ashby' in script_text.lower() or 'job' in script_text.lower():
                    # Try to find JSON arrays/objects with job data
                    json_patterns = [
                        r'jobPostings["\']?\s*[:=]\s*(\[[^\]]+\])',
                        r'jobs["\']?\s*[:=]\s*(\[[^\]]+\])',
                        r'positions["\']?\s*[:=]\s*(\[[^\]]+\])',
                    ]
                    for pattern in json_patterns:
                        matches = re.finditer(pattern, script_text, re.DOTALL | re.IGNORECASE)
                        for match in matches:
                            try:
                                data = json.loads(match.group(1))
                                if isinstance(data, list):
                                    for job in data:
                                        if isinstance(job, dict) and job.get('title'):
                                            jobs.append({
                                                'title': job.get('title'),
                                                'location': job.get('locationName') or job.get('location'),
                                                'department': job.get('team', {}).get('name') if isinstance(job.get('team'), dict) else job.get('department'),
                                                'url': job.get('publishedJobUrl') or job.get('url'),
                                                'id': job.get('id'),
                                                'source': 'ashby_embedded'
                                            })
                                    if jobs:
                                        logger.info(f"  ✅ Ashby embedded JSON: {len(jobs)} jobs")
                                        return jobs
                            except:
                                pass
            
            # Method 3: Extract from HTML structure (Ashby-specific selectors) - MORE AGGRESSIVE
            # Ashby uses specific data attributes
            job_elements = soup.find_all(['div', 'li', 'article'], 
                                        attrs={'data-qa': re.compile(r'job|posting', re.I)})
            job_elements.extend(soup.find_all(['div', 'li', 'article'], class_=re.compile(r'ashby|job|position|opening', re.I)))
            job_elements.extend(soup.find_all(['div', 'li'], attrs={'data-job-id': True}))
            
            # Also try finding all links that might be job links
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                href = link.get('href', '').lower()
                text = link.get_text(strip=True)
                # Check if it looks like a job link (Ashby often uses /jobs/ or /job/ paths)
                if (any(kw in href for kw in ['/jobs/', '/job/', '/position/', '/opening/']) or 
                    'ashbyhq.com' in href) and text and 10 < len(text) < 150:
                    # Check if we already have this job
                    full_url = urljoin(careers_url, link['href'])
                    if not any(j.get('url', '').lower() == full_url.lower() for j in jobs):
                        jobs.append({
                            'title': text,
                            'url': full_url,
                            'source': 'ashby_link'
                        })
            
            for elem in job_elements:
                title_elem = elem.find(['h2', 'h3', 'h4', 'a', 'span'], 
                                      class_=re.compile(r'title|name|heading|job-title', re.I))
                if not title_elem:
                    title_elem = elem.find(['h2', 'h3', 'h4', 'a'])
                
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if title and 5 < len(title) < 200:
                        job = {
                            'title': title,
                            'source': 'ashby_html'
                        }
                        
                        # Location
                        loc_elem = elem.find(class_=re.compile(r'location|city|place', re.I))
                        if loc_elem:
                            job['location'] = loc_elem.get_text(strip=True)
                        
                        # URL
                        link = elem.find('a', href=True)
                        if link:
                            job['url'] = urljoin(careers_url, link['href'])
                        elif title_elem.name == 'a' and title_elem.get('href'):
                            job['url'] = urljoin(careers_url, title_elem['href'])
                        
                        jobs.append(job)
            
        except Exception as e:
            logger.error(f"Ashby extraction error: {e}")
        
        return jobs
    
    def extract_bamboohr_jobs(self, html: str, careers_url: str) -> List[Dict[str, Any]]:
        """Extract jobs from BambooHR"""
        jobs = []
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # BambooHR uses specific class patterns
            job_elements = soup.find_all(['div', 'li', 'tr'], class_=re.compile(r'job|position|opening|listing', re.I))
            job_elements.extend(soup.find_all(['div', 'li'], attrs={'data-job-id': True}))
            
            # Also try finding job links
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                href = link.get('href', '').lower()
                text = link.get_text(strip=True)
                # Check if it looks like a job link
                if (any(kw in href for kw in ['/jobs/', '/job/', '/position/', '/opening/']) or 
                    'bamboohr.com' in href) and text and 10 < len(text) < 150:
                    full_url = urljoin(careers_url, link['href'])
                    if not any(j.get('url', '').lower() == full_url.lower() for j in jobs):
                        jobs.append({
                            'title': text,
                            'url': full_url,
                            'source': 'bamboohr_link'
                        })
            
            for elem in job_elements:
                title_elem = elem.find(['h2', 'h3', 'h4', 'a'], class_=re.compile(r'title|name|heading|job-title', re.I))
                if not title_elem:
                    title_elem = elem.find(['h2', 'h3', 'h4', 'a'])
                
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if title and 5 < len(title) < 200:
                        job = {
                            'title': title,
                            'source': 'bamboohr_html'
                        }
                        
                        # Location
                        loc_elem = elem.find(class_=re.compile(r'location|city|place', re.I))
                        if loc_elem:
                            job['location'] = loc_elem.get_text(strip=True)
                        
                        # Department
                        dept_elem = elem.find(class_=re.compile(r'department|team|division', re.I))
                        if dept_elem:
                            job['department'] = dept_elem.get_text(strip=True)
                        
                        # URL
                        link = elem.find('a', href=True)
                        if link:
                            job['url'] = urljoin(careers_url, link['href'])
                        elif title_elem.name == 'a' and title_elem.get('href'):
                            job['url'] = urljoin(careers_url, title_elem['href'])
                        
                        jobs.append(job)
        except Exception as e:
            logger.error(f"BambooHR extraction error: {e}")
        return jobs
    
    def extract_icims_jobs(self, html: str, careers_url: str) -> List[Dict[str, Any]]:
        """Extract jobs from iCIMS"""
        jobs = []
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # iCIMS uses specific class patterns
            job_elements = soup.find_all(['div', 'li', 'tr'], class_=re.compile(r'row|job|position|search', re.I))
            
            for elem in job_elements:
                title_elem = elem.find(['a', 'h2', 'h3'], class_=re.compile(r'title|job|position', re.I))
                if not title_elem:
                    title_elem = elem.find('a', href=re.compile(r'/jobs/|/job/'))
                
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if title and 5 < len(title) < 200:
                        job = {'title': title, 'source': 'icims_html'}
                        
                        link = title_elem if title_elem.name == 'a' else title_elem.find('a', href=True)
                        if link and link.get('href'):
                            job['url'] = urljoin(careers_url, link['href'])
                        
                        # Location
                        loc_elem = elem.find(class_=re.compile(r'location|city|state', re.I))
                        if loc_elem:
                            job['location'] = loc_elem.get_text(strip=True)
                        
                        jobs.append(job)
        except Exception as e:
            logger.error(f"iCIMS extraction error: {e}")
        return jobs
    
    def extract_workday_jobs(self, html: str, careers_url: str) -> List[Dict[str, Any]]:
        """Extract jobs from Workday"""
        jobs = []
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # Workday uses data-automation-id attributes
            job_elements = soup.find_all(attrs={'data-automation-id': re.compile(r'job|posting', re.I)})
            job_elements.extend(soup.find_all(['li', 'div'], class_=re.compile(r'job|posting|position', re.I)))
            
            for elem in job_elements:
                title_elem = elem.find(['a', 'h2', 'h3'], attrs={'data-automation-id': re.compile(r'title|jobTitle', re.I)})
                if not title_elem:
                    title_elem = elem.find(['a', 'h2', 'h3'])
                
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if title and 5 < len(title) < 200:
                        job = {'title': title, 'source': 'workday_html'}
                        
                        link = title_elem if title_elem.name == 'a' else title_elem.find('a', href=True)
                        if link and link.get('href'):
                            job['url'] = urljoin(careers_url, link['href'])
                        
                        # Location
                        loc_elem = elem.find(attrs={'data-automation-id': re.compile(r'location', re.I)})
                        if loc_elem:
                            job['location'] = loc_elem.get_text(strip=True)
                        
                        jobs.append(job)
        except Exception as e:
            logger.error(f"Workday extraction error: {e}")
        return jobs
    
    def extract_oracle_jobs(self, html: str, careers_url: str) -> List[Dict[str, Any]]:
        """Extract jobs from Oracle Taleo"""
        jobs = []
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # Oracle Taleo uses specific table structures
            job_rows = soup.find_all('tr', class_=re.compile(r'row|job|posting', re.I))
            job_rows.extend(soup.find_all(['div', 'li'], class_=re.compile(r'job|position', re.I)))
            
            for elem in job_rows:
                title_elem = elem.find(['a', 'td'], class_=re.compile(r'title|jobTitle', re.I))
                if not title_elem:
                    title_elem = elem.find('a', href=re.compile(r'/job/|/requisition'))
                
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if title and 5 < len(title) < 200:
                        job = {'title': title, 'source': 'oracle_html'}
                        
                        link = title_elem if title_elem.name == 'a' else title_elem.find('a', href=True)
                        if link and link.get('href'):
                            job['url'] = urljoin(careers_url, link['href'])
                        
                        jobs.append(job)
        except Exception as e:
            logger.error(f"Oracle extraction error: {e}")
        return jobs
    
    def extract_smartrecruiters_jobs(self, html: str, careers_url: str) -> List[Dict[str, Any]]:
        """Extract jobs from SmartRecruiters"""
        jobs = []
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # SmartRecruiters uses specific data attributes
            job_elements = soup.find_all(['div', 'li'], attrs={'data-job-id': True})
            job_elements.extend(soup.find_all(['div', 'li'], class_=re.compile(r'job|opening|position', re.I)))
            
            for elem in job_elements:
                title_elem = elem.find(['a', 'h2', 'h3'], class_=re.compile(r'title|job-title', re.I))
                if not title_elem:
                    title_elem = elem.find('a', href=re.compile(r'/jobs/'))
                
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if title and 5 < len(title) < 200:
                        job = {'title': title, 'source': 'smartrecruiters_html'}
                        
                        link = title_elem if title_elem.name == 'a' else title_elem.find('a', href=True)
                        if link and link.get('href'):
                            job['url'] = urljoin(careers_url, link['href'])
                        
                        jobs.append(job)
        except Exception as e:
            logger.error(f"SmartRecruiters extraction error: {e}")
        return jobs
    
    def extract_jobvite_jobs(self, html: str, careers_url: str) -> List[Dict[str, Any]]:
        """Extract jobs from Jobvite"""
        jobs = []
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # Jobvite uses specific class patterns
            job_elements = soup.find_all(['div', 'li'], class_=re.compile(r'job|position|opening', re.I))
            
            for elem in job_elements:
                title_elem = elem.find(['a', 'h2', 'h3'], class_=re.compile(r'title|job-title', re.I))
                if not title_elem:
                    title_elem = elem.find('a', href=re.compile(r'/jobs/'))
                
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if title and 5 < len(title) < 200:
                        job = {'title': title, 'source': 'jobvite_html'}
                        
                        link = title_elem if title_elem.name == 'a' else title_elem.find('a', href=True)
                        if link and link.get('href'):
                            job['url'] = urljoin(careers_url, link['href'])
                        
                        jobs.append(job)
        except Exception as e:
            logger.error(f"Jobvite extraction error: {e}")
        return jobs
    
    def extract_jobs(self, html: str, careers_url: str) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        """Detect ATS and extract all jobs"""
        ats_type = self.detect_ats(html, careers_url)
        
        if not ats_type:
            return None, []
        
        logger.info(f"  🎯 Detected ATS: {ats_type.upper()}")
        
        jobs = []
        if ats_type == 'greenhouse':
            jobs = self.extract_greenhouse_jobs(html, careers_url)
        elif ats_type == 'lever':
            jobs = self.extract_lever_jobs(html, careers_url)
        elif ats_type == 'workable':
            jobs = self.extract_workable_jobs(html, careers_url)
        elif ats_type == 'ashby':
            jobs = self.extract_ashby_jobs(html, careers_url)
        elif ats_type == 'bamboohr':
            jobs = self.extract_bamboohr_jobs(html, careers_url)
        elif ats_type == 'icims':
            jobs = self.extract_icims_jobs(html, careers_url)
        elif ats_type == 'workday':
            jobs = self.extract_workday_jobs(html, careers_url)
        elif ats_type == 'oracle':
            jobs = self.extract_oracle_jobs(html, careers_url)
        elif ats_type == 'smartrecruiters':
            jobs = self.extract_smartrecruiters_jobs(html, careers_url)
        elif ats_type == 'jobvite':
            jobs = self.extract_jobvite_jobs(html, careers_url)
        
        return ats_type, jobs

