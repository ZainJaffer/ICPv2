"""
Fix existing enriched leads by adding embeddings and current_job_titles.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(".env.local")

from app.services.db.supabase_client import supabase
from app.services.enrichment import extract_profile_fields
from app.services.matching.embeddings import generate_profile_embedding, format_embedding_for_postgres
from app.services.matching.classifier import classify_profile

print("="*60)
print("Fixing enriched leads (adding embeddings + current_job_titles)")
print("="*60)

# Get enriched leads
leads = supabase.table("leads").select("*").eq("status", "enriched").execute()
print(f"\nFound {len(leads.data)} enriched leads")

for lead in leads.data:
    lead_id = lead["id"]
    name = lead.get("name", "Unknown")
    profile_data = lead.get("profile_data") or {}
    
    print(f"\nProcessing: {name}")
    
    # Re-extract fields (to get current_job_titles)
    fields = extract_profile_fields(profile_data)
    
    # Build lead data for embedding
    lead_for_embedding = {
        **lead,
        "profile_data": profile_data,
        "name": fields.get("name") or lead.get("name"),
        "headline": fields.get("headline") or lead.get("headline"),
        "company": fields.get("company") or lead.get("company"),
        "location": fields.get("location") or lead.get("location"),
        "current_job_titles": fields.get("current_job_titles"),
    }
    
    # Generate embedding
    embedding = generate_profile_embedding(lead_for_embedding)
    
    # Classify
    classification = classify_profile(lead_for_embedding)
    
    # Build update
    update_data = {
        "current_job_titles": fields.get("current_job_titles"),
    }
    
    if embedding:
        update_data["embedding"] = format_embedding_for_postgres(embedding)
        print(f"  + Generated embedding")
    
    if classification:
        update_data["industry"] = classification.get("industry")
        update_data["company_type"] = classification.get("company_type")
        update_data["industry_reasoning"] = classification.get("industry_reasoning")
        update_data["company_reasoning"] = classification.get("company_reasoning")
        print(f"  + Classified: {classification.get('industry')} / {classification.get('company_type')}")
    
    titles = fields.get("current_job_titles") or []
    print(f"  + Titles: {titles}")
    
    # Update
    supabase.table("leads").update(update_data).eq("id", lead_id).execute()
    print(f"  + Updated")

print("\n" + "="*60)
print("DONE - All leads now have embeddings")
print("="*60)
