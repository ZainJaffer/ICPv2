"""
Test Jina Reranker.

Run: python scripts/test_reranker.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(".env.local")
load_dotenv()

from app.services.matching.reranker import get_reranker, JinaReranker

print("=" * 50)
print("Reranker Test")
print("=" * 50)

# Check API key
api_key = os.getenv("JINA_API_KEY")
print(f"\nJINA_API_KEY: {'✓ Set' if api_key else '✗ Missing'}")

if not api_key:
    print("Please add JINA_API_KEY to .env.local")
    exit(1)

# Test query (ICP)
query = "CFO, Chief Financial Officer, VP Finance at SaaS startup companies"

# Test documents (profile summaries)
documents = [
    "Sarah Chen | CFO at PayFlow | Building the future of B2B payments | San Francisco",
    "Mike Johnson | Software Engineer at Google | Python, Java, Kubernetes",
    "Emily Wong | VP Finance at TechStartup | Series B, 50 employees | Boston",
    "David Lee | Marketing Director at Enterprise Corp | Fortune 500",
    "Lisa Park | Head of Finance at CloudSaaS | Fintech startup | NYC",
    "Tom Brown | CEO at SmallBiz | Retail industry | Chicago",
    "Anna Smith | Finance Director at ScaleUp Inc | B2B SaaS | Austin",
    "Bob Wilson | Sales Manager at BigCorp | Enterprise software",
]

print(f"\nQuery: {query}")
print(f"Documents: {len(documents)}")

# Test Jina reranker
print("\n" + "-" * 50)
print("Testing Jina Reranker...")
print("-" * 50)

try:
    reranker = get_reranker("jina")
    results = reranker.rerank(query, documents, top_n=5)
    
    print(f"\n✓ Reranker returned {len(results)} results\n")
    
    print("Ranked Results:")
    print("-" * 50)
    for i, result in enumerate(results, 1):
        print(f"{i}. Score: {result.score:.4f}")
        print(f"   {result.text[:70]}...")
        print()
    
except Exception as e:
    print(f"\n✗ Error: {e}")
    exit(1)

# Compare with NoOp reranker
print("-" * 50)
print("Comparison: NoOp Reranker (no reranking)")
print("-" * 50)

noop = get_reranker("noop")
noop_results = noop.rerank(query, documents, top_n=5)

print("\nOriginal order (first 5):")
for i, result in enumerate(noop_results, 1):
    print(f"{i}. {result.text[:60]}...")

print("\n" + "=" * 50)
print("✅ Reranker test complete!")
print("=" * 50)
