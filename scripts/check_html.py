"""Quick script to examine HTML file format."""
import re
from pathlib import Path

INPUTS_DIR = Path("C:/Users/Zain Jaffer/Desktop/Dev/ICPv2/inputs")
OUTPUT_FILE = Path("C:/Users/Zain Jaffer/Desktop/Dev/ICPv2/html_analysis.txt")

html_file = INPUTS_DIR / "carl_seidman.html"

with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

with open(OUTPUT_FILE, 'w', encoding='utf-8') as out:
    out.write(f"File: {html_file.name}\n")
    out.write(f"Size: {len(content):,} characters\n\n")
    
    # Find LinkedIn URLs
    pattern = r'linkedin\.com/in/[^\s"\'<>]+'
    urls = re.findall(pattern, content, re.IGNORECASE)
    
    out.write(f"LinkedIn URL patterns found: {len(urls)}\n\n")
    
    if urls:
        out.write("First 10 samples:\n")
        for i, url in enumerate(urls[:10]):
            out.write(f"  {i+1}. {url[:80]}\n")
    
    out.write("\nDone.\n")

print("Analysis complete - check html_analysis.txt")
