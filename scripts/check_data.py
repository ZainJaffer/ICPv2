"""Check existing data in Supabase for testing."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(".env.local")

from app.services.db.supabase_client import supabase

print("="*60)
print("Checking Supabase data...")
print("="*60)

# Check clients
clients = supabase.table("clients").select("id, name").execute()
print(f"\nCLIENTS ({len(clients.data)}):")
for c in clients.data:
    print(f"  {c['id'][:8]}... - {c['name']}")

# Check batches with lead counts
batches = supabase.table("batches").select("id, client_id, status").execute()
print(f"\nBATCHES ({len(batches.data)}):")
for b in batches.data:
    discovered = supabase.table("leads").select("id").eq("batch_id", b["id"]).eq("status", "discovered").execute()
    enriched = supabase.table("leads").select("id").eq("batch_id", b["id"]).eq("status", "enriched").execute()
    qualified = supabase.table("leads").select("id").eq("batch_id", b["id"]).eq("status", "qualified").execute()
    print(f"  {b['id'][:8]}... - discovered:{len(discovered.data)} enriched:{len(enriched.data)} qualified:{len(qualified.data)}")

# Check ICPs
icps = supabase.table("client_icps").select("*").execute()
print(f"\nICPs ({len(icps.data)}):")
for icp in icps.data:
    print(f"  Client {icp['client_id'][:8]}...")
    print(f"    target_titles: {icp.get('target_titles')}")
    print(f"    target_industries: {icp.get('target_industries')}")
    print(f"    company_sizes: {icp.get('company_sizes')}")

print("\n" + "="*60)
