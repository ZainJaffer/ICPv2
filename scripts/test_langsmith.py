"""
Test LangSmith tracing - verify traces appear in dashboard.

Run: python scripts/test_langsmith.py
Check: https://smith.langchain.com
"""

import os
from dotenv import load_dotenv

# Load .env.local (or .env as fallback)
load_dotenv(".env.local")
load_dotenv()  # fallback to .env if .env.local doesn't exist

# Verify env vars are set
api_key = os.getenv("LANGCHAIN_API_KEY")
tracing = os.getenv("LANGCHAIN_TRACING_V2")
openai_key = os.getenv("OPENAI_API_KEY")
project = os.getenv("LANGCHAIN_PROJECT")

print("=" * 50)
print("LangSmith Tracing Test")
print("=" * 50)
print(f"LANGCHAIN_API_KEY: {'✓ Set (' + api_key[:8] + '...)' if api_key else '✗ Missing'}")
print(f"LANGCHAIN_TRACING_V2: {tracing}")
print(f"LANGCHAIN_PROJECT: {project or '(not set - using default)'}")
print(f"OPENAI_API_KEY: {'✓ Set' if openai_key else '✗ Missing'}")
print("=" * 50)

# Debug: show key details
print(f"\n🔑 API Key details:")
print(f"   Length: {len(api_key)} characters")
print(f"   First 12: {api_key[:12]}...")
print(f"   Last 4: ...{api_key[-4:]}")

# Test with direct HTTP request
print("\n🔍 Testing LangSmith API with direct HTTP...")
import httpx

headers = {
    "x-api-key": api_key,
    "Content-Type": "application/json"
}

try:
    # Try the info endpoint first (simplest)
    resp = httpx.get("https://api.smith.langchain.com/info", headers=headers, timeout=10)
    print(f"   /info response: {resp.status_code}")
    if resp.status_code == 200:
        print(f"   ✓ API key works!")
        print(f"   Response: {resp.text[:200]}")
    else:
        print(f"   Response body: {resp.text}")
except Exception as e:
    print(f"   Error: {e}")

# Try sessions endpoint
try:
    resp = httpx.get("https://api.smith.langchain.com/sessions?limit=1", headers=headers, timeout=10)
    print(f"\n   /sessions response: {resp.status_code}")
    if resp.status_code == 200:
        print(f"   ✓ Sessions endpoint works!")
    else:
        print(f"   Response body: {resp.text}")
except Exception as e:
    print(f"   Error: {e}")

# Try with Authorization header instead
print("\n🔍 Trying Authorization: Bearer header...")
headers2 = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}
try:
    resp = httpx.get("https://api.smith.langchain.com/sessions?limit=1", headers=headers2, timeout=10)
    print(f"   /sessions response: {resp.status_code}")
    if resp.status_code == 200:
        print(f"   ✓ Bearer auth works!")
    else:
        print(f"   Response body: {resp.text}")
except Exception as e:
    print(f"   Error: {e}")

if not api_key or not openai_key:
    print("\n❌ Missing required environment variables!")
    exit(1)

# Import langchain after env vars are loaded
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

# Create model with tracing
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

print("\n📤 Sending test message to LLM...")

# Make a simple call
response = llm.invoke([
    HumanMessage(content="Say 'LangSmith tracing works!' in exactly those words.")
])

print(f"\n📥 Response: {response.content}")

print("\n" + "=" * 50)
print("✅ Test complete!")
print("=" * 50)
print("\nNow check your LangSmith dashboard:")
print("  https://smith.langchain.com")
print("\nYou should see a trace for this LLM call.")
