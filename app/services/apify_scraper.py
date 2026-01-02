"""
Apify LinkedIn Scraper Service
Adapted from apify-api/api-backend/services/apify_scraper.py for ICPv2.

Handles both profile and posts scraping via Apify actors.
Posts scraping is included for future use (reactions, engagement data).
"""

import asyncio
import os
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from apify_client import ApifyClientAsync
from dotenv import load_dotenv

from .supabase_client import supabase
from .profile_id_utils import get_profile_id_from_post, get_profile_id_from_profile

load_dotenv()

# Configuration
APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")
POSTS_ACTOR_ID = "Wpp1BZ6yGWjySadk3"  # LinkedIn Posts Scraper
PROFILE_ACTOR_ID = "yZnhB5JewWf9xSmoM"  # LinkedIn Profile Scraper

# Timeout for Apify actor calls (30 minutes)
APIFY_TIMEOUT_SECONDS = 1800

# Cache TTL for profile data (30 days)
CACHE_TTL_DAYS = 30


def normalize_linkedin_url(url: str) -> str:
    """
    Normalize a LinkedIn URL, preserving URN case and query parameters.
    
    LinkedIn exports use URN-style IDs (e.g., ACoAAA9fX4UBcq8K...) which are case-sensitive.
    The ?miniProfileUrn= query parameter is also needed for scraping.
    
    Returns: Full URL with original case and query params preserved
    """
    if not url:
        return url
    
    url = url.strip()
    
    # Check if it's a LinkedIn profile URL (case-insensitive check)
    if 'linkedin.com/in/' not in url.lower():
        return url
    
    # Ensure https:// prefix
    if not url.startswith('http'):
        url = 'https://' + url
    
    # Normalize to www.linkedin.com but preserve the rest (case and query params)
    url = re.sub(r'https?://(www\.)?linkedin\.com', 'https://www.linkedin.com', url)
    
    return url


def extract_public_identifier(url: str) -> Optional[str]:
    """Extract the public identifier (username) from a LinkedIn URL."""
    if not url:
        return None
    
    match = re.search(r'linkedin\.com/in/([^/?#]+)', url.lower())
    if match:
        return match.group(1)
    return None


def get_default_scrape_until():
    """Get default scrape date (1 year ago from today)."""
    one_year_ago = datetime.utcnow().replace(year=datetime.utcnow().year - 1)
    return one_year_ago.strftime("%Y-%m-%d")


class ApifyScraper:
    """LinkedIn scraper using Apify API with Supabase storage."""
    
    def __init__(self):
        if not APIFY_TOKEN:
            raise ValueError("Missing APIFY_API_TOKEN environment variable")
        self.client = ApifyClientAsync(APIFY_TOKEN)
        self.posts_actor_id = POSTS_ACTOR_ID
        self.profile_actor_id = PROFILE_ACTOR_ID
    
    def check_cache(self, linkedin_url: str) -> Optional[Dict]:
        """
        Check if we have a cached profile that's still fresh (within TTL).
        
        Returns the cached profile_data if fresh, None if stale or not found.
        """
        try:
            normalized_url = normalize_linkedin_url(linkedin_url)
            result = supabase.table("profile_cache").select("*").eq("linkedin_url", normalized_url).execute()
            
            if result.data and len(result.data) > 0:
                cached = result.data[0]
                scraped_at = cached.get("scraped_at")
                
                if scraped_at:
                    # Parse the timestamp
                    scraped_dt = datetime.fromisoformat(scraped_at.replace('Z', '+00:00'))
                    cache_age = datetime.now(scraped_dt.tzinfo) - scraped_dt
                    
                    if cache_age < timedelta(days=CACHE_TTL_DAYS):
                        print(f"[Cache] HIT - {linkedin_url} scraped {cache_age.days} days ago")
                        return cached.get("profile_data")
                    else:
                        print(f"[Cache] STALE - {linkedin_url} scraped {cache_age.days} days ago (TTL: {CACHE_TTL_DAYS})")
            
            print(f"[Cache] MISS - {linkedin_url}")
            return None
            
        except Exception as e:
            print(f"[Cache] Error checking cache: {e}")
            return None
    
    def save_to_cache(self, linkedin_url: str, profile_data: Dict) -> bool:
        """Save profile data to the cache."""
        try:
            normalized_url = normalize_linkedin_url(linkedin_url)
            public_id = get_profile_id_from_profile(profile_data) or extract_public_identifier(linkedin_url)
            
            cache_entry = {
                "linkedin_url": normalized_url,
                "public_identifier": public_id,
                "profile_data": profile_data,
                "scraped_at": datetime.utcnow().isoformat()
            }
            
            supabase.table("profile_cache").upsert(cache_entry, on_conflict="linkedin_url").execute()
            print(f"[Cache] SAVED - {linkedin_url}")
            return True
            
        except Exception as e:
            print(f"[Cache] Error saving to cache: {e}")
            return False
    
    async def scrape_profile(self, url: str) -> Dict[str, Any]:
        """
        Scrape a single LinkedIn profile using Apify.
        Checks cache first, only calls Apify if cache miss or stale.
        
        Args:
            url: LinkedIn profile URL
        
        Returns:
            Dict with scrape results including profile data
        """
        normalized_url = normalize_linkedin_url(url)
        
        # Check cache first
        cached_data = self.check_cache(normalized_url)
        if cached_data:
            return {
                "url": normalized_url,
                "success": True,
                "from_cache": True,
                "profile_data": cached_data
            }
        
        # Cache miss - call Apify
        run_id = None
        try:
            actor_input = {
                "urls": [{"url": normalized_url}],
                "scrapeCompany": False,
                "findContacts": False,
            }
            
            timeout_mins = APIFY_TIMEOUT_SECONDS // 60
            print(f"[Scraper] Starting Apify profile actor for {url}... (timeout: {timeout_mins} min)", flush=True)
            
            actor_client = self.client.actor(self.profile_actor_id)
            run_info = await actor_client.start(run_input=actor_input)
            run_id = run_info.get("id") if run_info else None
            
            if run_id:
                print(f"[Scraper] Profile actor run ID: {run_id}", flush=True)
            else:
                raise Exception("Failed to start profile actor run - no run ID returned")
            
            run_client = self.client.run(run_id)
            call_result = await run_client.wait_for_finish(wait_secs=APIFY_TIMEOUT_SECONDS)
            
            if call_result is None:
                print(f"[Scraper] TIMEOUT: Profile actor exceeded {timeout_mins} min for {url}", flush=True)
                return {
                    "url": normalized_url,
                    "success": False,
                    "error": f"Apify timeout after {timeout_mins} minutes",
                    "from_cache": False,
                    "profile_data": None,
                    "run_id": run_id,
                    "timeout": True
                }
            
            print(f"[Scraper] Profile actor finished with status: {call_result.get('status')}", flush=True)
            
            if call_result.get("status") != "SUCCEEDED":
                raise Exception(f"Profile actor run failed: {call_result.get('status')}")
            
            # Fetch results from dataset
            dataset_id = call_result.get("defaultDatasetId")
            if not dataset_id:
                raise Exception("No dataset ID returned from profile scraper")
            
            print(f"[Scraper] Fetching profile from dataset: {dataset_id}", flush=True)
            dataset_client = self.client.dataset(dataset_id)
            await asyncio.sleep(2)
            
            results = []
            try:
                list_items_result = await dataset_client.list_items()
                if hasattr(list_items_result, 'items') and list_items_result.items:
                    results = list(list_items_result.items)
                elif hasattr(list_items_result, 'data') and list_items_result.data:
                    results = list(list_items_result.data)
                elif isinstance(list_items_result, dict) and 'items' in list_items_result:
                    results = list_items_result['items']
                elif isinstance(list_items_result, list):
                    results = list_items_result
            except Exception as e1:
                print(f"[Scraper] list_items failed: {e1}", flush=True)
            
            if not results:
                try:
                    async for item in dataset_client.iterate_items():
                        results.append(item)
                except Exception as e2:
                    print(f"[Scraper] iterate_items also failed: {e2}", flush=True)
            
            print(f"[Scraper] Found {len(results)} profile(s)", flush=True)
            
            profile_data = None
            if results:
                profile_data = results[0]
                # Save to cache
                self.save_to_cache(normalized_url, profile_data)
            
            return {
                "url": normalized_url,
                "success": True,
                "from_cache": False,
                "profile_data": profile_data,
                "run_id": run_id
            }
            
        except Exception as e:
            print(f"[Scraper] Profile ERROR: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return {
                "url": normalized_url,
                "success": False,
                "error": str(e),
                "from_cache": False,
                "profile_data": None,
                "run_id": run_id
            }
    
    async def scrape_profiles_batch(self, urls: List[str]) -> Dict[str, Any]:
        """
        Scrape multiple LinkedIn profiles in a single Apify call.
        Checks cache first, only sends uncached URLs to Apify.
        
        Args:
            urls: List of LinkedIn profile URLs
        
        Returns:
            Dict with results for each URL
        """
        results = {}
        urls_to_scrape = []
        
        print(f"\n[Scraper] Batch: Checking cache for {len(urls)} URLs...", flush=True)
        
        # Check cache for each URL
        for url in urls:
            normalized_url = normalize_linkedin_url(url)
            cached_data = self.check_cache(normalized_url)
            
            if cached_data:
                results[normalized_url] = {
                    "success": True,
                    "from_cache": True,
                    "profile_data": cached_data
                }
            else:
                urls_to_scrape.append(normalized_url)
        
        print(f"[Scraper] Batch: {len(results)} from cache, {len(urls_to_scrape)} to scrape", flush=True)
        
        if not urls_to_scrape:
            return results
        
        # Build URN → URL lookup for matching results back
        urn_to_url = {}
        for url in urls_to_scrape:
            match = re.search(r'/in/([^/?]+)', url)
            if match:
                urn = match.group(1)
                urn_to_url[urn] = url
        
        # Scrape all uncached URLs in one Apify call
        run_id = None
        try:
            actor_input = {
                "urls": [{"url": url} for url in urls_to_scrape],
                "scrapeCompany": False,
                "findContacts": False,
            }
            
            timeout_mins = APIFY_TIMEOUT_SECONDS // 60
            print(f"[Scraper] Batch: Starting Apify for {len(urls_to_scrape)} profiles... (timeout: {timeout_mins} min)", flush=True)
            
            actor_client = self.client.actor(self.profile_actor_id)
            run_info = await actor_client.start(run_input=actor_input)
            run_id = run_info.get("id") if run_info else None
            
            if run_id:
                print(f"[Scraper] Batch: Actor run ID: {run_id}", flush=True)
            else:
                raise Exception("Failed to start actor run - no run ID returned")
            
            run_client = self.client.run(run_id)
            call_result = await run_client.wait_for_finish(wait_secs=APIFY_TIMEOUT_SECONDS)
            
            if call_result is None:
                print(f"[Scraper] Batch: TIMEOUT after {timeout_mins} min", flush=True)
                for url in urls_to_scrape:
                    results[url] = {"success": False, "error": "Timeout", "from_cache": False, "profile_data": None}
                return results
            
            print(f"[Scraper] Batch: Actor finished with status: {call_result.get('status')}", flush=True)
            
            if call_result.get("status") != "SUCCEEDED":
                raise Exception(f"Actor run failed: {call_result.get('status')}")
            
            # Fetch results from dataset
            dataset_id = call_result.get("defaultDatasetId")
            if not dataset_id:
                raise Exception("No dataset ID returned")
            
            print(f"[Scraper] Batch: Fetching from dataset: {dataset_id}", flush=True)
            dataset_client = self.client.dataset(dataset_id)
            await asyncio.sleep(2)
            
            profiles = []
            try:
                list_items_result = await dataset_client.list_items()
                if hasattr(list_items_result, 'items') and list_items_result.items:
                    profiles = list(list_items_result.items)
                elif isinstance(list_items_result, dict) and 'items' in list_items_result:
                    profiles = list_items_result['items']
                elif isinstance(list_items_result, list):
                    profiles = list_items_result
            except Exception as e:
                print(f"[Scraper] Batch: list_items failed: {e}", flush=True)
            
            print(f"[Scraper] Batch: Got {len(profiles)} profiles", flush=True)
            
            # Match profiles to URLs using URN
            for profile in profiles:
                # Get URN from profile data
                profile_urn = get_profile_id_from_profile(profile)
                
                # Find original URL using URN lookup
                original_url = urn_to_url.get(profile_urn) if profile_urn else None
                
                if original_url:
                    self.save_to_cache(original_url, profile)
                    results[original_url] = {
                        "success": True,
                        "from_cache": False,
                        "profile_data": profile
                    }
                    print(f"[Scraper] Batch: Matched {profile_urn[:20]}... → {profile.get('firstName', '')} {profile.get('lastName', '')}", flush=True)
            
            # Mark any URLs we didn't get results for as failed
            for url in urls_to_scrape:
                if url not in results:
                    results[url] = {"success": False, "error": "No data returned", "from_cache": False, "profile_data": None}
            
            return results
            
        except Exception as e:
            print(f"[Scraper] Batch ERROR: {e}", flush=True)
            import traceback
            traceback.print_exc()
            
            for url in urls_to_scrape:
                if url not in results:
                    results[url] = {"success": False, "error": str(e), "from_cache": False, "profile_data": None}
            
            return results
    
    # ============================================
    # Posts Scraping (for future use)
    # ============================================
    
    async def scrape_posts(
        self,
        url: str,
        scrape_until: str = None
    ) -> Dict[str, Any]:
        """
        Scrape posts for a LinkedIn profile using Apify.
        
        Args:
            url: LinkedIn profile URL
            scrape_until: Date to scrape back to (YYYY-MM-DD)
        
        Returns:
            Dict with scrape results including posts
        """
        normalized_url = normalize_linkedin_url(url)
        run_id = None
        
        try:
            actor_input = {
                "urls": [normalized_url],
                "scrapeUntil": scrape_until or get_default_scrape_until(),
                "deepScrape": False,
                "rawData": False
            }
            
            timeout_mins = APIFY_TIMEOUT_SECONDS // 60
            print(f"[Scraper] Starting Apify posts actor for {url}... (timeout: {timeout_mins} min)", flush=True)
            
            actor_client = self.client.actor(self.posts_actor_id)
            run_info = await actor_client.start(run_input=actor_input)
            run_id = run_info.get("id") if run_info else None
            
            if run_id:
                print(f"[Scraper] Posts actor run ID: {run_id}", flush=True)
            else:
                raise Exception("Failed to start actor run - no run ID returned")
            
            run_client = self.client.run(run_id)
            call_result = await run_client.wait_for_finish(wait_secs=APIFY_TIMEOUT_SECONDS)
            
            if call_result is None:
                print(f"[Scraper] TIMEOUT: Posts actor exceeded {timeout_mins} min for {url}", flush=True)
                return {
                    "url": normalized_url,
                    "success": False,
                    "error": f"Apify timeout after {timeout_mins} minutes",
                    "posts": [],
                    "run_id": run_id,
                    "timeout": True
                }
            
            print(f"[Scraper] Actor finished with status: {call_result.get('status')}", flush=True)
            
            if call_result.get("status") != "SUCCEEDED":
                raise Exception(f"Actor run failed: {call_result.get('status')}")
            
            # Fetch results from dataset
            dataset_id = call_result.get("defaultDatasetId")
            if not dataset_id:
                raise Exception("No dataset ID returned")
            
            print(f"[Scraper] Fetching results from dataset: {dataset_id}", flush=True)
            dataset_client = self.client.dataset(dataset_id)
            await asyncio.sleep(2)
            
            results = []
            try:
                list_items_result = await dataset_client.list_items()
                if hasattr(list_items_result, 'items') and list_items_result.items:
                    results = list(list_items_result.items)
                elif hasattr(list_items_result, 'data') and list_items_result.data:
                    results = list(list_items_result.data)
                elif isinstance(list_items_result, dict) and 'items' in list_items_result:
                    results = list_items_result['items']
                elif isinstance(list_items_result, list):
                    results = list_items_result
            except Exception as e1:
                print(f"[Scraper] list_items failed: {e1}", flush=True)
            
            if not results:
                try:
                    async for item in dataset_client.iterate_items():
                        results.append(item)
                except Exception as e2:
                    print(f"[Scraper] iterate_items also failed: {e2}", flush=True)
            
            print(f"[Scraper] Found {len(results)} posts", flush=True)
            
            return {
                "url": normalized_url,
                "success": True,
                "posts": results,
                "run_id": run_id
            }
            
        except Exception as e:
            print(f"[Scraper] ERROR: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return {
                "url": normalized_url,
                "success": False,
                "error": str(e),
                "posts": [],
                "run_id": run_id
            }


# Singleton instance
scraper = ApifyScraper()
