"""Set up Allison Gates client with marketing ICP and ingest her followers."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(".env.local")

import uuid
from app.services.db.supabase_client import supabase
from app.services.scraping.html_parser import extract_linkedin_urls
from app.services.enrichment import create_leads_from_urls

# Create Allison Gates client
client_id = str(uuid.uuid4())
client_data = {
    "id": client_id,
    "name": "Allison Gates"
}

print("="*60)
print("SETTING UP ALLISON GATES")
print("="*60)

# Check if client already exists
existing = supabase.table("clients").select("id").eq("name", "Allison Gates").execute()
if existing.data:
    client_id = existing.data[0]["id"]
    print(f"\n1. Found existing client: Allison Gates ({client_id[:8]}...)")
else:
    result = supabase.table("clients").insert(client_data).execute()
    print(f"\n1. Created client: {client_data['name']} ({client_id[:8]}...)")

# Create ICP: CMOs and Head of Marketing at tech companies
icp_data = {
    "client_id": client_id,
    "target_titles": [
        "CMO", 
        "Chief Marketing Officer", 
        "Head of Marketing", 
        "VP Marketing", 
        "VP of Marketing",
        "Director of Marketing",
        "Marketing Director",
        "Head of Growth",
        "VP Growth"
    ],
    "target_industries": [
        "SaaS", 
        "AI", 
        "Technology", 
        "Software", 
        "Fintech",
        "B2B Tech",
        "Enterprise Software"
    ],
    "company_sizes": ["startup", "scaleup", "mid-market", "enterprise"],
    "target_keywords": ["marketing", "growth", "demand gen", "brand"],
    "notes": "Looking for marketing leaders at tech companies"
}

# Check if ICP exists
existing_icp = supabase.table("client_icps").select("*").eq("client_id", client_id).execute()
if existing_icp.data:
    supabase.table("client_icps").update(icp_data).eq("client_id", client_id).execute()
    print(f"\n2. Updated ICP:")
else:
    supabase.table("client_icps").insert(icp_data).execute()
    print(f"\n2. Created ICP:")
print(f"   Titles: {icp_data['target_titles']}")
print(f"   Industries: {icp_data['target_industries']}")

# Create batch
batch_id = str(uuid.uuid4())
batch_data = {
    "id": batch_id,
    "client_id": client_id,
    "status": "processing"
}
supabase.table("batches").insert(batch_data).execute()
print(f"\n3. Created batch: {batch_id[:8]}...")

# Extract URLs from HTML
print(f"\n4. Extracting URLs from allison_gates.html...")
with open("inputs/allison_gates.html", "r", encoding="utf-8") as f:
    html_content = f.read()

urls = extract_linkedin_urls(html_content)
print(f"   Found {len(urls)} LinkedIn URLs")

# Limit to 50 for testing
test_urls = urls[:50]
print(f"   Using first {len(test_urls)} for testing")

# Create leads
print(f"\n5. Creating leads...")
import asyncio
created, duplicates = asyncio.run(create_leads_from_urls(client_id, batch_id, test_urls))

# Update batch counts
supabase.table("batches").update({
    "discovered_count": created,
    "status": "discovered"
}).eq("id", batch_id).execute()

print(f"\n" + "="*60)
print(f"SETUP COMPLETE")
print(f"  Client ID: {client_id}")
print(f"  Batch ID: {batch_id}")
print(f"  Leads created: {created}")
print(f"="*60)
print(f"\nNext steps:")
print(f"  1. Enrich: POST http://localhost:8001/batches/{batch_id}/enrich")
print(f"  2. Qualify: POST http://localhost:8001/batches/{batch_id}/qualify")
print(f"  3. Export: GET http://localhost:8001/batches/{batch_id}/export")
