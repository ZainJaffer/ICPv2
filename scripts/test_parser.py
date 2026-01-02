"""Test the HTML parser with a real file."""
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.html_parser import extract_linkedin_urls

INPUTS_DIR = Path("C:/Users/Zain Jaffer/Desktop/Dev/ICPv2/inputs")
OUTPUT_FILE = Path("C:/Users/Zain Jaffer/Desktop/Dev/ICPv2/parser_test.txt")

html_file = INPUTS_DIR / "carl_seidman.html"

print(f"Reading {html_file.name}...")

with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

print(f"File size: {len(content):,} chars")
print("Running parser...")

urls = extract_linkedin_urls(content)

with open(OUTPUT_FILE, 'w', encoding='utf-8') as out:
    out.write(f"Parser Test Results\n")
    out.write(f"==================\n\n")
    out.write(f"Input file: {html_file.name}\n")
    out.write(f"File size: {len(content):,} characters\n\n")
    out.write(f"Unique URLs extracted: {len(urls)}\n\n")
    
    out.write("First 20 URLs:\n")
    for i, url in enumerate(urls[:20], 1):
        out.write(f"  {i}. {url}\n")
    
    out.write(f"\nLast 5 URLs:\n")
    for i, url in enumerate(urls[-5:], len(urls)-4):
        out.write(f"  {i}. {url}\n")

print(f"\nResults written to {OUTPUT_FILE}")
print(f"Extracted {len(urls)} unique URLs")
