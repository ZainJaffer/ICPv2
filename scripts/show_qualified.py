"""Show top qualified leads for Allison's batch."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(".env.local")

from app.services.db.supabase_client import supabase

batch_id = "97ac8489-4365-4d29-b5d0-66b18aa24f28"

print("="*60)
print("TOP QUALIFIED LEADS (Allison Gates - Marketing ICP)")
print("="*60)

leads = supabase.table("leads").select("name,headline,company,current_job_titles,industry,icp_score,match_reasoning").eq("batch_id", batch_id).eq("status", "qualified").order("icp_score", desc=True).limit(10).execute()

print(f"\nShowing top {len(leads.data)} of 50:\n")

for i, lead in enumerate(leads.data, 1):
    titles = lead.get("current_job_titles") or []
    title_str = ", ".join(titles[:2]) if titles else "No titles"
    print(f"{i}. {lead['name']} - Score: {lead.get('icp_score', 'N/A')}/100")
    print(f"   Titles: {title_str}")
    print(f"   Company: {lead.get('company', 'N/A')}")
    print(f"   Industry: {lead.get('industry', 'N/A')}")
    reasoning = lead.get('match_reasoning', '')[:100]
    if reasoning:
        print(f"   Reason: {reasoning}...")
    print()
