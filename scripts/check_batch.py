"""Check batch status and sample leads."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(".env.local")

from app.services.db.supabase_client import supabase

batch_id = "97ac8489-4365-4d29-b5d0-66b18aa24f28"

print("="*60)
print(f"BATCH STATUS: {batch_id[:8]}...")
print("="*60)

batch_result = supabase.table("batches").select("*").eq("id", batch_id).execute()
batch = batch_result.data[0] if batch_result.data else None
if batch:
    print(f"\nStatus: {batch['status']}")
    print(f"Enriched: {batch.get('enriched_count', 0)}")
else:
    print("\nBatch not found!")
    exit(1)

leads = supabase.table("leads").select("name,status,company,current_job_titles").eq("batch_id", batch_id).limit(5).execute()

print(f"\nSample leads ({len(leads.data)} shown):")
for lead in leads.data:
    titles = lead.get("current_job_titles") or []
    title_str = ", ".join(titles[:2]) if titles else "No titles"
    print(f"  {lead['name']}: {lead['status']} | {lead.get('company', 'N/A')} | {title_str}")
