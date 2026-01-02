"""
Embeddings Service - Generate vector embeddings for profiles and ICPs.

Uses OpenAI text-embedding-3-small (1536 dimensions).
"""

import os
from typing import Dict, Any, List, Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(".env.local")
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Model to use - text-embedding-3-small is fast and good quality
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


def create_profile_text(lead: Dict[str, Any]) -> str:
    """
    Create a text representation of a profile for embedding.
    
    Order is critical for ICP matching - job titles FIRST since that's
    the primary matching criterion, followed by industry/company.
    """
    parts = []
    profile_data = lead.get("profile_data", {}) or {}
    
    # 1. CURRENT JOB TITLES FIRST (most important for ICP matching)
    current_job_titles = lead.get("current_job_titles") or []
    if current_job_titles:
        parts.append(f"Job titles: {', '.join(current_job_titles)}")
    
    # 2. Name and headline
    if lead.get("name"):
        parts.append(lead["name"])
    
    if lead.get("headline"):
        parts.append(lead["headline"])
    
    # 3. Company and industry (important for ICP matching)
    if lead.get("company"):
        parts.append(f"Company: {lead['company']}")
    
    if lead.get("industry"):
        parts.append(f"Industry: {lead['industry']}")
    
    if lead.get("location"):
        parts.append(f"Location: {lead['location']}")
    
    # 4. Current positions with descriptions
    positions = profile_data.get("positions", [])
    if positions:
        current_positions = []
        past_positions = []
        
        for pos in positions:
            time_period = pos.get("timePeriod", {}) or {}
            end_date = time_period.get("endDate")
            
            title = pos.get("title", "")
            company = pos.get("company", {})
            company_name = company.get("name") if isinstance(company, dict) else company
            description = pos.get("description", "")
            
            if title:
                position_text = f"{title} at {company_name}" if company_name else title
                if description:
                    position_text += f". {description}"
                
                if end_date is None:
                    current_positions.append(position_text)
                else:
                    past_positions.append(position_text)
        
        if current_positions:
            parts.append("Current roles: " + " | ".join(current_positions))
        
        if past_positions:
            parts.append("Previous: " + " | ".join(past_positions[:2]))
    
    # 5. Summary
    if profile_data.get("summary"):
        parts.append(f"About: {profile_data['summary']}")
    
    # 6. Skills
    skills = profile_data.get("skills", [])
    if skills:
        skill_names = [s.get("name") if isinstance(s, dict) else s for s in skills[:10]]
        skill_names = [s for s in skill_names if s]
        if skill_names:
            parts.append(f"Skills: {', '.join(skill_names)}")
    
    return " | ".join(parts) if parts else "No profile information available"


def create_icp_text(icp: Dict[str, Any]) -> str:
    """
    Create a text representation of an ICP for embedding.
    
    Combines target criteria into a searchable description.
    """
    parts = []
    
    if icp.get("target_titles"):
        parts.append(f"Looking for: {', '.join(icp['target_titles'])}")
    
    if icp.get("target_industries"):
        parts.append(f"Industries: {', '.join(icp['target_industries'])}")
    
    if icp.get("company_sizes"):
        parts.append(f"Company sizes: {', '.join(icp['company_sizes'])}")
    
    if icp.get("target_keywords"):
        parts.append(f"Keywords: {', '.join(icp['target_keywords'])}")
    
    if icp.get("notes"):
        parts.append(icp["notes"])
    
    return " | ".join(parts) if parts else "General professional profile"


def generate_embedding(text: str) -> Optional[List[float]]:
    """
    Generate an embedding vector for the given text.
    
    Args:
        text: Text to embed
    
    Returns:
        List of floats (1536 dimensions) or None on error
    """
    if not text or not text.strip():
        return None
    
    try:
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text.strip()
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"[Embeddings] Error generating embedding: {e}")
        return None


def generate_profile_embedding(lead: Dict[str, Any]) -> Optional[List[float]]:
    """
    Generate an embedding for a lead's profile.
    
    Args:
        lead: Lead record with profile data
    
    Returns:
        Embedding vector or None
    """
    text = create_profile_text(lead)
    return generate_embedding(text)


def generate_icp_embedding(icp: Dict[str, Any]) -> Optional[List[float]]:
    """
    Generate an embedding for an ICP.
    
    Args:
        icp: ICP criteria from client_icps table
    
    Returns:
        Embedding vector or None
    """
    text = create_icp_text(icp)
    return generate_embedding(text)


def format_embedding_for_postgres(embedding: List[float]) -> str:
    """
    Format embedding as a string for Postgres vector type.
    
    Postgres expects: '[0.1, 0.2, 0.3, ...]'
    """
    return f"[{','.join(str(x) for x in embedding)}]"
