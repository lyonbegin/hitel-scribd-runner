#!/usr/bin/env python3
"""ONE-TIME 10 concurrent Scribd downloads in user's already signed-in Windows Chrome.

Use only the local CDP bridge; never start a browser or access its profile.
All 10 tabs operate concurrently. PDF files stay on this PC; Actions receives
only document IDs, download outcomes and sizes, not the downloaded files.
"""
import argparse
import asyncio
import csv
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scribd_pc_cdp_attach as engine
from playwright.async_api import async_playwright


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def choice(catalog, scope, local_checkpoint):
    docs = engine.load_documents(catalog, scope)
    prior = {r.get("document_id"): r for r in engine.load_csv(local_checkpoint)}
    confirmed = [
        d for d in docs if
        (p := prior.get(d["document_id"], {})).get("status") == "preview_visible"
        and str(p.get("download_button_visible", "")).lower() == "true"
    ]
    selected = list(confirmed[:10])
    taken = {d["document_id"] for d in selected}
    for doc in docs:
        if len(selected) >= 10:
            break
        if doc["document_id"] not in taken:
            selected.append(doc)
            taken.add(doc["document_id"])
    if len(selected) != 10 or len(taken) != 10:
        raise RuntimeError(f"Expected 10 unique saved document links; got {len(selected)}")
    return docs, selected, len(confirmed)


async def main(args):
    if args.cdp != "http://127.0.0.1:9222":
        raise ValueError("CDP must stay on localhost:9222")
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "HITEL"
    checkpoint = local / "ScribdReview" / "unlinked" / "results.csv"
    downloaded_files = local / "ScribdDownloads"
    docs, selected, prior_previews = choice(Path(args.catalog).resolve(), "unlinked", checkpoint)
    print("TEN_PARALLEL_SELECTED", json.dumps({
        "original_queue": len(docs), "previously_verified_preview_with_download_control": prior_previews,
        "ten_distinct_document_ids": [d["document_id"] for d in selected],
        "browser": "separate desktop Chrome", "cdp": "localhost:9222",
        "parallel_tabs": 10, "run_type": "ONE_TIME_SMOKE",
        "files_remain_on_user_pc": True,
    }, ensure_ascii=False), flush=True)
    from urllib.request import urlopen
    with urlopen(args.cdp + "/json/version", timeout=5) as response:
        info = json.loads(response.read(12000))
    if not str(info.get("Browser", "")).startswith("Chrome/"):
        raise RuntimeError("CDP endpoint is not the user's desktop Chrome")

    started_at = now()
    results = []
    sync_start = asyncio.Event()
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(args.cdp, timeout=15000)
        if not browser.contexts:
            raise RuntimeError("No preexisting signed-in Chrome context")
        context = browser.contexts[0]

        async def worker(item, index):
            folder = output / "diagnostics" / item["document_id"]
            folder.mkdir(parents=True, exist_ok=True)
            await sync_start.wait()
            start_time = now()
            start_clock = time.monotonic()
            print("TEN_PARALLEL_TAB_START", json.dumps({
                "tab": index, "document_id": item["document_id"], "timestamp": start_time
            }, ensure_ascii=False), flush=True)
            try:
                result = await asyncio.wait_for(
                    engine.one_permitted_download_test(
                        context, item, downloaded_files, folder
                    ), timeout=args.per_document_timeout)
            except Exception as exc:
                result = {"document_id": item["document_id"], "status": "task_exception",
                          "download_saved_on_pc": False,
                          "error": f"{type(exc).__name__}: {str(exc)}"[:260]}
            result["tab"] = index
            result["started_at"] = start_time
            result["completed_at"] = now()
            result["duration_seconds"] = round(time.monotonic() - start_clock, 2)
            results.append(result)
            print("TEN_PARALLEL_TAB_RESULT", json.dumps({
                "tab": index,
                "document_id": item["document_id"],
                "status": result.get("status"),
                "pdf_signature_valid": result.get("pdf_signature_valid"),
                "bytes": result.get("file_size_bytes"),
                "continue_anyway": result.get("continue_anyway_clicked"),
                "final_download_anchor": result.get("final_download_anchor_clicked"),
                "seconds": result["duration_seconds"],
            }, ensure_ascii=False), flush=True)

        tasks = [asyncio.create_task(worker(item, i + 1))
                 for i, item in enumerate(selected)]
        sync_start.set()  # Start all 10 tabs concurrently, not sequentially.
        await asyncio.gather(*tasks)
        # Do not browser.close(): user owns Chrome; CDP client just detaches.

    results.sort(key=lambda x: x["tab"])
    (output / "ten-download-results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    successes = sum(r.get("status") == "pdf_saved_on_pc" and
                    r.get("pdf_signature_valid") is True and
                    (r.get("file_size_bytes") or 0) > 0 for r in results)
    counts = dict(Counter(str(r.get("status", "unknown")) for r in results))
    summary = {
        "scope": "unlinked", "original_queue": len(docs),
        "attempted_documents": len(results),
        "simultaneous_tabs": 10,
        "pdf_saved_verified": successes,
        "failed_or_unconfirmed": len(results) - successes,
        "status_counts": counts,
        "run_started_at": started_at, "run_completed_at": now(),
        "each_tab_start": [r["started_at"] for r in results],
        "output_location_on_pc": r"%LOCALAPPDATA%\HITEL\ScribdDownloads",
        "files_uploaded_to_github": 0,
        "credentials_or_profile_uploaded_to_github": False,
        "note": "Only a successful file save plus %PDF- signature counts as verified."
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("TEN_PARALLEL_DOWNLOAD_SUMMARY",
          json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--cdp", default="http://127.0.0.1:9222")
    parser.add_argument("--out", default="hitel-scribd-10parallel-results")
    parser.add_argument("--per-document-timeout", type=int, default=145)
    args = parser.parse_args()
    asyncio.run(main(args))
