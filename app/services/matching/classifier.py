"""
LLM Classifier Service - Classify LinkedIn profiles by industry and company type.

Runs during enrichment to enable SQL filtering before vector search.
Stores reasoning for debugging and transparency.
"""

import os
import json
from typing import Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(".env.local")
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MODEL = "gpt-5-mini"

# Industry categories (expandable)
INDUSTRIES = [
    "SaaS",
    "Fintech", 
    "Healthcare",
    "E-commerce",
    "AI/ML",
    "Cybersecurity",
    "EdTech",
    "MarTech",
    "HRTech",
    "PropTech",
    "CleanTech",
    "Consulting",
    "Financial Services",
    "Manufacturing",
    "Retail",
    "Media/Entertainment",
    "Telecommunications",
    "Government/Public Sector",
    "Non-profit",
    "Other"
]

# Company type categories
COMPANY_TYPES = [
    "startup",      # < 50 employees, early stage
    "scaleup",      # 50-500 employees, growth stage
    "mid-market",   # 500-5000 employees
    "enterprise",   # > 5000 employees
    "agency",       # Service/consulting firm
    "freelance",    # Self-employed/solo
    "unknown"
]

CLASSIFICATION_PROMPT = """Analyze this LinkedIn profile and classify the person's company.

## PROFILE

Name: {name}
Headline: {headline}
Company: {company}
Location: {location}

About/Summary:
{summary}

Current Position:
{position_details}

## TASK

1. Determine the PRIMARY INDUSTRY of their current company
2. Determine the COMPANY TYPE/SIZE

## INDUSTRY OPTIONS
{industries}

## COMPANY TYPE OPTIONS
{company_types}

## RESPONSE FORMAT

Respond with JSON only:
{{
  "industry": "<one of the industry options>",
  "industry_reasoning": "<1-2 sentences explaining why this industry>",
  "company_type": "<one of the company type options>",
  "company_reasoning": "<1-2 sentences explaining the company size/type>"
}}

Use "Other" for industry if none fit well.
Use "unknown" for company_type if you can't determine it."""


def build_profile_context(lead: Dict[str, Any]) -> Dict[str, str]:
    """Extract relevant context from lead for classification."""
    profile_data = lead.get("profile_data", {}) or {}
    
    # Get summary (no truncation - GPT-5-mini can handle full summaries)
    summary = profile_data.get("summary", "Not available")
    
    # Get current position details (no truncation - include full descriptions)
    positions = profile_data.get("positions", [])
    position_details = "Not available"
    if positions:
        pos = positions[0]
        title = pos.get("title", "Unknown")
        company = pos.get("company", {})
        company_name = company.get("name") if isinstance(company, dict) else company
        description = pos.get("description", "")
        position_details = f"{title} at {company_name}"
        if description:
            position_details += f"\n{description}"
    
    return {
        "name": lead.get("name", "Unknown"),
        "headline": lead.get("headline", "Not available"),
        "company": lead.get("company", "Not available"),
        "location": lead.get("location", "Not available"),
        "summary": summary,
        "position_details": position_details
    }


def classify_profile(lead: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    Classify a profile by industry and company type.
    
    Args:
        lead: Lead record with profile_data
    
    Returns:
        Dict with industry, company_type, and reasoning, or None on error
    """
    try:
        context = build_profile_context(lead)
        
        prompt = CLASSIFICATION_PROMPT.format(
            name=context["name"],
            headline=context["headline"],
            company=context["company"],
            location=context["location"],
            summary=context["summary"],
            position_details=context["position_details"],
            industries=", ".join(INDUSTRIES),
            company_types=", ".join(COMPANY_TYPES)
        )
        
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        
        # Validate industry
        industry = result.get("industry", "Other")
        if industry not in INDUSTRIES:
            industry = "Other"
        
        # Validate company_type
        company_type = result.get("company_type", "unknown")
        if company_type not in COMPANY_TYPES:
            company_type = "unknown"
        
        return {
            "industry": industry,
            "industry_reasoning": result.get("industry_reasoning", ""),
            "company_type": company_type,
            "company_reasoning": result.get("company_reasoning", "")
        }
        
    except Exception as e:
        print(f"[Classifier] Error classifying profile: {e}")
        return None


def batch_classify_profiles(leads: list[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    """
    Classify multiple profiles.
    
    Args:
        leads: List of lead records
    
    Returns:
        Dict mapping lead_id -> classification result
    """
    results = {}
    
    for lead in leads:
        lead_id = lead.get("id")
        if not lead_id:
            continue
        
        classification = classify_profile(lead)
        if classification:
            results[lead_id] = classification
    
    return results
