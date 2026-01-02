"""
Test LLM classifier.

Run: python scripts/test_classifier.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(".env.local")
load_dotenv()

from app.services.matching.classifier import classify_profile

print("=" * 50)
print("Classifier Test")
print("=" * 50)

# Test profile 1: SaaS startup
sample_lead_1 = {
    "name": "Sarah Chen",
    "headline": "VP Engineering | Building the future of B2B payments",
    "company": "PayFlow",
    "location": "San Francisco, CA",
    "profile_data": {
        "summary": "Leading engineering at PayFlow, a Series B fintech startup revolutionizing B2B payments. Previously at Stripe and Square.",
        "positions": [
            {
                "title": "VP Engineering",
                "company": {"name": "PayFlow"},
                "description": "Leading a team of 25 engineers building payment infrastructure for businesses."
            }
        ]
    }
}

print("\n1. Testing SaaS/Fintech profile...")
print(f"   Profile: {sample_lead_1['name']} - {sample_lead_1['headline']}")
result1 = classify_profile(sample_lead_1)
if result1:
    print(f"   ✓ Industry: {result1['industry']}")
    print(f"     Reasoning: {result1['industry_reasoning']}")
    print(f"   ✓ Company Type: {result1['company_type']}")
    print(f"     Reasoning: {result1['company_reasoning']}")
else:
    print("   ✗ Classification failed")

# Test profile 2: Enterprise consulting
sample_lead_2 = {
    "name": "Michael Roberts",
    "headline": "Partner at McKinsey & Company | Digital Transformation",
    "company": "McKinsey & Company",
    "location": "New York, NY",
    "profile_data": {
        "summary": "Partner at McKinsey focusing on digital transformation for Fortune 500 companies.",
        "positions": [
            {
                "title": "Partner",
                "company": {"name": "McKinsey & Company"},
                "description": "Leading digital transformation engagements across financial services and healthcare sectors."
            }
        ]
    }
}

print("\n2. Testing Enterprise Consulting profile...")
print(f"   Profile: {sample_lead_2['name']} - {sample_lead_2['headline']}")
result2 = classify_profile(sample_lead_2)
if result2:
    print(f"   ✓ Industry: {result2['industry']}")
    print(f"     Reasoning: {result2['industry_reasoning']}")
    print(f"   ✓ Company Type: {result2['company_type']}")
    print(f"     Reasoning: {result2['company_reasoning']}")
else:
    print("   ✗ Classification failed")

# Test profile 3: Healthcare startup
sample_lead_3 = {
    "name": "Dr. Emily Wong",
    "headline": "CEO & Co-founder | AI-powered diagnostics",
    "company": "MedAI Labs",
    "location": "Boston, MA",
    "profile_data": {
        "summary": "Physician-turned-entrepreneur building AI tools to help radiologists detect cancer earlier. Raised $5M seed round.",
        "positions": [
            {
                "title": "CEO & Co-founder",
                "company": {"name": "MedAI Labs"},
                "description": "Building machine learning models for medical imaging analysis."
            }
        ]
    }
}

print("\n3. Testing Healthcare/AI startup profile...")
print(f"   Profile: {sample_lead_3['name']} - {sample_lead_3['headline']}")
result3 = classify_profile(sample_lead_3)
if result3:
    print(f"   ✓ Industry: {result3['industry']}")
    print(f"     Reasoning: {result3['industry_reasoning']}")
    print(f"   ✓ Company Type: {result3['company_type']}")
    print(f"     Reasoning: {result3['company_reasoning']}")
else:
    print("   ✗ Classification failed")

print("\n" + "=" * 50)
print("✅ Classifier test complete!")
print("=" * 50)
