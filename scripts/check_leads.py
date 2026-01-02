"""Reset failed leads back to discovered."""
import sys
sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv()

from app.services.supabase_client import supabase

batch_id = "541581b9-4b08-4b0b-b01f-94c175b60df5"

# Check current status
result = supabase.table("leads").select("status").eq("batch_id", batch_id).execute()
status_counts = {}
for lead in result.data:
    s = lead.get("status", "unknown")
    status_counts[s] = status_counts.get(s, 0) + 1

print(f"\n=== Current Status ===")
for status, count in sorted(status_counts.items()):
    print(f"  {status}: {count}")

# Reset failed leads
print(f"\n=== Resetting failed leads ===")
result = supabase.table("leads").update({
    "status": "discovered",
    "error_message": None,
    "retry_count": 0
}).eq("batch_id", batch_id).eq("status", "failed").execute()
print(f"Reset {len(result.data)} leads")

# Verify
result2 = supabase.table("leads").select("status").eq("batch_id", batch_id).execute()
status_counts2 = {}
for lead in result2.data:
    s = lead.get("status", "unknown")
    status_counts2[s] = status_counts2.get(s, 0) + 1

print(f"\n=== After Reset ===")
for status, count in sorted(status_counts2.items()):
    print(f"  {status}: {count}")
