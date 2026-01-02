"""
Test script for concurrent scraping.
Run directly: python scripts/test_concurrent.py
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.services.supabase_client import supabase
from app.services.apify_scraper import scraper

BATCH_ID = "541581b9-4b08-4b0b-b01f-94c175b60df5"


async def main():
    print("=" * 60)
    print("CONCURRENT SCRAPING TEST")
    print("=" * 60)
    
    # Get discovered leads
    print("\n[1] Fetching discovered leads...")
    result = supabase.table("leads").select("linkedin_url").eq("batch_id", BATCH_ID).eq("status", "discovered").limit(25).execute()
    
    leads = result.data or []
    print(f"    Found {len(leads)} discovered leads")
    
    if not leads:
        print("    No discovered leads! Run check_leads.py to reset them.")
        return
    
    # Extract URLs
    urls = [lead["linkedin_url"] for lead in leads]
    print(f"\n[2] URLs to scrape:")
    for i, url in enumerate(urls[:5]):
        print(f"    {i+1}. {url[:70]}...")
    if len(urls) > 5:
        print(f"    ... and {len(urls) - 5} more")
    
    # Run concurrent scraping
    print(f"\n[3] Starting concurrent scraping (20 actors × 5 URLs)...")
    print("-" * 60)
    
    results = await scraper.scrape_profiles_concurrent(urls)
    
    # Summary
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    success = sum(1 for r in results.values() if r.get("success"))
    cached = sum(1 for r in results.values() if r.get("from_cache"))
    failed = sum(1 for r in results.values() if not r.get("success"))
    
    print(f"  Total: {len(results)}")
    print(f"  Success: {success} ({cached} from cache)")
    print(f"  Failed: {failed}")


if __name__ == "__main__":
    asyncio.run(main())
