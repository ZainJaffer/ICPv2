"""Fix company names for qualified leads."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(".env.local")

from app.services.db.supabase_client import supabase
from app.services.enrichment import extract_profile_fields

# Get all leads (enriched or qualified)
leads = supabase.table("leads").select("id, name, profile_data, company").in_("status", ["enriched", "qualified"]).execute()
print(f"Found {len(leads.data)} leads to check")

fixed = 0
for lead in leads.data:
    profile_data = lead.get("profile_data") or {}
    fields = extract_profile_fields(profile_data)
    new_company = fields.get("company")
    old_company = lead.get("company")
    
    if new_company != old_company:
        print(f"  {lead['name']}: '{old_company}' -> '{new_company}'")
        supabase.table("leads").update({"company": new_company}).eq("id", lead["id"]).execute()
        fixed += 1

print(f"\nFixed {fixed} leads")
