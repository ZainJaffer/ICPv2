"""
Enrichment Service - Scrape and cache LinkedIn profile data.

Handles:
- Creating leads from extracted URLs
- Batch enrichment with cache checking
- Profile data extraction and storage
"""

from typing import List, Tuple, Dict, Any
from datetime import datetime

from .supabase_client import supabase
from .apify_scraper import scraper, normalize_linkedin_url, extract_public_identifier


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
        public_id = extract_public_identifier(url)
        
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
    
    try:
        # Scrape profile (checks cache internally)
        result = await scraper.scrape_profile(linkedin_url)
        
        if not result["success"]:
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


async def enrich_batch(batch_id: str) -> Dict[str, int]:
    """
    Enrich all discovered leads in a batch.
    
    Args:
        batch_id: The batch ID to process
    
    Returns:
        Dict with counts: enriched, from_cache, failed
    """
    # Get all discovered leads in batch
    result = supabase.table("leads").select("*").eq("batch_id", batch_id).eq("status", "discovered").execute()
    
    leads = result.data or []
    print(f"[Enrichment] Processing {len(leads)} leads in batch {batch_id}")
    
    enriched = 0
    from_cache = 0
    failed = 0
    
    for lead in leads:
        result = await enrich_lead(lead)
        
        if result["success"]:
            if result.get("from_cache"):
                from_cache += 1
            else:
                enriched += 1
        else:
            failed += 1
    
    print(f"[Enrichment] Batch complete: {enriched} enriched, {from_cache} from cache, {failed} failed")
    
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
