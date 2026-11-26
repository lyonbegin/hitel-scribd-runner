#!/usr/bin/env python3
"""ONE-TIME ten downloads, running at most FIVE concurrent tabs in user Chrome.

Use only the local CDP bridge; never start a browser or access its profile.
Five tabs operate together, then the next five; never ten at once. PDF files stay on this PC; Actions receives
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
from urllib.parse import urlparse
import re

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


def load_classified_queue(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    seen=set(); result=[]
    for row in rows:
        doc_id=row["document_id"]
        url=row["original_url"]
        parsed=urlparse(url)
        if (row.get("download_decision")!="대상" or not doc_id.isdecimal()
            or doc_id in seen or parsed.scheme!="https"
            or parsed.netloc.lower() not in ("scribd.com","www.scribd.com")
            or not re.match(r"^/document/"+re.escape(doc_id)+r"(?:/|$)",parsed.path)):
            raise ValueError("INVALID_CLASSIFIED_QUEUE_ROW")
        seen.add(doc_id)
        result.append({k:row[k] for k in ("document_id","original_title","original_url")})
    if len(result)<10:raise ValueError("CLASSIFIED_QUEUE_HAS_FEWER_THAN_TEN_DOCUMENTS")
    return result

async def main(args):
    if args.cdp != "http://127.0.0.1:9222":
        raise ValueError("CDP must stay on localhost:9222")
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "HITEL"
    checkpoint = local / "ScribdReview" / "unlinked" / "results.csv"
    downloaded_files = local / "ScribdDownloads"
    if args.queue_csv:
        docs=load_classified_queue(args.queue_csv)
        selected=docs[:10]
        prior_previews=0
        scope="classified"
    else:
        docs, selected, prior_previews = choice(Path(args.catalog).resolve(), "unlinked", checkpoint)
        scope="unlinked"
    print("FIVE_PARALLEL_SELECTED", json.dumps({
        "original_queue": len(docs), "previously_verified_preview_with_download_control": prior_previews,
        "ten_distinct_document_ids": [d["document_id"] for d in selected],
        "browser": "separate desktop Chrome", "cdp": "localhost:9222",
        "parallel_tabs": 5, "batches": 2, "click_timeout_ms": 20000, "run_type": "ONE_TIME_SMOKE",
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
            print("FIVE_PARALLEL_TAB_START", json.dumps({
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
            print("FIVE_PARALLEL_TAB_RESULT", json.dumps({
                "tab": index,
                "document_id": item["document_id"],
                "status": result.get("status"),
                "pdf_signature_valid": result.get("pdf_signature_valid"),
                "bytes": result.get("file_size_bytes"),
                "continue_anyway": result.get("continue_anyway_clicked"),
                "final_download_anchor": result.get("final_download_anchor_clicked"),
                "seconds": result["duration_seconds"],
            }, ensure_ascii=False), flush=True)

        # Keep exactly FIVE active download tabs at a time.
        # Ten documents are inspected in TWO nonoverlapping 5-tab batches.
        for batch_no, offset in enumerate(range(0, len(selected), 5), start=1):
            group = selected[offset:offset + 5]
            sync_start.clear()
            print("FIVE_PARALLEL_BATCH_START", json.dumps({
                "batch": batch_no,
                "five_document_ids": [item["document_id"] for item in group],
                "click_timeout_ms": 20000
            }, ensure_ascii=False), flush=True)
            tasks = [asyncio.create_task(worker(item, offset + i + 1))
                     for i, item in enumerate(group)]
            sync_start.set()
            await asyncio.gather(*tasks)
            print("FIVE_PARALLEL_BATCH_DONE", json.dumps({
                "batch": batch_no, "completed": len(group)
            }, ensure_ascii=False), flush=True)
        # Do not browser.close(): user owns Chrome; CDP client just detaches.

    results.sort(key=lambda x: x["tab"])
    (output / "ten-download-results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    successes = sum(r.get("status") == "pdf_saved_on_pc" and
                    r.get("pdf_signature_valid") is True and
                    (r.get("file_size_bytes") or 0) > 0 for r in results)
    counts = dict(Counter(str(r.get("status", "unknown")) for r in results))
    summary = {
        "scope": scope, "original_queue": len(docs),
        "attempted_documents": len(results),
        "simultaneous_tabs": 5,
        "total_batches": 2, "batch_size": 5, "click_timeout_ms": 20000,
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
    print("FIVE_PARALLEL_DOWNLOAD_SUMMARY",
          json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    inputs=parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--catalog")
    inputs.add_argument("--queue-csv",help="Verified classification queue; ten authorized downloads only")
    parser.add_argument("--cdp", default="http://127.0.0.1:9222")
    parser.add_argument("--out", default="hitel-scribd-10parallel-results")
    parser.add_argument("--per-document-timeout", type=int, default=145)
    args = parser.parse_args()
    asyncio.run(main(args))
