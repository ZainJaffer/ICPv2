"""
Test embedding generation.

Run: python scripts/test_embeddings.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(".env.local")
load_dotenv()

from app.services.matching.embeddings import (
    generate_embedding,
    generate_profile_embedding,
    create_profile_text,
    format_embedding_for_postgres
)

print("=" * 50)
print("Embeddings Test")
print("=" * 50)

# Test basic embedding
print("\n1. Testing basic embedding generation...")
text = "CFO at a SaaS startup, experienced in financial planning"
embedding = generate_embedding(text)

if embedding:
    print(f"   ✓ Generated embedding with {len(embedding)} dimensions")
    print(f"   First 5 values: {embedding[:5]}")
else:
    print("   ✗ Failed to generate embedding")
    exit(1)

# Test profile embedding
print("\n2. Testing profile embedding...")
sample_lead = {
    "name": "John Smith",
    "headline": "Chief Financial Officer | SaaS Expert",
    "company": "TechCorp",
    "location": "San Francisco, CA",
    "profile_data": {
        "summary": "20 years of experience in finance and technology.",
        "positions": [
            {"title": "CFO", "company": {"name": "TechCorp"}},
            {"title": "VP Finance", "company": {"name": "StartupXYZ"}}
        ],
        "skills": [
            {"name": "Financial Planning"},
            {"name": "SaaS Metrics"},
            {"name": "Fundraising"}
        ]
    }
}

profile_text = create_profile_text(sample_lead)
print(f"   Profile text: {profile_text[:100]}...")

profile_embedding = generate_profile_embedding(sample_lead)
if profile_embedding:
    print(f"   ✓ Generated profile embedding with {len(profile_embedding)} dimensions")
else:
    print("   ✗ Failed to generate profile embedding")

# Test postgres format
print("\n3. Testing Postgres format...")
formatted = format_embedding_for_postgres(embedding[:5])  # Just first 5 for display
print(f"   Format: {formatted}")

print("\n" + "=" * 50)
print("✅ Embeddings working!")
print("=" * 50)
