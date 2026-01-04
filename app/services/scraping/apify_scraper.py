"""
Apify LinkedIn Scraper Service
Adapted from apify-api/api-scraping/scrape_linkedin.py for ICPv2.

Handles profile, posts, and reactions scraping via Apify actors.
Uses concurrent batching for performance (20 actors × 5 URLs each).
"""

import asyncio
import os
import re
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Set
from apify_client import ApifyClientAsync
from dotenv import load_dotenv

from ..db.supabase_client import supabase
from .profile_id_utils import get_profile_id_from_post, get_profile_id_from_profile

load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")

# Actor IDs
PROFILE_ACTOR_ID = "yZnhB5JewWf9xSmoM"  # LinkedIn Profile Scraper
POSTS_ACTOR_ID = "Wpp1BZ6yGWjySadk3"    # LinkedIn Posts Scraper
# REACTIONS_ACTOR_ID = "TBD"             # Future: LinkedIn Reactions Scraper

# Batch settings (matches original scrape_linkedin.py)
URLS_PER_ACTOR = 5           # URLs sent to each actor call
CONCURRENT_ACTORS = 20       # Actor runs in parallel
DELAY_BETWEEN_GROUPS = 10    # Seconds between concurrent groups

# Timeout for Apify actor calls (30 minutes)
APIFY_TIMEOUT_SECONDS = 1800

# Cache TTL for profile data (30 days)
CACHE_TTL_DAYS = 30


# ============================================================================
# URL UTILITIES
# ============================================================================

def normalize_linkedin_url(url: str) -> str:
    """
    Normalize a LinkedIn URL, preserving URN case and query parameters.
    
    LinkedIn exports use URN-style IDs (e.g., ACoAAA9fX4UBcq8K...) which are case-sensitive.
    The ?miniProfileUrn= query parameter is also needed for scraping.
    """
    if not url:
        return url
    
    url = url.strip()
    
    if 'linkedin.com/in/' not in url.lower():
        return url
    
    if not url.startswith('http'):
        url = 'https://' + url
    
    url = re.sub(r'https?://(www\.)?linkedin\.com', 'https://www.linkedin.com', url)
    
    return url


def extract_urn_from_url(url: str) -> Optional[str]:
    """Extract the URN/username from a LinkedIn URL (preserves case)."""
    if not url:
        return None
    match = re.search(r'/in/([^/?]+)', url)
    if match:
        return match.group(1)
    return None


def get_default_scrape_until() -> str:
    """Get default scrape date (1 year ago from today)."""
    one_year_ago = datetime.utcnow().replace(year=datetime.utcnow().year - 1)
    return one_year_ago.strftime("%Y-%m-%d")


# ============================================================================
# MAIN SCRAPER CLASS
# ============================================================================

class ApifyScraper:
    """
    LinkedIn scraper using Apify API with concurrent batching.
    
    Supports:
    - Profile scraping (current)
    - Posts scraping (future)
    - Reactions scraping (future)
    """
    
    def __init__(self):
        if not APIFY_TOKEN:
            raise ValueError("Missing APIFY_API_TOKEN environment variable")
        self.client = ApifyClientAsync(APIFY_TOKEN)
        self.active_run_ids: Set[str] = set()  # Track runs for cleanup
    
    # ========================================================================
    # CACHE MANAGEMENT
    # ========================================================================
    
    def check_cache(self, linkedin_url: str) -> Optional[Dict]:
        """Check if we have a cached profile that's still fresh."""
        try:
            normalized_url = normalize_linkedin_url(linkedin_url)
            result = supabase.table("profile_cache").select("*").eq("linkedin_url", normalized_url).execute()
            
            if result.data and len(result.data) > 0:
                cached = result.data[0]
                scraped_at = cached.get("scraped_at")
                
                if scraped_at:
                    scraped_dt = datetime.fromisoformat(scraped_at.replace('Z', '+00:00'))
                    cache_age = datetime.now(scraped_dt.tzinfo) - scraped_dt
                    
                    if cache_age < timedelta(days=CACHE_TTL_DAYS):
                        print(f"[Cache] HIT - {linkedin_url} ({cache_age.days}d old)")
                        return cached.get("profile_data")
                    else:
                        print(f"[Cache] STALE - {linkedin_url} ({cache_age.days}d > {CACHE_TTL_DAYS}d TTL)")
            
            return None
            
        except Exception as e:
            print(f"[Cache] Error: {e}")
            return None
    
    def save_to_cache(self, linkedin_url: str, profile_data: Dict) -> bool:
        """Save profile data to the cache."""
        try:
            normalized_url = normalize_linkedin_url(linkedin_url)
            public_id = get_profile_id_from_profile(profile_data) or extract_urn_from_url(linkedin_url)
            
            cache_entry = {
                "linkedin_url": normalized_url,
                "public_identifier": public_id,
                "profile_data": profile_data,
                "scraped_at": datetime.utcnow().isoformat()
            }
            
            supabase.table("profile_cache").upsert(cache_entry, on_conflict="linkedin_url").execute()
            return True
            
        except Exception as e:
            print(f"[Cache] Save error: {e}")
            return False
    
    # ========================================================================
    # ORPHAN CLEANUP (from original)
    # ========================================================================
    
    async def cleanup_running_actors(self, actor_id: str) -> None:
        """Check for and abort any running actors from previous failed runs."""
        print(f"\n[*] Checking for orphaned running actors...", flush=True)
        try:
            actor_client = self.client.actor(actor_id)
            runs_list = await actor_client.runs().list(status="RUNNING")
            
            running_runs = []
            if hasattr(runs_list, 'items'):
                running_runs = list(runs_list.items) if runs_list.items else []
            elif isinstance(runs_list, dict) and 'items' in runs_list:
                running_runs = runs_list['items']
            
            if not running_runs:
                print("[OK] No orphaned actors found", flush=True)
                return
            
            print(f"[!] Found {len(running_runs)} running actor(s) - aborting...", flush=True)
            
            for run in running_runs:
                run_id = run.get('id')
                if run_id:
                    try:
                        run_client = self.client.run(run_id)
                        await run_client.abort()
                        print(f"  [OK] Aborted run: {run_id}", flush=True)
                    except Exception as e:
                        print(f"  [!] Could not abort {run_id}: {e}", flush=True)
            
            print("[OK] Cleanup complete", flush=True)
            
        except Exception as e:
            print(f"[!] Could not check for running actors: {e}", flush=True)
    
    async def abort_active_runs(self) -> None:
        """Abort any runs we've started that might still be running."""
        if not self.active_run_ids:
            return
        
        print(f"\n[!] Aborting {len(self.active_run_ids)} active run(s)...", flush=True)
        for run_id in list(self.active_run_ids):
            try:
                run_client = self.client.run(run_id)
                await run_client.abort()
                print(f"  [OK] Aborted: {run_id}", flush=True)
                self.active_run_ids.discard(run_id)
            except Exception as e:
                print(f"  [!] Could not abort {run_id}: {e}", flush=True)
    
    # ========================================================================
    # PROFILE SCRAPING
    # ========================================================================
    
    async def scrape_profile_batch(
        self, 
        batch_num: int, 
        urls: List[str], 
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Scrape a batch of profile URLs with retry logic.
        Copied from original scrape_linkedin.py scrape_batch().
        
        Returns:
            Dict mapping URL -> result
        """
        print(f"\n[Batch {batch_num}] Starting scrape for {len(urls)} profiles...")
        
        current_run_id = None
        results = {}
        
        for attempt in range(max_retries):
            try:
                # Profile actor input format
                actor_input = {
                    "urls": [{"url": url} for url in urls],
                    "scrapeCompany": False,
                    "findContacts": False,
                }
                
                actor_client = self.client.actor(PROFILE_ACTOR_ID)
                start_time = time.time()
                print(f"[Batch {batch_num}] Starting Apify actor...", flush=True)
                
                # Start the run with timeout
                run_info = await actor_client.start(run_input=actor_input, timeout_secs=APIFY_TIMEOUT_SECONDS)
                current_run_id = run_info.get('id')
                self.active_run_ids.add(current_run_id)
                print(f"[Batch {batch_num}] Run ID: {current_run_id} (timeout: 30 min)", flush=True)
                
                # Wait for completion
                run_client = self.client.run(current_run_id)
                call_result = await run_client.wait_for_finish(wait_secs=APIFY_TIMEOUT_SECONDS)
                
                # Clear run ID on success
                self.active_run_ids.discard(current_run_id)
                current_run_id = None
                
                elapsed = time.time() - start_time
                print(f"[Batch {batch_num}] Actor completed in {elapsed:.1f}s", flush=True)
                
                if call_result is None:
                    raise Exception("Actor run returned None (timeout)")
                
                if call_result.get('status') != 'SUCCEEDED':
                    raise Exception(f"Actor run status: {call_result.get('status')}")
                
                # Fetch results from dataset
                dataset_id = call_result.get('defaultDatasetId')
                if not dataset_id:
                    raise Exception("No default dataset ID found")
                
                dataset_client = self.client.dataset(dataset_id)
                print(f"[Batch {batch_num}] Dataset ID: {dataset_id}", flush=True)
                
                await asyncio.sleep(2)
                
                # Get items from dataset
                profiles = []
                try:
                    list_items_result = await dataset_client.list_items()
                    if hasattr(list_items_result, 'items') and list_items_result.items:
                        profiles = list(list_items_result.items)
                    elif isinstance(list_items_result, dict) and 'items' in list_items_result:
                        profiles = list_items_result['items']
                    elif isinstance(list_items_result, list):
                        profiles = list_items_result
                    print(f"[Batch {batch_num}] Got {len(profiles)} profiles from list_items", flush=True)
                except Exception as e1:
                    print(f"[Batch {batch_num}] list_items failed: {e1}", flush=True)
                    try:
                        async for item in dataset_client.iterate_items():
                            profiles.append(item)
                        print(f"[Batch {batch_num}] iterate_items returned {len(profiles)} profiles", flush=True)
                    except Exception as e2:
                        print(f"[Batch {batch_num}] iterate_items also failed: {e2}", flush=True)
                
                print(f"[Batch {batch_num}] Successfully scraped {len(profiles)} profiles")
                
                # Build URN lookup for matching
                urn_to_url = {}
                for url in urls:
                    urn = extract_urn_from_url(url)
                    if urn:
                        urn_to_url[urn] = url
                
                # Match profiles to URLs
                for profile in profiles:
                    profile_urn = get_profile_id_from_profile(profile)
                    original_url = urn_to_url.get(profile_urn) if profile_urn else None
                    
                    if original_url:
                        self.save_to_cache(original_url, profile)
                        results[original_url] = {
                            "success": True,
                            "from_cache": False,
                            "profile_data": profile
                        }
                
                # Mark unmatched URLs as failed
                for url in urls:
                    if url not in results:
                        results[url] = {
                            "success": False,
                            "error": "No data returned",
                            "from_cache": False,
                            "profile_data": None
                        }
                
                return results
                
            except Exception as e:
                error_str = str(e)
                error_lower = error_str.lower()
                is_connection_error = any(x in error_lower for x in ["connection reset", "connection"])
                
                # On connection error, check if run actually succeeded (from original)
                if current_run_id and is_connection_error:
                    try:
                        print(f"[Batch {batch_num}] Connection lost - checking if run {current_run_id} succeeded...", flush=True)
                        run_client = self.client.run(current_run_id)
                        run_info = await run_client.get()
                        run_status = run_info.get('status') if run_info else None
                        print(f"[Batch {batch_num}] Run status: {run_status}", flush=True)
                        
                        if run_status == 'SUCCEEDED':
                            print(f"[Batch {batch_num}] Run succeeded despite connection error! Fetching results...", flush=True)
                            dataset_id = run_info.get('defaultDatasetId')
                            if dataset_id:
                                dataset_client = self.client.dataset(dataset_id)
                                list_items_result = await dataset_client.list_items()
                                profiles = list(list_items_result.items) if hasattr(list_items_result, 'items') and list_items_result.items else []
                                if profiles:
                                    urn_to_url = {extract_urn_from_url(url): url for url in urls if extract_urn_from_url(url)}
                                    for profile in profiles:
                                        profile_urn = get_profile_id_from_profile(profile)
                                        original_url = urn_to_url.get(profile_urn) if profile_urn else None
                                        if original_url:
                                            self.save_to_cache(original_url, profile)
                                            results[original_url] = {"success": True, "from_cache": False, "profile_data": profile}
                                    print(f"[Batch {batch_num}] Recovered {len(results)} results!", flush=True)
                                    self.active_run_ids.discard(current_run_id)
                                    for url in urls:
                                        if url not in results:
                                            results[url] = {"success": False, "error": "No data returned", "from_cache": False, "profile_data": None}
                                    return results
                        elif run_status == 'RUNNING':
                            print(f"[Batch {batch_num}] Run still in progress - NOT aborting (let it finish)", flush=True)
                            self.active_run_ids.discard(current_run_id)
                            # Mark all as failed for this attempt, they may succeed
                            for url in urls:
                                results[url] = {"success": False, "error": "Run still in progress", "from_cache": False, "profile_data": None}
                            return results
                    except Exception as check_err:
                        print(f"[Batch {batch_num}] Could not check run status: {check_err}", flush=True)
                
                # Abort run on non-connection errors
                elif current_run_id:
                    try:
                        print(f"[Batch {batch_num}] Aborting run {current_run_id}...", flush=True)
                        run_client = self.client.run(current_run_id)
                        await run_client.abort()
                        print(f"[Batch {batch_num}] Run aborted", flush=True)
                    except Exception as abort_err:
                        print(f"[Batch {batch_num}] Could not abort run: {abort_err}", flush=True)
                    self.active_run_ids.discard(current_run_id)
                    current_run_id = None
                
                # Retry on timeouts only
                is_retryable = any(x in error_lower for x in ["timed-out", "timed out", "timeout"])
                
                if attempt < max_retries - 1 and is_retryable:
                    wait_time = min(15 * (2 ** attempt), 60)  # 15s, 30s, 60s
                    print(f"[Batch {batch_num}] Attempt {attempt + 1}/{max_retries} failed, retrying in {wait_time}s", end="", flush=True)
                    for i in range(wait_time):
                        await asyncio.sleep(1)
                        if i % 5 == 4:
                            print(".", end="", flush=True)
                    print(" GO!", flush=True)
                    continue
                else:
                    print(f"[Batch {batch_num}] Failed after {attempt + 1} attempts: {error_str}")
                    for url in urls:
                        results[url] = {
                            "success": False,
                            "error": error_str,
                            "from_cache": False,
                            "profile_data": None
                        }
                    return results
        
        return results
    
    async def scrape_profiles_concurrent(self, urls: List[str]) -> Dict[str, Any]:
        """
        Scrape profiles with concurrent batching (20 actors × 5 URLs).
        Main entry point for profile scraping.
        
        Args:
            urls: List of LinkedIn profile URLs
        
        Returns:
            Dict mapping URL -> scrape result
        """
        if not urls:
            print("No URLs provided!")
            return {}
        
        # Cleanup any orphaned actors first
        await self.cleanup_running_actors(PROFILE_ACTOR_ID)
        
        # Check cache first
        results = {}
        urls_to_scrape = []
        
        print(f"\n[Scraper] Checking cache for {len(urls)} URLs...", flush=True)
        
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
        
        print(f"[Scraper] {len(results)} from cache, {len(urls_to_scrape)} to scrape", flush=True)
        
        if not urls_to_scrape:
            print(f"[OK] All {len(urls)} URLs in cache! Nothing to scrape.")
            return results
        
        # Split into batches of URLS_PER_ACTOR
        batches = []
        for i in range(0, len(urls_to_scrape), URLS_PER_ACTOR):
            batch_urls = urls_to_scrape[i:i + URLS_PER_ACTOR]
            batches.append((i // URLS_PER_ACTOR + 1, batch_urls))
        
        print(f"\nTotal URLs to scrape: {len(urls_to_scrape)}")
        print(f"Total batches: {len(batches)} (batch size: {URLS_PER_ACTOR})")
        print(f"Concurrent actors: {CONCURRENT_ACTORS}")
        
        # Process batches in concurrent groups
        for i in range(0, len(batches), CONCURRENT_ACTORS):
            batch_group = batches[i:i + CONCURRENT_ACTORS]
            batch_start = i + 1
            batch_end = min(i + CONCURRENT_ACTORS, len(batches))
            print(f"\n{'='*60}")
            print(f"Processing batches {batch_start}-{batch_end} of {len(batches)}...")
            print(f"{'='*60}")
            
            # Run batch_group concurrently with asyncio.gather
            batch_tasks = [
                self.scrape_profile_batch(batch_num, batch_urls) 
                for batch_num, batch_urls in batch_group
            ]
            group_results = await asyncio.gather(*batch_tasks)
            
            # Merge results
            for batch_result in group_results:
                results.update(batch_result)
            
            # Delay between groups
            if i + CONCURRENT_ACTORS < len(batches):
                print(f"\nWaiting {DELAY_BETWEEN_GROUPS} seconds before next group...", flush=True)
                await asyncio.sleep(DELAY_BETWEEN_GROUPS)
        
        # Summary
        success_count = sum(1 for r in results.values() if r.get("success"))
        cache_count = sum(1 for r in results.values() if r.get("from_cache"))
        fail_count = sum(1 for r in results.values() if not r.get("success"))
        
        print(f"\n{'='*60}")
        print(f"SCRAPING COMPLETE")
        print(f"{'='*60}")
        print(f"  Total: {len(results)}")
        print(f"  [OK] Success: {success_count} ({cache_count} from cache)")
        print(f"  [X] Failed: {fail_count}")
        print(f"{'='*60}\n")
        
        return results
    
    # ========================================================================
    # POSTS SCRAPING (for future use)
    # ========================================================================
    
    async def scrape_posts_batch(
        self, 
        batch_num: int, 
        urls: List[str],
        scrape_until: str = None,
        max_retries: int = 3
    ) -> List[Dict]:
        """
        Scrape posts for a batch of URLs with retry logic.
        Same pattern as scrape_profile_batch but for posts.
        
        Returns:
            List of post results
        """
        print(f"\n[Posts Batch {batch_num}] Starting scrape for {len(urls)} profiles...")
        
        current_run_id = None
        
        for attempt in range(max_retries):
            try:
                actor_input = {
                    "urls": urls,
                    "scrapeUntil": scrape_until or get_default_scrape_until(),
                    "deepScrape": False,
                    "rawData": False
                }
                
                actor_client = self.client.actor(POSTS_ACTOR_ID)
                start_time = time.time()
                print(f"[Posts Batch {batch_num}] Starting Apify actor...", flush=True)
                
                run_info = await actor_client.start(run_input=actor_input, timeout_secs=APIFY_TIMEOUT_SECONDS)
                current_run_id = run_info.get('id')
                self.active_run_ids.add(current_run_id)
                print(f"[Posts Batch {batch_num}] Run ID: {current_run_id} (timeout: 30 min)", flush=True)
                
                run_client = self.client.run(current_run_id)
                call_result = await run_client.wait_for_finish(wait_secs=APIFY_TIMEOUT_SECONDS)
                
                self.active_run_ids.discard(current_run_id)
                current_run_id = None
                
                elapsed = time.time() - start_time
                print(f"[Posts Batch {batch_num}] Actor completed in {elapsed:.1f}s", flush=True)
                
                if call_result is None:
                    raise Exception("Actor run returned None (timeout)")
                
                if call_result.get('status') != 'SUCCEEDED':
                    raise Exception(f"Actor run status: {call_result.get('status')}")
                
                dataset_id = call_result.get('defaultDatasetId')
                if not dataset_id:
                    raise Exception("No default dataset ID found")
                
                dataset_client = self.client.dataset(dataset_id)
                print(f"[Posts Batch {batch_num}] Dataset ID: {dataset_id}", flush=True)
                
                await asyncio.sleep(2)
                
                results = []
                try:
                    list_items_result = await dataset_client.list_items()
                    if hasattr(list_items_result, 'items') and list_items_result.items:
                        results = list(list_items_result.items)
                    elif isinstance(list_items_result, dict) and 'items' in list_items_result:
                        results = list_items_result['items']
                    elif isinstance(list_items_result, list):
                        results = list_items_result
                    print(f"[Posts Batch {batch_num}] Got {len(results)} posts", flush=True)
                except Exception as e1:
                    print(f"[Posts Batch {batch_num}] list_items failed: {e1}", flush=True)
                    try:
                        async for item in dataset_client.iterate_items():
                            results.append(item)
                        print(f"[Posts Batch {batch_num}] iterate_items returned {len(results)} posts", flush=True)
                    except Exception as e2:
                        print(f"[Posts Batch {batch_num}] iterate_items also failed: {e2}", flush=True)
                
                print(f"[Posts Batch {batch_num}] Successfully scraped {len(results)} posts")
                return results
                
            except Exception as e:
                error_str = str(e)
                error_lower = error_str.lower()
                
                # Similar retry logic as profiles
                is_retryable = any(x in error_lower for x in ["timed-out", "timed out", "timeout"])
                
                if attempt < max_retries - 1 and is_retryable:
                    wait_time = min(15 * (2 ** attempt), 60)
                    print(f"[Posts Batch {batch_num}] Attempt {attempt + 1}/{max_retries} failed, retrying in {wait_time}s...", flush=True)
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    print(f"[Posts Batch {batch_num}] Failed after {attempt + 1} attempts: {error_str}")
                    return []
        
        return []
    
    async def scrape_posts_concurrent(
        self, 
        urls: List[str],
        scrape_until: str = None
    ) -> List[Dict]:
        """
        Scrape posts with concurrent batching (20 actors × 5 URLs).
        
        Args:
            urls: List of LinkedIn profile URLs
            scrape_until: Date to scrape back to (YYYY-MM-DD)
        
        Returns:
            List of all posts
        """
        if not urls:
            print("No URLs provided!")
            return []
        
        await self.cleanup_running_actors(POSTS_ACTOR_ID)
        
        # Split into batches
        batches = []
        for i in range(0, len(urls), URLS_PER_ACTOR):
            batch_urls = urls[i:i + URLS_PER_ACTOR]
            batches.append((i // URLS_PER_ACTOR + 1, batch_urls))
        
        print(f"\nTotal URLs to scrape: {len(urls)}")
        print(f"Total batches: {len(batches)} (batch size: {URLS_PER_ACTOR})")
        
        all_posts = []
        
        for i in range(0, len(batches), CONCURRENT_ACTORS):
            batch_group = batches[i:i + CONCURRENT_ACTORS]
            print(f"\nProcessing batches {i+1}-{min(i+CONCURRENT_ACTORS, len(batches))} of {len(batches)}...")
            
            batch_tasks = [
                self.scrape_posts_batch(batch_num, batch_urls, scrape_until)
                for batch_num, batch_urls in batch_group
            ]
            group_results = await asyncio.gather(*batch_tasks)
            
            for batch_posts in group_results:
                all_posts.extend(batch_posts)
            
            if i + CONCURRENT_ACTORS < len(batches):
                print(f"\nWaiting {DELAY_BETWEEN_GROUPS} seconds before next group...", flush=True)
                await asyncio.sleep(DELAY_BETWEEN_GROUPS)
        
        print(f"\n[OK] Scraped {len(all_posts)} total posts from {len(urls)} profiles")
        return all_posts
    
    # ========================================================================
    # REACTIONS SCRAPING (future placeholder)
    # ========================================================================
    
    # async def scrape_reactions_concurrent(self, post_urns: List[str]) -> List[Dict]:
    #     """
    #     Scrape reactions for posts.
    #     TODO: Implement when reactions actor is available.
    #     """
    #     pass


# Singleton instance
scraper = ApifyScraper()
