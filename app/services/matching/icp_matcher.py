"""
ICP Matcher Service - Score LinkedIn profiles against client ICPs.

Architecture:
1. Build ICP text from raw criteria (no LLM expansion - preserves client intent)
2. Generate ICP embedding
3. Vector search to rank all leads by similarity
4. Rerank with Jina to filter bottom matches
5. Convert scores and update leads

Embeddings naturally handle synonyms (CFO ≈ Chief Financial Officer) so LLM
expansion is unnecessary and risks adding terms the client didn't ask for.
"""

import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from dotenv import load_dotenv

from ..db.supabase_client import supabase
from .embeddings import generate_embedding, create_profile_text, format_embedding_for_postgres
from .reranker import get_reranker

load_dotenv(".env.local")
load_dotenv()


# =============================================================================
# ICP Text Building (No LLM - Direct from criteria)
# =============================================================================

def build_icp_text(icp: Dict[str, Any]) -> str:
    """
    Build ICP text directly from criteria without LLM expansion.

    Embeddings naturally understand that CFO ≈ Chief Financial Officer,
    so we don't need to expand terms. This preserves client intent and
    avoids adding terms they didn't ask for (e.g., expanding CFO to VP Finance).
    """
    parts = []

    if icp.get("target_titles"):
        parts.append(f"Target titles: {', '.join(icp['target_titles'])}")

    if icp.get("target_industries"):
        parts.append(f"Industries: {', '.join(icp['target_industries'])}")

    if icp.get("company_sizes"):
        parts.append(f"Company sizes: {', '.join(icp['company_sizes'])}")

    if icp.get("target_keywords"):
        parts.append(f"Keywords: {', '.join(icp['target_keywords'])}")

    if icp.get("notes"):
        parts.append(f"Notes: {icp['notes']}")

    icp_text = " | ".join(parts) if parts else "General professional profile"
    print(f"[ICP Matcher] ICP text: {icp_text}")
    return icp_text


# =============================================================================
# Vector Search
# =============================================================================

def vector_search_leads(icp_embedding: List[float], batch_id: str) -> List[Dict[str, Any]]:
    """
    Search all leads in a batch by similarity to ICP embedding.
    
    Uses the match_leads() Postgres function with pgvector.
    Returns ALL leads, ranked by similarity.
    """
    try:
        embedding_str = format_embedding_for_postgres(icp_embedding)
        
        result = supabase.rpc(
            "match_leads",
            {
                "query_embedding": embedding_str,
                "match_batch_id": batch_id
            }
        ).execute()
        
        leads = result.data or []
        print(f"[ICP Matcher] Vector search returned {len(leads)} leads")
        return leads
        
    except Exception as e:
        print(f"[ICP Matcher] Vector search error: {e}")
        # Fallback: return all enriched leads without ranking
        result = supabase.table("leads").select("*").eq("batch_id", batch_id).eq("status", "enriched").execute()
        return result.data or []


# =============================================================================
# Scoring
# =============================================================================

def similarity_to_score(similarity: float) -> int:
    """
    Convert embedding similarity (0-1) to ICP score (0-100).
    
    Similarity scores from embeddings are typically in range 0.3-0.9.
    We normalize this to 0-100 for user-friendly display.
    """
    # Clamp to reasonable range
    similarity = max(0.0, min(1.0, similarity))
    
    # Linear mapping: 0.3 -> 0, 0.9 -> 100
    # Anything below 0.3 is very poor, above 0.9 is excellent
    if similarity < 0.3:
        return int(similarity / 0.3 * 30)  # 0-30
    elif similarity > 0.9:
        return 100
    else:
        # Map 0.3-0.9 to 30-100
        return int(30 + (similarity - 0.3) / 0.6 * 70)


def generate_match_reasoning(lead: Dict[str, Any], score: int, icp: Dict[str, Any]) -> str:
    """
    Generate a simple reasoning string for the match.
    
    For now, this is template-based. Could be LLM-enhanced later.
    """
    name = lead.get("name", "Unknown")
    titles = lead.get("current_job_titles") or []
    company = lead.get("company", "Unknown")
    industry = lead.get("industry", "Unknown")
    
    title_str = ", ".join(titles) if titles else "Unknown role"
    
    if score >= 80:
        return f"Strong match: {title_str} at {company} ({industry})"
    elif score >= 60:
        return f"Good match: {title_str} at {company} ({industry})"
    elif score >= 40:
        return f"Moderate match: {title_str} at {company}"
    else:
        return f"Low match: {title_str} at {company}"


# =============================================================================
# Main Qualification Flow
# =============================================================================

async def qualify_batch(batch_id: str, icp: Dict[str, Any]) -> Dict[str, int]:
    """
    Qualify all enriched leads in a batch using embeddings + reranker.

    Flow:
    1. Build ICP text from raw criteria (no LLM expansion)
    2. Generate ICP embedding
    3. Vector search to get all leads ranked by similarity
    4. Rerank with Jina to filter bottom matches
    5. Update all leads with scores

    Args:
        batch_id: The batch ID to process
        icp: ICP criteria from client_icps table

    Returns:
        Dict with counts: qualified, failed
    """
    print(f"\n{'='*60}")
    print(f"[ICP Matcher] Starting qualification for batch: {batch_id}")
    print(f"{'='*60}\n")

    # Step 1: Build ICP text (no LLM expansion - preserves client intent)
    print("[Step 1] Building ICP text from criteria...")
    icp_text = build_icp_text(icp)

    # Step 2: Generate ICP embedding
    print("[Step 2] Generating ICP embedding...")
    icp_embedding = generate_embedding(icp_text)
    
    if not icp_embedding:
        print("[ICP Matcher] Failed to generate ICP embedding")
        return {"qualified": 0, "failed": 0, "error": "Failed to generate ICP embedding"}
    
    # Step 3: Vector search
    print("[Step 3] Running vector search...")
    leads = vector_search_leads(icp_embedding, batch_id)
    
    if not leads:
        print("[ICP Matcher] No leads found for qualification")
        return {"qualified": 0, "failed": 0}
    
    # Step 4: Rerank with Jina
    print(f"[Step 4] Reranking {len(leads)} leads with Jina...")
    
    try:
        reranker = get_reranker("jina")
        
        # Prepare documents for reranker (profile text summaries)
        documents = []
        lead_ids = []
        for lead in leads:
            # Create a text summary for reranking
            profile_text = create_profile_text(lead)
            documents.append(profile_text)
            lead_ids.append(lead["id"])
        
        # Rerank (returns ALL leads, no limit)
        reranked = reranker.rerank(
            query=icp_text,
            documents=documents,
            lead_ids=lead_ids
        )
        
        # Build lookup from reranked results
        raw_scores = {}
        for result in reranked:
            if result.lead_id:
                raw_scores[result.lead_id] = result.score
        
        # Normalize scores to a reasonable range (25-85)
        # Reranker scores are relative, not absolute, so we scale them
        if raw_scores:
            max_score = max(raw_scores.values())
            min_score = min(raw_scores.values())
            score_range = max_score - min_score if max_score > min_score else 1.0
            
            rerank_scores = {}
            for lead_id, raw in raw_scores.items():
                # Normalize to 0-1 within this batch
                normalized = (raw - min_score) / score_range if score_range > 0 else 0.5
                # Scale to 25-85 range (best gets 85, worst gets 25)
                rerank_scores[lead_id] = 25 + (normalized * 60)
            
            print(f"[ICP Matcher] Reranking complete - {len(rerank_scores)} scores (raw: {min_score:.3f}-{max_score:.3f})")
        else:
            rerank_scores = {}
            print(f"[ICP Matcher] Reranking complete - no scores")
        
    except Exception as e:
        print(f"[ICP Matcher] Reranking failed: {e}")
        print("[ICP Matcher] Falling back to embedding similarity only")
        rerank_scores = {}
    
    # Step 5: Update all leads with scores
    print(f"[Step 5] Updating {len(leads)} leads...")
    
    qualified = 0
    failed = 0
    
    for lead in leads:
        lead_id = lead["id"]
        
        try:
            # Get score from reranker (already normalized to 25-85) or fall back
            if lead_id in rerank_scores:
                score = int(rerank_scores[lead_id])
            else:
                # Use embedding similarity as fallback
                similarity = lead.get("similarity", 0.5)
                score = similarity_to_score(similarity)
            
            # Generate reasoning
            reasoning = generate_match_reasoning(lead, score, icp)
            
            # Update lead
            supabase.table("leads").update({
                "status": "qualified",
                "icp_score": score,
                "match_reasoning": reasoning,
                "qualified_at": datetime.utcnow().isoformat(),
                "error_message": None
            }).eq("id", lead_id).execute()
            
            qualified += 1
            
        except Exception as e:
            print(f"[ICP Matcher] Error updating lead {lead_id}: {e}")
            supabase.table("leads").update({
                "status": "failed",
                "error_message": str(e)[:200]
            }).eq("id", lead_id).execute()
            failed += 1
    
    print(f"\n{'='*60}")
    print(f"[ICP Matcher] COMPLETE")
    print(f"  - Qualified: {qualified}")
    print(f"  - Failed: {failed}")
    print(f"{'='*60}\n")
    
    return {
        "qualified": qualified,
        "failed": failed
    }


async def re_qualify_batch(batch_id: str, icp: Dict[str, Any]) -> Dict[str, int]:
    """
    Re-qualify all leads in a batch (even those already qualified).
    
    Useful when ICP criteria have been updated.
    """
    # Reset qualified leads to enriched
    result = supabase.table("leads").select("id").eq("batch_id", batch_id).eq("status", "qualified").execute()
    
    for lead in (result.data or []):
        supabase.table("leads").update({"status": "enriched"}).eq("id", lead["id"]).execute()
    
    print(f"[ICP Matcher] Reset {len(result.data or [])} leads to enriched")
    
    # Run qualification
    return await qualify_batch(batch_id, icp)


# =============================================================================
# Single Profile Scoring (for testing/debugging)
# =============================================================================

async def score_profile(lead: Dict[str, Any], icp: Dict[str, Any]) -> Dict[str, Any]:
    """
    Score a single profile against the ICP.

    Uses embedding similarity. For debugging/testing only.
    """
    try:
        # Build ICP text and generate embedding
        icp_text = build_icp_text(icp)
        icp_embedding = generate_embedding(icp_text)
        
        if not icp_embedding:
            return {"success": False, "score": 0, "reasoning": "Failed to generate ICP embedding"}
        
        # Generate profile embedding
        profile_text = create_profile_text(lead)
        profile_embedding = generate_embedding(profile_text)
        
        if not profile_embedding:
            return {"success": False, "score": 0, "reasoning": "Failed to generate profile embedding"}
        
        # Calculate cosine similarity
        import math
        dot_product = sum(a * b for a, b in zip(icp_embedding, profile_embedding))
        norm1 = math.sqrt(sum(a * a for a in icp_embedding))
        norm2 = math.sqrt(sum(b * b for b in profile_embedding))
        similarity = dot_product / (norm1 * norm2) if norm1 and norm2 else 0
        
        score = similarity_to_score(similarity)
        reasoning = generate_match_reasoning(lead, score, icp)
        
        return {
            "success": True,
            "score": score,
            "reasoning": reasoning,
            "similarity": similarity
        }
        
    except Exception as e:
        return {"success": False, "score": 0, "reasoning": f"Error: {str(e)[:100]}"}
