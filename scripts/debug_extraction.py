"""Debug the job title extraction issue."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(".env.local")

from app.services.db.supabase_client import supabase
from app.services.enrichment import extract_profile_fields

print("="*60)
print("DEBUGGING JOB TITLE EXTRACTION")
print("="*60)

leads = supabase.table("leads").select("name,current_job_titles,company,profile_data").eq("status", "qualified").execute()

for lead in leads.data:
    print(f"\n{'='*60}")
    print(f"NAME: {lead['name']}")
    print(f"CURRENT (stored): titles={lead.get('current_job_titles')}, company={lead.get('company')}")
    
    profile_data = lead.get("profile_data", {}) or {}
    positions = profile_data.get("positions", [])
    
    print(f"\nRAW POSITIONS ({len(positions)} total):")
    for i, pos in enumerate(positions[:4]):
        title = pos.get("title")
        company = pos.get("company")
        time_period = pos.get("timePeriod", {}) or {}
        end_date = time_period.get("endDate")
        is_current = "CURRENT" if end_date is None else f"ended {end_date}"
        print(f"  [{i}] title='{title}' | company={company} | {is_current}")
    
    # Re-extract to see what we'd get now
    re_extracted = extract_profile_fields(profile_data)
    print(f"\nRE-EXTRACTED: titles={re_extracted.get('current_job_titles')}, company={re_extracted.get('company')}")
    
    if re_extracted.get('current_job_titles') != lead.get('current_job_titles'):
        print("  ^ MISMATCH - extraction logic may have changed")
