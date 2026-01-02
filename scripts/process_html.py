"""
Process HTML files from the inputs folder.

Usage:
    # Process a single file for a client
    python scripts/process_html.py --client "Carl Seidman" --file "carl_seidman.html"
    
    # Process all files in inputs/ (creates one client per file)
    python scripts/process_html.py --all
    
    # List all input files
    python scripts/process_html.py --list
"""

import argparse
import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.supabase_client import supabase
from app.services.html_parser import extract_linkedin_urls
from app.services.enrichment import create_leads_from_urls


INPUTS_DIR = Path(__file__).parent.parent / "inputs"
OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"


def list_input_files():
    """List all HTML files in the inputs directory."""
    files = list(INPUTS_DIR.glob("*.html"))
    print(f"\n📁 Found {len(files)} HTML files in inputs/:\n")
    for f in sorted(files):
        print(f"  - {f.name}")
    print()
    return files


def get_or_create_client(name: str) -> str:
    """Get existing client or create new one. Returns client_id."""
    # Check if client exists
    result = supabase.table("clients").select("id").eq("name", name).execute()
    
    if result.data and len(result.data) > 0:
        client_id = result.data[0]["id"]
        print(f"✓ Found existing client: {name} ({client_id[:8]}...)")
        return client_id
    
    # Create new client
    result = supabase.table("clients").insert({"name": name}).execute()
    client_id = result.data[0]["id"]
    
    # Create empty ICP
    supabase.table("client_icps").insert({"client_id": client_id}).execute()
    
    print(f"✓ Created new client: {name} ({client_id[:8]}...)")
    return client_id


def create_batch(client_id: str, filename: str, total_leads: int) -> str:
    """Create a new batch for the client."""
    result = supabase.table("batches").insert({
        "client_id": client_id,
        "filename": filename,
        "status": "ready",
        "total_leads": total_leads
    }).execute()
    
    batch_id = result.data[0]["id"]
    print(f"✓ Created batch: {batch_id[:8]}...")
    return batch_id


async def process_file(client_name: str, filename: str) -> dict:
    """Process a single HTML file."""
    filepath = INPUTS_DIR / filename
    
    if not filepath.exists():
        print(f"❌ File not found: {filepath}")
        return {"success": False, "error": "File not found"}
    
    print(f"\n{'='*60}")
    print(f"Processing: {filename}")
    print(f"Client: {client_name}")
    print(f"{'='*60}")
    
    # Read HTML
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        html_content = f.read()
    
    # Extract URLs
    urls = extract_linkedin_urls(html_content)
    
    if not urls:
        print(f"⚠️  No LinkedIn URLs found in {filename}")
        return {"success": False, "error": "No URLs found"}
    
    print(f"✓ Extracted {len(urls)} LinkedIn URLs")
    
    # Get or create client
    client_id = get_or_create_client(client_name)
    
    # Create batch
    batch_id = create_batch(client_id, filename, len(urls))
    
    # Create leads
    created, duplicates = await create_leads_from_urls(client_id, batch_id, urls)
    
    print(f"✓ Created {created} leads ({duplicates} duplicates skipped)")
    
    return {
        "success": True,
        "client_id": client_id,
        "batch_id": batch_id,
        "urls_extracted": len(urls),
        "leads_created": created,
        "duplicates_skipped": duplicates
    }


async def process_all_files():
    """Process all HTML files, creating one client per file."""
    files = list(INPUTS_DIR.glob("*.html"))
    
    if not files:
        print("❌ No HTML files found in inputs/")
        return
    
    print(f"\n🚀 Processing {len(files)} files...\n")
    
    results = []
    for filepath in sorted(files):
        # Generate client name from filename
        # e.g., "carl_seidman.html" -> "Carl Seidman"
        client_name = filepath.stem.replace("_", " ").replace("-", " ").title()
        
        result = await process_file(client_name, filepath.name)
        results.append({
            "file": filepath.name,
            "client": client_name,
            **result
        })
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    successful = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]
    
    print(f"✓ Processed: {len(successful)}/{len(results)} files")
    
    if failed:
        print(f"\n⚠️  Failed files:")
        for r in failed:
            print(f"  - {r['file']}: {r.get('error', 'Unknown error')}")
    
    total_leads = sum(r.get("leads_created", 0) for r in results)
    print(f"\n📊 Total leads created: {total_leads}")
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Process LinkedIn HTML files")
    parser.add_argument("--client", help="Client name")
    parser.add_argument("--file", help="HTML filename (in inputs/ folder)")
    parser.add_argument("--all", action="store_true", help="Process all files")
    parser.add_argument("--list", action="store_true", help="List input files")
    
    args = parser.parse_args()
    
    if args.list:
        list_input_files()
        return
    
    if args.all:
        asyncio.run(process_all_files())
        return
    
    if args.client and args.file:
        asyncio.run(process_file(args.client, args.file))
        return
    
    # Default: show help
    parser.print_help()
    print("\n📂 Input files available:")
    list_input_files()


if __name__ == "__main__":
    main()
