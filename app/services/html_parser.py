"""
HTML Parser - Extract LinkedIn URLs from exported HTML files.

Handles various LinkedIn export formats:
- Followers list HTML
- Connections export HTML
- Any HTML containing LinkedIn profile links
"""

import re
from typing import List, Set
from bs4 import BeautifulSoup


def normalize_linkedin_url(url: str) -> str:
    """
    Normalize a LinkedIn URL to canonical format.
    
    Returns: https://www.linkedin.com/in/username
    """
    if not url:
        return ""
    
    url = url.strip().rstrip('/')
    
    # Extract username from various LinkedIn URL formats
    match = re.search(r'linkedin\.com/in/([^/?#]+)', url.lower())
    if match:
        username = match.group(1)
        return f"https://www.linkedin.com/in/{username}"
    
    return ""


def extract_linkedin_urls(html_content: str) -> List[str]:
    """
    Extract unique LinkedIn profile URLs from HTML content.
    
    Args:
        html_content: Raw HTML string
    
    Returns:
        List of normalized, unique LinkedIn profile URLs
    """
    urls: Set[str] = set()
    
    # Method 1: Parse with BeautifulSoup and find all links
    try:
        soup = BeautifulSoup(html_content, 'lxml')
        
        # Find all anchor tags with href
        for link in soup.find_all('a', href=True):
            href = link['href']
            if 'linkedin.com/in/' in href.lower():
                normalized = normalize_linkedin_url(href)
                if normalized:
                    urls.add(normalized)
        
        # Also check data attributes that might contain URLs
        for element in soup.find_all(attrs={"data-url": True}):
            data_url = element.get("data-url", "")
            if 'linkedin.com/in/' in data_url.lower():
                normalized = normalize_linkedin_url(data_url)
                if normalized:
                    urls.add(normalized)
    
    except Exception as e:
        print(f"[Parser] BeautifulSoup parsing error: {e}")
    
    # Method 2: Regex fallback for any URLs in the raw HTML
    # This catches URLs that might not be in proper anchor tags
    try:
        # Match linkedin.com/in/username patterns
        pattern = r'https?://(?:www\.)?linkedin\.com/in/([a-zA-Z0-9_-]+)'
        matches = re.findall(pattern, html_content, re.IGNORECASE)
        
        for username in matches:
            normalized = f"https://www.linkedin.com/in/{username.lower()}"
            urls.add(normalized)
    
    except Exception as e:
        print(f"[Parser] Regex parsing error: {e}")
    
    # Convert to sorted list for consistent ordering
    result = sorted(list(urls))
    
    print(f"[Parser] Extracted {len(result)} unique LinkedIn URLs")
    
    return result


def extract_urls_from_text(text: str) -> List[str]:
    """
    Extract LinkedIn URLs from plain text (not HTML).
    
    Useful for:
    - Pasted lists of URLs
    - CSV content
    - Plain text exports
    
    Args:
        text: Plain text containing LinkedIn URLs
    
    Returns:
        List of normalized, unique LinkedIn profile URLs
    """
    urls: Set[str] = set()
    
    # Match linkedin.com/in/username patterns
    pattern = r'https?://(?:www\.)?linkedin\.com/in/([a-zA-Z0-9_-]+)'
    matches = re.findall(pattern, text, re.IGNORECASE)
    
    for username in matches:
        normalized = f"https://www.linkedin.com/in/{username.lower()}"
        urls.add(normalized)
    
    # Also try to match just "linkedin.com/in/username" without protocol
    pattern_no_protocol = r'(?:www\.)?linkedin\.com/in/([a-zA-Z0-9_-]+)'
    matches = re.findall(pattern_no_protocol, text, re.IGNORECASE)
    
    for username in matches:
        normalized = f"https://www.linkedin.com/in/{username.lower()}"
        urls.add(normalized)
    
    return sorted(list(urls))
