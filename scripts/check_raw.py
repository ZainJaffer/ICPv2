"""Check raw profile data to debug company extraction."""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(".env.local")

from app.services.db.supabase_client import supabase

# Get the lead with "8 yrs 1 mo" company
leads = supabase.table("leads").select("id, name, company, profile_data").eq("name", "Chris Meringolo").execute()

if leads.data:
    lead = leads.data[0]
    print(f"Name: {lead['name']}")
    print(f"Company field: {lead['company']}")
    print()
    
    profile_data = lead.get("profile_data") or {}
    print(f"companyName: {profile_data.get('companyName')}")
    print()
    
    positions = profile_data.get("positions", [])
    print(f"Positions ({len(positions)}):")
    for i, pos in enumerate(positions[:3]):
        print(f"\n  Position {i+1}:")
        print(f"    title: {pos.get('title')}")
        print(f"    company: {pos.get('company')}")
        time_period = pos.get("timePeriod", {})
        print(f"    timePeriod: {time_period}")
