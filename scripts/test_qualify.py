"""
Test the qualification pipeline with existing enriched leads.
"""

import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(".env.local")

from app.services.db.supabase_client import supabase
from app.services.matching.icp_matcher import qualify_batch

async def main():
    print("="*60)
    print("QUALIFICATION PIPELINE TEST")
    print("="*60)
    
    # Get client and batch
    clients = supabase.table("clients").select("id, name").execute()
    if not clients.data:
        print("ERROR: No clients found.")
        return
    
    client = clients.data[0]
    client_id = client["id"]
    print(f"\nClient: {client['name']}")
    
    batches = supabase.table("batches").select("id, status").eq("client_id", client_id).execute()
    if not batches.data:
        print("ERROR: No batches found.")
        return
    
    batch = batches.data[0]
    batch_id = batch["id"]
    print(f"Batch: {batch_id[:8]}...")
    
    # Step 1: Set up ICP
    print("\n" + "-"*60)
    print("STEP 1: Setting up ICP...")
    print("-"*60)
    
    icp_data = {
        "client_id": client_id,
        "target_titles": ["CEO", "Founder", "CTO", "VP Engineering", "Head of Product", "Director"],
        "target_industries": ["SaaS", "AI", "Technology", "Software", "Fintech"],
        "company_sizes": ["startup", "scaleup", "mid-market"],
        "target_keywords": ["B2B", "enterprise", "growth"],
        "notes": "Looking for tech executives at growing companies"
    }
    
    # Upsert ICP
    existing = supabase.table("client_icps").select("id").eq("client_id", client_id).execute()
    if existing.data:
        supabase.table("client_icps").update(icp_data).eq("client_id", client_id).execute()
        print("Updated existing ICP")
    else:
        supabase.table("client_icps").insert(icp_data).execute()
        print("Created new ICP")
    
    print(f"  Target titles: {icp_data['target_titles']}")
    print(f"  Target industries: {icp_data['target_industries']}")
    
    # Step 2: Check enriched leads
    print("\n" + "-"*60)
    print("STEP 2: Checking enriched leads...")
    print("-"*60)
    
    enriched = supabase.table("leads").select("*").eq("batch_id", batch_id).eq("status", "enriched").execute()
    print(f"  Found {len(enriched.data)} enriched leads")
    
    if not enriched.data:
        print("ERROR: No enriched leads to qualify. Run enrichment first.")
        return
    
    # Show the leads we're about to qualify
    print("\nLeads to qualify:")
    for lead in enriched.data:
        titles = lead.get("current_job_titles") or []
        print(f"  - {lead.get('name', 'Unknown')}: {', '.join(titles) if titles else 'No title'}")
    
    # Step 3: Run qualification
    print("\n" + "-"*60)
    print(f"STEP 3: Qualifying {len(enriched.data)} leads...")
    print("-"*60)
    
    result = await qualify_batch(batch_id, icp_data)
    
    # Step 4: Show results
    print("\n" + "-"*60)
    print("STEP 4: Results")
    print("-"*60)
    
    qualified = supabase.table("leads").select("name, current_job_titles, company, industry, icp_score, match_reasoning").eq("batch_id", batch_id).eq("status", "qualified").order("icp_score", desc=True).execute()
    
    print(f"\nQualified leads (sorted by score):")
    print("-"*60)
    for i, lead in enumerate(qualified.data):
        titles = lead.get("current_job_titles") or []
        title_str = ", ".join(titles) if titles else "Unknown"
        print(f"\n{i+1}. {lead.get('name', 'Unknown')}")
        print(f"   Score: {lead.get('icp_score', 0)}/100")
        print(f"   Title: {title_str}")
        print(f"   Company: {lead.get('company', 'Unknown')}")
        print(f"   Industry: {lead.get('industry', 'Unknown')}")
        print(f"   Reason: {lead.get('match_reasoning', '')}")
    
    print("\n" + "="*60)
    print("TEST COMPLETE")
    print(f"Qualified: {result.get('qualified', 0)}, Failed: {result.get('failed', 0)}")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
