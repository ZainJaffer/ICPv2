"""
Test Phase 2: Full Ingestion Flow

1. Create client "Ben Turtel"
2. Upload ben_turtel.html
3. Verify leads are created in Supabase
"""
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.supabase_client import supabase
from app.services.html_parser import extract_linkedin_urls
from app.services.enrichment import create_leads_from_urls
import asyncio

CLIENT_NAME = "Ben Turtel"
HTML_FILE = Path("C:/Users/Zain Jaffer/Desktop/Dev/ICPv2/inputs/ben_turtel.html")
OUTPUT_FILE = Path("C:/Users/Zain Jaffer/Desktop/Dev/ICPv2/ingestion_test.txt")


def get_or_create_client(name: str) -> str:
    """Get existing client or create new one."""
    result = supabase.table("clients").select("id").eq("name", name).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]["id"]
    
    # Create new client
    result = supabase.table("clients").insert({"name": name}).execute()
    client_id = result.data[0]["id"]
    
    # Create empty ICP
    supabase.table("client_icps").insert({"client_id": client_id}).execute()
    
    return client_id


def create_batch(client_id: str, filename: str, total_leads: int) -> str:
    """Create a new batch."""
    result = supabase.table("batches").insert({
        "client_id": client_id,
        "filename": filename,
        "status": "processing",
        "total_leads": total_leads
    }).execute()
    return result.data[0]["id"]


async def main():
    output_lines = []
    
    def log(msg):
        print(msg)
        output_lines.append(msg)
    
    log("=" * 60)
    log("PHASE 2 TEST: Full Ingestion Flow")
    log("=" * 60)
    log("")
    
    # Step 1: Read HTML file
    log(f"Step 1: Reading {HTML_FILE.name}...")
    with open(HTML_FILE, 'r', encoding='utf-8', errors='ignore') as f:
        html_content = f.read()
    log(f"  File size: {len(html_content):,} characters")
    
    # Step 2: Extract URLs
    log("")
    log("Step 2: Extracting LinkedIn URLs...")
    urls = extract_linkedin_urls(html_content)
    log(f"  Extracted: {len(urls)} unique URLs")
    
    if not urls:
        log("  ERROR: No URLs found!")
        return
    
    # Step 3: Create/get client
    log("")
    log(f"Step 3: Creating client '{CLIENT_NAME}'...")
    client_id = get_or_create_client(CLIENT_NAME)
    log(f"  Client ID: {client_id}")
    
    # Step 4: Create batch
    log("")
    log("Step 4: Creating batch...")
    batch_id = create_batch(client_id, HTML_FILE.name, len(urls))
    log(f"  Batch ID: {batch_id}")
    
    # Step 5: Create leads
    log("")
    log("Step 5: Creating leads...")
    created, duplicates = await create_leads_from_urls(client_id, batch_id, urls)
    log(f"  Created: {created}")
    log(f"  Duplicates skipped: {duplicates}")
    
    # Step 6: Update batch status
    log("")
    log("Step 6: Updating batch status...")
    supabase.table("batches").update({
        "total_leads": created,
        "status": "ready"
    }).eq("id", batch_id).execute()
    log("  Status: ready")
    
    # Step 7: Verify in database
    log("")
    log("Step 7: Verifying in Supabase...")
    leads_result = supabase.table("leads").select("id, linkedin_url, status").eq("batch_id", batch_id).limit(5).execute()
    log(f"  Leads in database: {len(leads_result.data)} (showing first 5)")
    for lead in leads_result.data[:5]:
        log(f"    - {lead['linkedin_url'][:60]}... [{lead['status']}]")
    
    # Summary
    log("")
    log("=" * 60)
    log("SUMMARY")
    log("=" * 60)
    log(f"Client: {CLIENT_NAME} ({client_id[:8]}...)")
    log(f"Batch: {batch_id[:8]}...")
    log(f"Leads created: {created}")
    log(f"Status: ready for enrichment")
    log("")
    log("✓ Phase 2 test PASSED!")
    
    # Write output
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))
    
    log(f"\nResults saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
