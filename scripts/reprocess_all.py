"""
Re-extract, regenerate embeddings, and re-qualify all leads.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(".env.local")

import asyncio
from app.services.db.supabase_client import supabase
from app.services.enrichment import extract_profile_fields
from app.services.matching.embeddings import generate_profile_embedding, format_embedding_for_postgres, create_profile_text
from app.services.matching.classifier import classify_profile
from app.services.matching.icp_matcher import qualify_batch

async def main():
    print("="*60)
    print("REPROCESSING ALL LEADS")
    print("="*60)
    
    # Get all leads
    leads = supabase.table("leads").select("*").in_("status", ["enriched", "qualified"]).execute()
    print(f"\nFound {len(leads.data)} leads to reprocess")
    
    # Step 1: Re-extract and update
    print("\n" + "-"*60)
    print("STEP 1: Re-extracting profile fields...")
    print("-"*60)
    
    for lead in leads.data:
        lead_id = lead["id"]
        name = lead.get("name", "Unknown")
        profile_data = lead.get("profile_data") or {}
        
        # Re-extract with fixed logic
        fields = extract_profile_fields(profile_data)
        
        # Build lead for embedding
        lead_for_embedding = {
            **lead,
            "profile_data": profile_data,
            "name": fields.get("name") or lead.get("name"),
            "headline": fields.get("headline") or lead.get("headline"),
            "company": fields.get("company") or lead.get("company"),
            "location": fields.get("location") or lead.get("location"),
            "current_job_titles": fields.get("current_job_titles"),
            "industry": lead.get("industry"),
        }
        
        # Generate new embedding
        embedding = generate_profile_embedding(lead_for_embedding)
        
        print(f"\n{name}:")
        print(f"  Titles: {fields.get('current_job_titles')}")
        print(f"  Company: {fields.get('company')}")
        
        # Update database
        update_data = {
            "current_job_titles": fields.get("current_job_titles"),
            "company": fields.get("company"),
            "status": "enriched"  # Reset for re-qualification
        }
        
        if embedding:
            update_data["embedding"] = format_embedding_for_postgres(embedding)
            print(f"  Embedding: Generated")
        
        supabase.table("leads").update(update_data).eq("id", lead_id).execute()
    
    # Step 2: Re-qualify
    print("\n" + "-"*60)
    print("STEP 2: Re-qualifying leads...")
    print("-"*60)
    
    batches = supabase.table("batches").select("id").execute()
    batch_id = batches.data[0]["id"] if batches.data else None
    
    icps = supabase.table("client_icps").select("*").execute()
    icp = icps.data[0] if icps.data else {}
    
    if batch_id and icp:
        result = await qualify_batch(batch_id, icp)
        print(f"\nQualification result: {result}")
    
    # Step 3: Show results
    print("\n" + "-"*60)
    print("STEP 3: Final Results")
    print("-"*60)
    
    qualified = supabase.table("leads").select("*").eq("status", "qualified").order("icp_score", desc=True).execute()
    
    for i, lead in enumerate(qualified.data):
        titles = lead.get("current_job_titles") or []
        title_str = ", ".join(titles[:2]) if titles else "Unknown"
        print(f"\n{i+1}. {lead.get('name')} - Score: {lead.get('icp_score')}/100")
        print(f"   Titles: {title_str}")
        print(f"   Company: {lead.get('company')}")
        print(f"   Industry: {lead.get('industry')}")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    asyncio.run(main())
