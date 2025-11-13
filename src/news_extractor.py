"""
News and Blog Extraction Module

Extracts news articles from:
- RSS/Atom feeds
- Blog index pages
- Individual article pages
"""

import json
import re
import logging
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, urljoin
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import feedparser
import trafilatura

logger = logging.getLogger(__name__)


class NewsExtractor:
    """Extract news articles from various sources"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.parsed_base = urlparse(base_url)
    
    def find_rss_feeds(self, html: str) -> List[str]:
        """Find RSS/Atom feed URLs"""
        feeds = []
        soup = BeautifulSoup(html, 'lxml')
        
        # Look for feed links
        for link in soup.find_all('link', type=lambda x: x and ('rss' in x.lower() or 'atom' in x.lower() or 'xml' in x.lower())):
            href = link.get('href')
            if href:
                feeds.append(urljoin(self.base_url, href))
        
        # Also check for common feed paths
        common_feeds = [
            '/feed', '/feed.xml', '/rss', '/rss.xml', '/atom.xml',
            '/blog/feed', '/news/feed', '/feed.rss'
        ]
        
        for feed_path in common_feeds:
            feed_url = urljoin(self.base_url, feed_path)
            # Try to fetch to verify
            try:
                response = requests.head(feed_url, timeout=5, allow_redirects=True)
                if response.status_code == 200 and 'xml' in response.headers.get('content-type', '').lower():
                    feeds.append(feed_url)
            except:
                pass
        
        return list(set(feeds))
    
    def extract_from_rss(self, feed_url: str) -> List[Dict[str, Any]]:
        """Extract articles from RSS/Atom feed"""
        articles = []
        
        try:
            feed = feedparser.parse(feed_url)
            
            for entry in feed.entries:
                article = {
                    'title': entry.get('title', ''),
                    'url': entry.get('link', ''),
                    'author': entry.get('author', ''),
                    'date_published': entry.get('published', '') or entry.get('updated', ''),
                    'excerpt': entry.get('summary', '') or entry.get('description', ''),
                    'categories': [tag.term for tag in entry.get('tags', [])],
                    'source': 'rss_feed'
                }
                
                # Try to extract content
                if entry.get('content'):
                    article['content'] = entry.get('content')[0].get('value', '')
                
                articles.append(article)
            
            logger.info(f"  ✅ RSS Feed: {len(articles)} articles")
            
        except Exception as e:
            logger.debug(f"RSS extraction error: {e}")
        
        return articles
    
    def extract_article_links_from_index(self, html: str, blog_url: str) -> List[str]:
        """Extract article URLs from blog index page"""
        article_urls = []
        soup = BeautifulSoup(html, 'lxml')
        
        # Common article link patterns
        article_selectors = [
            'article a',
            '.post a',
            '.blog-post a',
            '.article-link',
            'h2 a', 'h3 a',
            '[class*="post"] a',
            '[class*="article"] a'
        ]
        
        for selector in article_selectors:
            links = soup.select(selector)
            for link in links:
                href = link.get('href', '')
                if not href:
                    continue
                
                full_url = urljoin(blog_url, href)
                parsed = urlparse(full_url)
                
                # Only same domain
                if parsed.netloc != self.parsed_base.netloc:
                    continue
                
                # Skip non-article pages
                if any(skip in href.lower() for skip in ['/category/', '/tag/', '/author/', '/page/', '/search', '/archive']):
                    continue
                
                # Check if it looks like an article
                if any(kw in href.lower() for kw in ['/blog/', '/news/', '/post/', '/article/']):
                    if full_url not in article_urls:
                        article_urls.append(full_url)
        
        return article_urls
    
    def extract_article_content(self, html: str, url: str) -> Dict[str, Any]:
        """Extract full article content from a page"""
        article = {
            "url": url,
            "title": "",
            "author": "",
            "date_published": "",
            "content": "",
            "excerpt": "",
            "categories": [],
            "tags": [],
            "images": [],
            "word_count": 0
        }
        
        soup = BeautifulSoup(html, 'lxml')
        
        # Extract from JSON-LD
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get('@type') in ['Article', 'BlogPosting', 'NewsArticle']:
                    article['title'] = data.get('headline') or data.get('name', '')
                    article['author'] = data.get('author', {}).get('name') if isinstance(data.get('author'), dict) else data.get('author', '')
                    article['date_published'] = data.get('datePublished', '')
                    article['excerpt'] = data.get('description', '')
            except:
                pass
        
        # Extract from HTML
        if not article['title']:
            title_tag = soup.find('title')
            if title_tag:
                article['title'] = title_tag.get_text(strip=True)
        
        # Extract article content
        article_tag = soup.find('article')
        if article_tag:
            for tag in article_tag.find_all(['script', 'style', 'nav', 'footer']):
                tag.decompose()
            article['content'] = article_tag.get_text(separator='\n', strip=True)
        else:
            # Try trafilatura
            try:
                article['content'] = trafilatura.extract(html, include_tables=True) or ""
            except:
                pass
        
        # Extract author
        author_elem = soup.find(['span', 'div', 'p'], class_=re.compile(r'author', re.I))
        if author_elem:
            article['author'] = author_elem.get_text(strip=True)
        
        # Extract date
        date_elem = soup.find('time', datetime=True)
        if date_elem:
            article['date_published'] = date_elem.get('datetime', '')
        
        # Calculate word count
        article['word_count'] = len(article['content'].split())
        
        return article

