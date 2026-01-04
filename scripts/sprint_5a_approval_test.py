"""
Sprint 5a approval test runner (API usability):
- Upsert ICP via API (POST /clients/{id}/icp)
- Background enrich (POST /batches/{id}/enrich?background=true&limit=5) + polling
- Background qualify (POST /batches/{id}/qualify?background=true) + polling
- Export CSV
- Background run (POST /batches/{id}/run?background=true&limit=5) + polling

This script is safe to run multiple times.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

import requests


BASE_URL = "http://localhost:8001"

# Existing IDs from our recent testing
ALLISON_CLIENT_ID = "867a2eb0-6655-4fa8-9e25-f4a1d6e26859"
BEN_BATCH_ID = "541581b9-4b08-4b0b-b01f-94c175b60df5"


def _pretty(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def _get(path: str) -> Dict[str, Any]:
    r = requests.get(f"{BASE_URL}{path}", timeout=30)
    r.raise_for_status()
    return r.json()


def _post(path: str, json_body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    r = requests.post(f"{BASE_URL}{path}", json=json_body, timeout=300)
    r.raise_for_status()
    return r.json()


def _poll_batch(batch_id: str, target_status: str, timeout_s: int = 180, interval_s: int = 5) -> Dict[str, Any]:
    start = time.time()
    last = None
    while time.time() - start < timeout_s:
        data = _get(f"/batches/{batch_id}")
        last = data
        status = (data.get("batch") or {}).get("status")
        counts = data.get("lead_counts") or {}
        print(f"[poll] status={status} counts={counts}")
        if status == target_status:
            return data
        time.sleep(interval_s)
    raise TimeoutError(f"Timed out waiting for batch {batch_id} to reach status={target_status}. Last={last}")


def main() -> None:
    print("=" * 70)
    print("SPRINT 5a APPROVAL TEST")
    print("=" * 70)

    # 1) ICP upsert via API
    print("\n[1/5] Upsert ICP via API (Allison Gates)")
    icp_payload = {
        "target_titles": [
            "CMO",
            "Chief Marketing Officer",
            "Head of Marketing",
            "VP Marketing",
            "Director of Marketing",
            "Head of Growth",
        ],
        "target_industries": ["SaaS", "AI", "Technology", "Software", "Fintech"],
        "company_sizes": ["startup", "scaleup", "mid-market", "enterprise"],
        "target_keywords": ["demand gen", "growth", "pipeline", "brand"],
        "notes": "Marketing leaders at tech companies",
    }
    resp = _post(f"/clients/{ALLISON_CLIENT_ID}/icp", json_body=icp_payload)
    print(_pretty(resp))

    verify = _get(f"/clients/{ALLISON_CLIENT_ID}")
    icp = verify.get("icp") or {}
    print("\n[verify] client icp fields:")
    print(_pretty({k: icp.get(k) for k in ["target_titles", "target_industries", "company_sizes", "target_keywords", "notes"]}))

    # 2) Background enrich (limit=5) on Ben batch (large discovered set)
    print("\n[2/5] Background enrich (Ben batch, limit=5)")
    resp = _post(f"/batches/{BEN_BATCH_ID}/enrich?background=true&limit=5")
    print(_pretty(resp))
    print("[poll] waiting for status=enriched ...")
    _poll_batch(BEN_BATCH_ID, target_status="enriched", timeout_s=240, interval_s=5)

    # 3) Background qualify
    print("\n[3/5] Background qualify (Ben batch)")
    resp = _post(f"/batches/{BEN_BATCH_ID}/qualify?background=true")
    print(_pretty(resp))
    print("[poll] waiting for status=qualified ...")
    _poll_batch(BEN_BATCH_ID, target_status="qualified", timeout_s=240, interval_s=5)

    # 4) Export CSV
    print("\n[4/5] Export CSV (Ben batch)")
    csv_resp = requests.get(f"{BASE_URL}/batches/{BEN_BATCH_ID}/export", timeout=60)
    csv_resp.raise_for_status()
    out_path = "ben_sprint_5a_export.csv"
    with open(out_path, "wb") as f:
        f.write(csv_resp.content)
    print(f"Wrote {out_path} ({len(csv_resp.content)} bytes)")

    # 5) Run orchestrator in background (limit=5)
    print("\n[5/5] Background run orchestrator (Ben batch, limit=5)")
    resp = _post(f"/batches/{BEN_BATCH_ID}/run?background=true&limit=5")
    print(_pretty(resp))
    print("[poll] waiting for status=qualified ...")
    _poll_batch(BEN_BATCH_ID, target_status="qualified", timeout_s=240, interval_s=5)

    print("\nOK - Sprint 5a endpoints responded successfully.")


if __name__ == "__main__":
    main()

