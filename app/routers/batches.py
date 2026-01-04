"""
Batches Router - Manage batch operations

Endpoints:
- GET /batches/{id} - Get batch status
- POST /batches/{id}/enrich - Scrape profiles for batch
- POST /batches/{id}/qualify - Score profiles against ICP
- GET /batches/{id}/export - Download qualified leads CSV
"""

import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import csv
import io

from ..services.db.supabase_client import supabase
from ..services.enrichment import enrich_batch
from ..services.matching.icp_matcher import qualify_batch

router = APIRouter()

_RUNNING_TASKS: set[asyncio.Task] = set()


# ============================================
# Pydantic Models
# ============================================

class BatchStatus(BaseModel):
    id: str
    client_id: str
    filename: Optional[str]
    status: str
    total_leads: int
    enriched_count: int
    qualified_count: int
    exported_count: int
    failed_count: int
    created_at: str
    completed_at: Optional[str]


class EnrichResponse(BaseModel):
    batch_id: str
    status: str
    enriched: int
    from_cache: int
    failed: int


class QualifyResponse(BaseModel):
    batch_id: str
    status: str
    qualified: int
    failed: int


class RunResponse(BaseModel):
    batch_id: str
    status: str
    message: str


# ============================================
# Endpoints
# ============================================

async def _enrich_worker(batch_id: str, limit: Optional[int] = None) -> None:
    try:
        supabase.table("batches").update({"status": "enriching"}).eq("id", batch_id).execute()
        result = await enrich_batch(batch_id, limit=limit)
        supabase.table("batches").update({
            "status": "enriched",
            "enriched_count": result["enriched"] + result["from_cache"],
            "failed_count": result["failed"],
        }).eq("id", batch_id).execute()
    except Exception as e:
        # Best-effort error status
        try:
            supabase.table("batches").update({"status": "failed"}).eq("id", batch_id).execute()
        except Exception:
            pass
        print(f"[Batches] Enrich worker failed for {batch_id}: {e}", flush=True)


async def _qualify_worker(batch_id: str) -> None:
    try:
        batch_result = supabase.table("batches").select("*").eq("id", batch_id).execute()
        if not batch_result.data:
            return
        batch = batch_result.data[0]
        client_id = batch["client_id"]

        icp_result = supabase.table("client_icps").select("*").eq("client_id", client_id).execute()
        if not icp_result.data:
            supabase.table("batches").update({"status": "failed"}).eq("id", batch_id).execute()
            return
        icp = icp_result.data[0]

        supabase.table("batches").update({"status": "qualifying"}).eq("id", batch_id).execute()
        result = await qualify_batch(batch_id, icp)
        supabase.table("batches").update({
            "status": "qualified",
            "qualified_count": result["qualified"],
            "failed_count": (batch.get("failed_count") or 0) + result["failed"],
        }).eq("id", batch_id).execute()
    except Exception as e:
        try:
            supabase.table("batches").update({"status": "failed"}).eq("id", batch_id).execute()
        except Exception:
            pass
        print(f"[Batches] Qualify worker failed for {batch_id}: {e}", flush=True)


async def _run_worker(batch_id: str, limit: Optional[int] = None) -> None:
    # Run end-to-end: enrich -> qualify
    try:
        supabase.table("batches").update({"status": "running"}).eq("id", batch_id).execute()
        await _enrich_worker(batch_id, limit=limit)
        await _qualify_worker(batch_id)
    except Exception as e:
        try:
            supabase.table("batches").update({"status": "failed"}).eq("id", batch_id).execute()
        except Exception:
            pass
        print(f"[Batches] Run worker failed for {batch_id}: {e}", flush=True)


def _start_background(coro: asyncio.coroutines) -> None:
    task = asyncio.create_task(coro)
    _RUNNING_TASKS.add(task)
    task.add_done_callback(lambda t: _RUNNING_TASKS.discard(t))

@router.get("/{batch_id}")
async def get_batch(batch_id: str):
    """Get batch status and lead summary."""
    try:
        # Get batch
        batch_result = supabase.table("batches").select("*").eq("id", batch_id).execute()
        
        if not batch_result.data:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        batch = batch_result.data[0]
        
        # Get lead counts by status
        leads_result = supabase.table("leads").select("status").eq("batch_id", batch_id).execute()
        
        status_counts = {
            "discovered": 0,
            "enriched": 0,
            "qualified": 0,
            "exported": 0,
            "failed": 0
        }
        
        for lead in leads_result.data:
            status = lead.get("status", "discovered")
            if status in status_counts:
                status_counts[status] += 1
        
        return {
            "batch": batch,
            "lead_counts": status_counts
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{batch_id}/enrich", response_model=EnrichResponse)
async def enrich_batch_endpoint(batch_id: str, limit: Optional[int] = None, background: bool = False):
    """
    Scrape LinkedIn profiles for discovered leads in batch.
    
    Args:
        limit: Max profiles to scrape (for testing). Omit to process all.
    """
    try:
        # Verify batch exists
        batch_result = supabase.table("batches").select("*").eq("id", batch_id).execute()
        
        if not batch_result.data:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        batch = batch_result.data[0]
        
        # Count leads to enrich
        leads_result = supabase.table("leads").select("id").eq("batch_id", batch_id).eq("status", "discovered").execute()
        
        if not leads_result.data:
            return EnrichResponse(
                batch_id=batch_id,
                status="no_leads",
                enriched=0,
                from_cache=0,
                failed=0
            )
        
        if background:
            _start_background(_enrich_worker(batch_id, limit=limit))
            return EnrichResponse(
                batch_id=batch_id,
                status="started",
                enriched=0,
                from_cache=0,
                failed=0,
            )

        await _enrich_worker(batch_id, limit=limit)
        # Re-fetch counts for response
        batch_result = supabase.table("batches").select("*").eq("id", batch_id).execute()
        batch = batch_result.data[0] if batch_result.data else {}
        return EnrichResponse(
            batch_id=batch_id,
            status="completed",
            enriched=int(batch.get("enriched_count") or 0),
            from_cache=0,
            failed=int(batch.get("failed_count") or 0),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{batch_id}/qualify", response_model=QualifyResponse)
async def qualify_batch_endpoint(batch_id: str, background: bool = False):
    """
    Score all enriched leads against client's ICP.
    """
    try:
        # Verify batch exists and get client_id
        batch_result = supabase.table("batches").select("*").eq("id", batch_id).execute()
        
        if not batch_result.data:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        batch = batch_result.data[0]
        client_id = batch["client_id"]
        
        # Get client's ICP
        icp_result = supabase.table("client_icps").select("*").eq("client_id", client_id).execute()
        
        if not icp_result.data:
            raise HTTPException(status_code=400, detail="Client has no ICP defined")
        
        icp = icp_result.data[0]
        
        # Check if ICP has any criteria
        has_criteria = (
            icp.get("target_titles") or 
            icp.get("target_industries") or 
            icp.get("company_sizes") or
            icp.get("target_keywords")
        )
        
        if not has_criteria:
            raise HTTPException(
                status_code=400, 
                detail="ICP has no criteria defined. Please update the client's ICP first."
            )
        
        # Count leads to qualify
        leads_result = supabase.table("leads").select("id").eq("batch_id", batch_id).eq("status", "enriched").execute()
        
        if not leads_result.data:
            return QualifyResponse(
                batch_id=batch_id,
                status="no_leads",
                qualified=0,
                failed=0
            )
        
        if background:
            _start_background(_qualify_worker(batch_id))
            return QualifyResponse(
                batch_id=batch_id,
                status="started",
                qualified=0,
                failed=0,
            )

        await _qualify_worker(batch_id)
        batch_result = supabase.table("batches").select("*").eq("id", batch_id).execute()
        batch = batch_result.data[0] if batch_result.data else {}
        return QualifyResponse(
            batch_id=batch_id,
            status="completed",
            qualified=int(batch.get("qualified_count") or 0),
            failed=int(batch.get("failed_count") or 0),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{batch_id}/export")
async def export_batch(batch_id: str, min_score: int = 0):
    """
    Export qualified leads as CSV.
    
    Args:
        min_score: Minimum ICP score to include (default: 0 = all qualified leads)
    """
    try:
        # Verify batch exists
        batch_result = supabase.table("batches").select("*").eq("id", batch_id).execute()
        
        if not batch_result.data:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        batch = batch_result.data[0]
        
        # Get qualified leads
        query = supabase.table("leads").select("*").eq("batch_id", batch_id).eq("status", "qualified")
        
        if min_score > 0:
            query = query.gte("icp_score", min_score)
        
        leads_result = query.order("icp_score", desc=True).execute()
        
        if not leads_result.data:
            raise HTTPException(status_code=404, detail="No qualified leads to export")
        
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "Name",
            "Profile URL",
            "Headline",
            "Company",
            "Location",
            "Job Title",
            "ICP Score",
            "Match Reasoning"
        ])
        
        # Data rows
        for lead in leads_result.data:
            writer.writerow([
                lead.get("name", ""),
                lead.get("linkedin_url", ""),
                lead.get("headline", ""),
                lead.get("company", ""),
                lead.get("location", ""),
                ", ".join(lead.get("current_job_titles") or []),
                lead.get("icp_score", ""),
                lead.get("match_reasoning", "")
            ])
        
        # Update leads to exported status
        lead_ids = [lead["id"] for lead in leads_result.data]
        for lead_id in lead_ids:
            supabase.table("leads").update({"status": "exported"}).eq("id", lead_id).execute()
        
        # Update batch
        supabase.table("batches").update({
            "status": "exported",
            "exported_count": len(lead_ids)
        }).eq("id", batch_id).execute()
        
        # Return CSV
        output.seek(0)
        filename = f"qualified_leads_{batch_id[:8]}.csv"
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{batch_id}/run", response_model=RunResponse)
async def run_batch_endpoint(batch_id: str, limit: Optional[int] = None, background: bool = True):
    """
    Run end-to-end: enrich then qualify.

    Use background=true to return immediately and poll with GET /batches/{id}.
    """
    try:
        batch_result = supabase.table("batches").select("*").eq("id", batch_id).execute()
        if not batch_result.data:
            raise HTTPException(status_code=404, detail="Batch not found")

        if background:
            _start_background(_run_worker(batch_id, limit=limit))
            return RunResponse(batch_id=batch_id, status="started", message="Batch run started. Poll GET /batches/{id}.")

        await _run_worker(batch_id, limit=limit)
        return RunResponse(batch_id=batch_id, status="completed", message="Batch run completed.")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{batch_id}/leads")
async def list_batch_leads(batch_id: str, status: Optional[str] = None, limit: Optional[int] = None):
    """
    List leads in a batch with optional status filter.
    
    Args:
        batch_id: The batch ID
        status: Optional status filter (discovered, enriched, qualified, etc.)
        limit: Optional limit on results (default: return ALL leads)
    """
    try:
        query = supabase.table("leads").select("*").eq("batch_id", batch_id)
        
        if status:
            query = query.eq("status", status)
        
        query = query.order("icp_score", desc=True)
        
        if limit:
            query = query.limit(limit)
        
        result = query.execute()
        
        return {
            "leads": result.data,
            "count": len(result.data)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
