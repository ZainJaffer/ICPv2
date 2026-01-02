"""Show qualified leads with scores."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(".env.local")

from app.services.db.supabase_client import supabase

leads = supabase.table("leads").select("name, current_job_titles, company, industry, icp_score, match_reasoning").eq("status", "qualified").order("icp_score", desc=True).execute()

print("QUALIFIED LEADS (sorted by score):")
print("="*60)
for i, lead in enumerate(leads.data):
    titles = lead.get("current_job_titles") or []
    title_str = ", ".join(titles[:2]) if titles else "Unknown"
    print(f"\n{i+1}. {lead.get('name')} - Score: {lead.get('icp_score')}/100")
    print(f"   Titles: {title_str}")
    print(f"   Company: {lead.get('company')}")
    print(f"   Industry: {lead.get('industry')}")
    print(f"   Reason: {lead.get('match_reasoning')}")
