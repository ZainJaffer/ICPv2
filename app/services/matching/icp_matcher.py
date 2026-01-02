"""
ICP Matcher Service - Score LinkedIn profiles against client ICPs using GPT-5-mini.

Uses structured LLM outputs to generate:
- ICP score (0-100)
- Match reasoning
"""

import os
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

from ..db.supabase_client import supabase

load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Model to use
MODEL = "gpt-5-mini"


ICP_MATCHING_PROMPT = """You are scoring a LinkedIn profile against an Ideal Customer Profile (ICP).

## ICP CRITERIA

Target Titles: {target_titles}
Target Industries: {target_industries}
Company Sizes: {company_sizes}
Target Keywords: {target_keywords}
Exclude Titles: {exclude_titles}

## LINKEDIN PROFILE

Name: {name}
Headline: {headline}
Company: {company}
Location: {location}
Current Job Title: {current_job_title}

Full Profile Data:
{profile_summary}

## SCORING RULES

Score 0-100 based on how well this profile matches the ICP:

- **90-100**: Perfect match - title, industry, and company size all align strongly
- **70-89**: Strong match - most criteria align, minor gaps
- **50-69**: Moderate match - some criteria align, some don't
- **30-49**: Weak match - few criteria align
- **10-29**: Poor match - mostly misaligned
- **0-9**: No match - completely outside ICP

IMPORTANT:
- If the person's title is in the EXCLUDE list, score should be 0-10
- If no ICP criteria are provided, score based on general relevance
- Consider the person's seniority and decision-making authority

## RESPONSE FORMAT

Respond with JSON only:
{{
  "score": <0-100>,
  "reasoning": "<2-3 sentence explanation of the score>"
}}"""


def format_list(items: Optional[List[str]]) -> str:
    """Format a list for display in the prompt."""
    if not items:
        return "Not specified"
    return ", ".join(items)


def create_profile_summary(profile_data: Dict[str, Any]) -> str:
    """Create a concise summary of profile data for the prompt."""
    if not profile_data:
        return "No additional profile data available"
    
    parts = []
    
    # Add summary/about
    if profile_data.get("summary"):
        parts.append(f"About: {profile_data['summary'][:300]}...")
    
    # Add current positions
    positions = profile_data.get("positions", [])
    if positions:
        parts.append("Current Positions:")
        for pos in positions[:3]:  # Limit to first 3
            title = pos.get("title", "Unknown")
            company = pos.get("company", {})
            company_name = company.get("name") if isinstance(company, dict) else company
            parts.append(f"  - {title} at {company_name}")
    
    # Add skills
    skills = profile_data.get("skills", [])
    if skills:
        skill_names = [s.get("name") if isinstance(s, dict) else s for s in skills[:10]]
        parts.append(f"Skills: {', '.join(skill_names)}")
    
    return "\n".join(parts) if parts else "No additional profile data available"


async def score_profile(
    lead: Dict[str, Any],
    icp: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Score a single profile against the ICP.
    
    Args:
        lead: Lead record with profile_data
        icp: ICP criteria from client_icps table
    
    Returns:
        Dict with score and reasoning
    """
    try:
        # Build the prompt
        profile_data = lead.get("profile_data", {}) or {}
        
        prompt = ICP_MATCHING_PROMPT.format(
            target_titles=format_list(icp.get("target_titles")),
            target_industries=format_list(icp.get("target_industries")),
            company_sizes=format_list(icp.get("company_sizes")),
            target_keywords=format_list(icp.get("target_keywords")),
            exclude_titles=format_list(icp.get("exclude_titles")),
            name=lead.get("name", "Unknown"),
            headline=lead.get("headline", "Not available"),
            company=lead.get("company", "Not available"),
            location=lead.get("location", "Not available"),
            current_job_title=lead.get("current_job_title", "Not available"),
            profile_summary=create_profile_summary(profile_data)
        )
        
        # Call GPT-5-mini
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,  # Low temperature for consistency
            response_format={"type": "json_object"}
        )
        
        # Parse response
        result = json.loads(response.choices[0].message.content)
        
        score = int(result.get("score", 0))
        reasoning = result.get("reasoning", "No reasoning provided")
        
        # Clamp score to valid range
        score = max(0, min(100, score))
        
        return {
            "success": True,
            "score": score,
            "reasoning": reasoning
        }
        
    except Exception as e:
        print(f"[ICP Matcher] Error scoring profile: {e}")
        return {
            "success": False,
            "score": 0,
            "reasoning": f"Error: {str(e)[:100]}"
        }


async def qualify_lead(lead: Dict[str, Any], icp: Dict[str, Any]) -> Dict[str, Any]:
    """
    Qualify a single lead by scoring against ICP.
    
    Args:
        lead: Lead record from database
        icp: ICP criteria
    
    Returns:
        Dict with qualification result
    """
    lead_id = lead["id"]
    
    try:
        # Score the profile
        result = await score_profile(lead, icp)
        
        if not result["success"]:
            # Update lead with error
            supabase.table("leads").update({
                "status": "failed",
                "error_message": result.get("reasoning", "Scoring failed"),
                "retry_count": lead.get("retry_count", 0) + 1
            }).eq("id", lead_id).execute()
            
            return {
                "lead_id": lead_id,
                "success": False,
                "error": result.get("reasoning")
            }
        
        # Update lead with score
        supabase.table("leads").update({
            "status": "qualified",
            "icp_score": result["score"],
            "match_reasoning": result["reasoning"],
            "qualified_at": datetime.utcnow().isoformat(),
            "error_message": None
        }).eq("id", lead_id).execute()
        
        return {
            "lead_id": lead_id,
            "success": True,
            "score": result["score"],
            "reasoning": result["reasoning"]
        }
        
    except Exception as e:
        print(f"[ICP Matcher] Error qualifying lead {lead_id}: {e}")
        
        supabase.table("leads").update({
            "status": "failed",
            "error_message": str(e),
            "retry_count": lead.get("retry_count", 0) + 1
        }).eq("id", lead_id).execute()
        
        return {
            "lead_id": lead_id,
            "success": False,
            "error": str(e)
        }


async def qualify_batch(batch_id: str, icp: Dict[str, Any]) -> Dict[str, int]:
    """
    Qualify all enriched leads in a batch.
    
    Args:
        batch_id: The batch ID to process
        icp: ICP criteria from client_icps table
    
    Returns:
        Dict with counts: qualified, failed
    """
    # Get all enriched leads in batch
    result = supabase.table("leads").select("*").eq("batch_id", batch_id).eq("status", "enriched").execute()
    
    leads = result.data or []
    print(f"[ICP Matcher] Qualifying {len(leads)} leads in batch {batch_id}")
    
    qualified = 0
    failed = 0
    
    for lead in leads:
        result = await qualify_lead(lead, icp)
        
        if result["success"]:
            qualified += 1
            print(f"  → {lead.get('name', 'Unknown')}: {result['score']}/100")
        else:
            failed += 1
    
    print(f"[ICP Matcher] Batch complete: {qualified} qualified, {failed} failed")
    
    return {
        "qualified": qualified,
        "failed": failed
    }


async def re_qualify_batch(batch_id: str, icp: Dict[str, Any]) -> Dict[str, int]:
    """
    Re-qualify all leads in a batch (even those already qualified).
    
    Useful when ICP criteria have been updated.
    
    Args:
        batch_id: The batch ID to process
        icp: Updated ICP criteria
    
    Returns:
        Dict with counts
    """
    # Get all enriched or qualified leads
    result = supabase.table("leads").select("*").eq("batch_id", batch_id).in_("status", ["enriched", "qualified"]).execute()
    
    leads = result.data or []
    print(f"[ICP Matcher] Re-qualifying {len(leads)} leads in batch {batch_id}")
    
    # Reset qualified leads to enriched
    for lead in leads:
        if lead["status"] == "qualified":
            supabase.table("leads").update({"status": "enriched"}).eq("id", lead["id"]).execute()
    
    # Run qualification
    return await qualify_batch(batch_id, icp)
