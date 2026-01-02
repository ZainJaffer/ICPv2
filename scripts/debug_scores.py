"""Debug why scores are so low."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(".env.local")

from app.services.db.supabase_client import supabase
from app.services.matching.embeddings import create_profile_text
from app.services.matching.reranker import get_reranker
from app.services.matching.icp_matcher import expand_icp

print("="*60)
print("DEBUGGING SCORES")
print("="*60)

# Get ICP
icps = supabase.table("client_icps").select("*").execute()
icp = icps.data[0] if icps.data else {}

print("\nICP:")
print(f"  Target titles: {icp.get('target_titles')}")
print(f"  Target industries: {icp.get('target_industries')}")

# Expand ICP
expanded_icp = expand_icp(icp)
print(f"\nExpanded ICP (query for reranker):")
print(f"  {expanded_icp}")

# Get leads
leads = supabase.table("leads").select("*").eq("status", "qualified").execute()

print("\n" + "-"*60)
print("PROFILE TEXTS (what reranker sees):")
print("-"*60)

documents = []
lead_names = []

for lead in leads.data:
    profile_text = create_profile_text(lead)
    documents.append(profile_text)
    lead_names.append(lead.get("name", "Unknown"))
    print(f"\n{lead.get('name')}:")
    print(f"  {profile_text[:300]}...")

# Rerank
print("\n" + "-"*60)
print("RERANKER SCORES:")
print("-"*60)

reranker = get_reranker("jina")
results = reranker.rerank(
    query=expanded_icp,
    documents=documents
)

for result in results:
    idx = result.index
    name = lead_names[idx] if idx < len(lead_names) else "Unknown"
    print(f"  {name}: {result.score:.4f} (x100 = {int(result.score * 100)})")
