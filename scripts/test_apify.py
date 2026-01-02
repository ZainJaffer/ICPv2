"""Test Apify scraper directly."""
import sys
import os
import asyncio
sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv()

print("=== Testing Apify Scraper ===\n")

# Check token
token = os.getenv("APIFY_API_TOKEN")
print(f"1. APIFY_API_TOKEN: {'SET' if token else 'NOT SET'}")
if not token:
    print("   ERROR: Add APIFY_API_TOKEN to .env file")
    sys.exit(1)

# Try to import and initialize scraper
print("\n2. Initializing scraper...")
try:
    from app.services.apify_scraper import scraper
    print("   ✓ Scraper initialized")
except Exception as e:
    print(f"   ✗ Failed: {e}")
    sys.exit(1)

# Test with one profile
print("\n3. Testing scrape on one profile...")
test_url = "https://www.linkedin.com/in/satyanadella"

async def test():
    print(f"   URL: {test_url}")
    print("   Calling Apify... (this may take 30-60 seconds)")
    result = await scraper.scrape_profile(test_url)
    print(f"\n4. Result:")
    print(f"   Success: {result.get('success')}")
    print(f"   From cache: {result.get('from_cache')}")
    if result.get('error'):
        print(f"   Error: {result.get('error')}")
    if result.get('profile_data'):
        data = result['profile_data']
        print(f"   Name: {data.get('firstName')} {data.get('lastName')}")
        print(f"   Headline: {data.get('headline', 'N/A')[:50]}...")

asyncio.run(test())
print("\n=== Test Complete ===")
