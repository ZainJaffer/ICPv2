"""
Enrichment Service - Scrape and cache LinkedIn profile data.

Handles:
- Creating leads from extracted URLs
- Batch enrichment with cache checking
- Profile data extraction and storage
"""

from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime

from .db.supabase_client import supabase
from .scraping.apify_scraper import scraper, normalize_linkedin_url, extract_urn_from_url
from .matching.embeddings import generate_profile_embedding, format_embedding_for_postgres
from .matching.classifier import classify_profile


async def create_leads_from_urls(
    client_id: str, 
    batch_id: str, 
    urls: List[str]
) -> Tuple[int, int]:
    """
    Create lead records from a list of LinkedIn URLs.
    
    Args:
        client_id: The client ID
        batch_id: The batch ID
        urls: List of LinkedIn profile URLs
    
    Returns:
        Tuple of (created_count, duplicate_count)
    """
    created = 0
    duplicates = 0
    
    for url in urls:
        normalized_url = normalize_linkedin_url(url)
        public_id = extract_urn_from_url(url)
        
        try:
            lead_data = {
                "client_id": client_id,
                "batch_id": batch_id,
                "linkedin_url": normalized_url,
                "public_identifier": public_id,
                "status": "discovered"
            }
            
            supabase.table("leads").insert(lead_data).execute()
            created += 1
            
        except Exception as e:
            error_str = str(e).lower()
            # Check for duplicate key error
            if "duplicate" in error_str or "unique" in error_str or "23505" in error_str:
                duplicates += 1
            else:
                print(f"[Enrichment] Error creating lead for {url}: {e}")
    
    print(f"[Enrichment] Created {created} leads, {duplicates} duplicates skipped")
    return created, duplicates


def extract_profile_fields(profile_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract key fields from raw profile data for the leads table.
    
    Args:
        profile_data: Raw profile JSON from Apify
    
    Returns:
        Dict with extracted fields
    """
    if not profile_data:
        return {}
    
    # Build name from first/last
    first_name = profile_data.get("firstName", "").strip()
    last_name = profile_data.get("lastName", "").strip()
    name = f"{first_name} {last_name}".strip() if (first_name or last_name) else None
    
    # Get headline
    headline = profile_data.get("headline")
    
    # Get company from first position or companyName field
    company = profile_data.get("companyName")
    if not company:
        positions = profile_data.get("positions", [])
        if positions and len(positions) > 0:
            company_obj = positions[0].get("company", {})
            if isinstance(company_obj, dict):
                company = company_obj.get("name")
            elif isinstance(company_obj, str):
                company = company_obj
    
    # Get location
    location = profile_data.get("geoLocationName") or profile_data.get("locationName")
    
    # Get follower count
    follower_count = profile_data.get("followerCount")
    
    return {
        "name": name,
        "headline": headline,
        "company": company,
        "location": location,
        "follower_count": follower_count
    }


async def enrich_lead(lead: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich a single lead by scraping their LinkedIn profile.
    
    Args:
        lead: Lead record from database
    
    Returns:
        Dict with enrichment result
    """
    lead_id = lead["id"]
    linkedin_url = lead["linkedin_url"]
    normalized_url = normalize_linkedin_url(linkedin_url)
    
    try:
        # Scrape profile using concurrent method (works for single URLs too)
        scrape_results = await scraper.scrape_profiles_concurrent([normalized_url])
        result = scrape_results.get(normalized_url, {})
        
        if not result.get("success"):
            # Update lead with error
            supabase.table("leads").update({
                "status": "failed",
                "error_message": result.get("error", "Unknown error"),
                "retry_count": lead.get("retry_count", 0) + 1
            }).eq("id", lead_id).execute()
            
            return {
                "lead_id": lead_id,
                "success": False,
                "error": result.get("error"),
                "from_cache": False
            }
        
        # Extract fields from profile data
        profile_data = result.get("profile_data", {})
        fields = extract_profile_fields(profile_data)
        
        # Update lead with enriched data
        update_data = {
            "status": "enriched",
            "profile_data": profile_data,
            "name": fields.get("name"),
            "headline": fields.get("headline"),
            "company": fields.get("company"),
            "location": fields.get("location"),
            "follower_count": fields.get("follower_count"),
            "scraped_at": datetime.utcnow().isoformat(),
            "error_message": None
        }
        
        supabase.table("leads").update(update_data).eq("id", lead_id).execute()
        
        return {
            "lead_id": lead_id,
            "success": True,
            "from_cache": result.get("from_cache", False)
        }
        
    except Exception as e:
        print(f"[Enrichment] Error enriching lead {lead_id}: {e}")
        
        supabase.table("leads").update({
            "status": "failed",
            "error_message": str(e),
            "retry_count": lead.get("retry_count", 0) + 1
        }).eq("id", lead_id).execute()
        
        return {
            "lead_id": lead_id,
            "success": False,
            "error": str(e),
            "from_cache": False
        }


async def enrich_batch(batch_id: str, limit: Optional[int] = None) -> Dict[str, int]:
    """
    Enrich discovered leads in a batch using batch scraping.
    
    Args:
        batch_id: The batch ID to process
        limit: Max leads to process (for testing)
    
    Returns:
        Dict with counts: enriched, from_cache, failed
    """
    print(f"\n{'='*60}", flush=True)
    print(f"[Enrichment] Starting batch: {batch_id}", flush=True)
    if limit:
        print(f"[Enrichment] Limit: {limit} profiles", flush=True)
    print(f"{'='*60}\n", flush=True)
    
    # Get discovered leads in batch
    print("[Step 1] Fetching discovered leads from Supabase...", flush=True)
    query = supabase.table("leads").select("*").eq("batch_id", batch_id).eq("status", "discovered")
    if limit:
        query = query.limit(limit)
    result = query.execute()
    
    leads = result.data or []
    print(f"[Step 1] Found {len(leads)} leads to process\n", flush=True)
    
    if not leads:
        return {"enriched": 0, "from_cache": 0, "failed": 0}
    
    # Build URL list and lead lookup
    urls = []
    lead_by_url = {}
    for lead in leads:
        url = normalize_linkedin_url(lead.get("linkedin_url", ""))
        urls.append(url)
        lead_by_url[url] = lead
    
    # Scrape with concurrent batching (20 actors × 5 URLs)
    print("[Step 2] Scraping profiles via Apify (concurrent mode)...", flush=True)
    scrape_results = await scraper.scrape_profiles_concurrent(urls)
    
    # Process results and update leads
    print("\n[Step 3] Updating leads in Supabase...", flush=True)
    enriched = 0
    from_cache = 0
    failed = 0
    
    for url, result in scrape_results.items():
        lead = lead_by_url.get(url)
        if not lead:
            continue
        
        lead_id = lead["id"]
        
        if result.get("success"):
            profile_data = result.get("profile_data", {})
            fields = extract_profile_fields(profile_data)
            
            # Build lead data for embedding
            lead_for_embedding = {
                **lead,
                "profile_data": profile_data,
                "name": fields.get("name"),
                "headline": fields.get("headline"),
                "company": fields.get("company"),
                "location": fields.get("location"),
            }
            
            # Generate embedding
            embedding = generate_profile_embedding(lead_for_embedding)
            
            # Classify profile (industry + company type)
            classification = classify_profile(lead_for_embedding)
            
            update_data = {
                "status": "enriched",
                "profile_data": profile_data,
                "name": fields.get("name"),
                "headline": fields.get("headline"),
                "company": fields.get("company"),
                "location": fields.get("location"),
                "follower_count": fields.get("follower_count"),
                "scraped_at": datetime.utcnow().isoformat(),
                "error_message": None
            }
            
            # Add embedding if generated successfully
            if embedding:
                update_data["embedding"] = format_embedding_for_postgres(embedding)
            
            # Add classification if successful
            if classification:
                update_data["industry"] = classification.get("industry")
                update_data["company_type"] = classification.get("company_type")
                update_data["industry_reasoning"] = classification.get("industry_reasoning")
                update_data["company_reasoning"] = classification.get("company_reasoning")
            
            supabase.table("leads").update(update_data).eq("id", lead_id).execute()
            
            if result.get("from_cache"):
                from_cache += 1
            else:
                enriched += 1
        else:
            supabase.table("leads").update({
                "status": "failed",
                "error_message": result.get("error", "Unknown error"),
                "retry_count": lead.get("retry_count", 0) + 1
            }).eq("id", lead_id).execute()
            failed += 1
    
    print(f"\n{'='*60}", flush=True)
    print(f"[Enrichment] COMPLETE", flush=True)
    print(f"  - Scraped: {enriched}", flush=True)
    print(f"  - From cache: {from_cache}", flush=True)
    print(f"  - Failed: {failed}", flush=True)
    print(f"{'='*60}\n", flush=True)
    
    return {
        "enriched": enriched,
        "from_cache": from_cache,
        "failed": failed
    }


async def retry_failed_leads(batch_id: str, max_retries: int = 3) -> Dict[str, int]:
    """
    Retry enrichment for failed leads that haven't exceeded retry limit.
    
    Args:
        batch_id: The batch ID to process
        max_retries: Maximum retry attempts
    
    Returns:
        Dict with counts
    """
    # Get failed leads that haven't exceeded retry limit
    result = supabase.table("leads").select("*").eq("batch_id", batch_id).eq("status", "failed").lt("retry_count", max_retries).execute()
    
    leads = result.data or []
    print(f"[Enrichment] Retrying {len(leads)} failed leads in batch {batch_id}")
    
    # Reset status to discovered so they can be re-enriched
    for lead in leads:
        supabase.table("leads").update({"status": "discovered"}).eq("id", lead["id"]).execute()
    
    # Run enrichment
    return await enrich_batch(batch_id)
