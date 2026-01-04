"""
Set up LangSmith evals for ICP matching.

Creates test cases with known good/bad matches:
- Good matches: CMO, Head of Marketing, VP Marketing at tech companies
- Bad matches: Non-marketing roles, wrong industries
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(".env.local")

from app.services.db.supabase_client import supabase
from app.services.matching.icp_matcher import qualify_batch

# Get Allison's ICP
client_result = supabase.table("clients").select("id").eq("name", "Allison Gates").execute()
if not client_result.data:
    print("ERROR: Allison Gates client not found!")
    exit(1)

client_id = client_result.data[0]["id"]
icp_result = supabase.table("client_icps").select("*").eq("client_id", client_id).execute()
icp = icp_result.data[0] if icp_result.data else None

if not icp:
    print("ERROR: ICP not found!")
    exit(1)

print("="*60)
print("LANGSMITH EVALS SETUP")
print("="*60)

print(f"\nICP Criteria:")
print(f"  Titles: {icp.get('target_titles')}")
print(f"  Industries: {icp.get('target_industries')}")

# Get qualified leads to create test cases
leads = supabase.table("leads").select("*").eq("batch_id", "97ac8489-4365-4d29-b5d0-66b18aa24f28").eq("status", "qualified").order("icp_score", desc=True).execute()

print(f"\nFound {len(leads.data)} qualified leads")

# Create test cases: top 10 (should be good), bottom 10 (should be bad)
test_cases = []

# Good matches (top scores)
print("\n" + "-"*60)
print("GOOD MATCHES (top 10 - should score 60+):")
print("-"*60)
for i, lead in enumerate(leads.data[:10], 1):
    titles = lead.get("current_job_titles") or []
    title_str = ", ".join(titles[:2]) if titles else "No titles"
    score = lead.get("icp_score", 0)
    test_cases.append({
        "lead_id": lead["id"],
        "name": lead.get("name"),
        "titles": title_str,
        "company": lead.get("company"),
        "industry": lead.get("industry"),
        "expected_score_min": 60,
        "expected_score_max": 100,
        "type": "good_match"
    })
    print(f"{i}. {lead.get('name')}: {title_str} | {lead.get('company')} | Score: {score}")

# Bad matches (bottom 10)
print("\n" + "-"*60)
print("BAD MATCHES (bottom 10 - should score <50):")
print("-"*60)
for i, lead in enumerate(leads.data[-10:], 1):
    titles = lead.get("current_job_titles") or []
    title_str = ", ".join(titles[:2]) if titles else "No titles"
    score = lead.get("icp_score", 0)
    test_cases.append({
        "lead_id": lead["id"],
        "name": lead.get("name"),
        "titles": title_str,
        "company": lead.get("company"),
        "industry": lead.get("industry"),
        "expected_score_min": 0,
        "expected_score_max": 50,
        "type": "bad_match"
    })
    print(f"{i}. {lead.get('name')}: {title_str} | {lead.get('company')} | Score: {score}")

print(f"\n" + "="*60)
print(f"Created {len(test_cases)} test cases")
print(f"="*60)
print(f"\nNext: Run evals with:")
print(f"  python scripts/run_evals.py")
