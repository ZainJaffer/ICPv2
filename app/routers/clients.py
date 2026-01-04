"""
Clients Router - Manage clients and their ICPs

Endpoints:
- POST /clients - Create new client
- GET /clients - List all clients
- GET /clients/{id} - Get client details
- POST /clients/{id}/ingest - Upload HTML file to extract leads
- POST /clients/{id}/sync-icp - Sync ICP from Fathom (Phase 6)
"""

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List

from ..services.db.supabase_client import supabase
from ..services.scraping.html_parser import extract_linkedin_urls
from ..services.enrichment import create_leads_from_urls

router = APIRouter()


# ============================================
# Pydantic Models
# ============================================

class ClientCreate(BaseModel):
    name: str


class ClientResponse(BaseModel):
    id: str
    name: str
    created_at: str


class ICPUpdate(BaseModel):
    target_titles: Optional[List[str]] = None
    target_industries: Optional[List[str]] = None
    company_sizes: Optional[List[str]] = None
    target_keywords: Optional[List[str]] = None
    exclude_titles: Optional[List[str]] = None
    notes: Optional[str] = None


class IngestResponse(BaseModel):
    batch_id: str
    leads_created: int
    duplicates_skipped: int


# ============================================
# Endpoints
# ============================================

@router.post("", response_model=ClientResponse)
async def create_client(client: ClientCreate):
    """Create a new client."""
    try:
        result = supabase.table("clients").insert({
            "name": client.name
        }).execute()
        
        if result.data and len(result.data) > 0:
            created = result.data[0]
            
            # Also create empty ICP record
            supabase.table("client_icps").insert({
                "client_id": created["id"]
            }).execute()
            
            return ClientResponse(
                id=created["id"],
                name=created["name"],
                created_at=created["created_at"]
            )
        
        raise HTTPException(status_code=500, detail="Failed to create client")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_clients():
    """List all clients."""
    try:
        result = supabase.table("clients").select("*").order("created_at", desc=True).execute()
        return {"clients": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{client_id}")
async def get_client(client_id: str):
    """Get client details including ICP."""
    try:
        # Get client
        client_result = supabase.table("clients").select("*").eq("id", client_id).execute()
        
        if not client_result.data:
            raise HTTPException(status_code=404, detail="Client not found")
        
        client = client_result.data[0]
        
        # Get ICP
        icp_result = supabase.table("client_icps").select("*").eq("client_id", client_id).execute()
        icp = icp_result.data[0] if icp_result.data else None
        
        # Get batch count
        batch_result = supabase.table("batches").select("id").eq("client_id", client_id).execute()
        
        return {
            "client": client,
            "icp": icp,
            "batch_count": len(batch_result.data) if batch_result.data else 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _upsert_icp(client_id: str, icp: ICPUpdate):
    """Create/update client's ICP criteria (upsert)."""
    try:
        # Verify client exists
        client_result = supabase.table("clients").select("id").eq("id", client_id).execute()
        if not client_result.data:
            raise HTTPException(status_code=404, detail="Client not found")
        
        # Build update data (only include non-None fields)
        update_data = {}
        if icp.target_titles is not None:
            update_data["target_titles"] = icp.target_titles
        if icp.target_industries is not None:
            update_data["target_industries"] = icp.target_industries
        if icp.company_sizes is not None:
            update_data["company_sizes"] = icp.company_sizes
        if icp.target_keywords is not None:
            update_data["target_keywords"] = icp.target_keywords
        if icp.exclude_titles is not None:
            update_data["exclude_titles"] = icp.exclude_titles
        if icp.notes is not None:
            update_data["notes"] = icp.notes
        
        if update_data:
            payload = {"client_id": client_id, **update_data}
            # Upsert on client_id so this works even if the ICP row doesn't exist yet
            result = supabase.table("client_icps").upsert(payload, on_conflict="client_id").execute()
            return {"status": "updated", "icp": result.data[0] if result.data else None}
        
        return {"status": "no_changes"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{client_id}/icp")
async def upsert_icp_post(client_id: str, icp: ICPUpdate):
    """Upsert client's ICP criteria (preferred)."""
    return await _upsert_icp(client_id, icp)


@router.put("/{client_id}/icp")
async def upsert_icp_put(client_id: str, icp: ICPUpdate):
    """Upsert client's ICP criteria (alias for PUT)."""
    return await _upsert_icp(client_id, icp)


@router.post("/{client_id}/ingest", response_model=IngestResponse)
async def ingest_html(client_id: str, file: UploadFile = File(...)):
    """
    Upload LinkedIn followers HTML file and extract leads.
    
    Creates a new batch and extracts LinkedIn URLs from the uploaded HTML.
    """
    try:
        # Verify client exists
        client_result = supabase.table("clients").select("id").eq("id", client_id).execute()
        if not client_result.data:
            raise HTTPException(status_code=404, detail="Client not found")
        
        # Read file content
        content = await file.read()
        html_content = content.decode('utf-8', errors='ignore')
        
        # Extract LinkedIn URLs
        urls = extract_linkedin_urls(html_content)
        
        if not urls:
            raise HTTPException(status_code=400, detail="No LinkedIn URLs found in file")
        
        # Create batch
        batch_result = supabase.table("batches").insert({
            "client_id": client_id,
            "filename": file.filename,
            "status": "processing",
            "total_leads": len(urls)
        }).execute()
        
        if not batch_result.data:
            raise HTTPException(status_code=500, detail="Failed to create batch")
        
        batch_id = batch_result.data[0]["id"]
        
        # Create leads
        created, duplicates = await create_leads_from_urls(client_id, batch_id, urls)
        
        # Update batch with actual counts
        supabase.table("batches").update({
            "total_leads": created,
            "status": "ready"
        }).eq("id", batch_id).execute()
        
        return IngestResponse(
            batch_id=batch_id,
            leads_created=created,
            duplicates_skipped=duplicates
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{client_id}/sync-icp")
async def sync_icp_from_fathom(client_id: str):
    """
    Sync ICP from Fathom call transcripts.
    
    Phase 6 - Not yet implemented.
    """
    raise HTTPException(
        status_code=501, 
        detail="Fathom ICP sync not yet implemented (Phase 6)"
    )
