#!/usr/bin/env python3
"""Scribd-FIRST download test: documents found ON Scribd, never sourced from Moonzip.

Only download if Scribd permits it in the user's existing authenticated Chrome.
Save PDFs on Windows PC, publish verification METADATA only.
Five concurrent tabs, 20s button clicks (shared tested CDP engine).
"""
import asyncio
import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from playwright.async_api import async_playwright
import scribd_pc_cdp_attach as engine

# These five exact Scribd pages were found by searching Scribd itself or
# publicly indexed Scribd pages on 2026-11-18. They are not from Moonzip.
CANDIDATES = [
    {"document_id":"885710753","original_url":"https://www.scribd.com/document/885710753/%EB%B8%94%EB%9E%99%EB%9D%BC%EB%B2%A8-%EA%B3%B5%ED%86%B5%EC%88%98%ED%95%991-%EB%B3%B8%EC%B1%85","discovered_title":"블랙라벨 공통수학1 본책","expected_subject":"수학","source_page_count":116},
    {"document_id":"829166236","original_url":"https://www.scribd.com/document/829166236/%EB%B8%94%EB%9E%99%EB%9D%BC%EB%B2%A8-%EA%B3%B5%ED%86%B5%EC%88%98%ED%95%991","discovered_title":"블랙라벨 공통수학1","expected_subject":"수학","source_page_count":112},
    {"document_id":"842677237","original_url":"https://www.scribd.com/document/842677237/1-%EC%88%98%EC%97%AC%EB%8F%99%EC%82%AC-25","discovered_title":"수여동사 문법 문제집","expected_subject":"영어","source_page_count":4},
    {"document_id":"1024520867","original_url":"https://www.scribd.com/document/1024520867","discovered_title":"중학교 국어 2-1 평가문제집 정답과 해설","expected_subject":"국어","source_page_count":72},
    {"document_id":"1053898149","original_url":"https://www.scribd.com/document/1053898149/%EC%A4%912-1-%EC%88%98%ED%95%99-%EC%97%B0%EC%82%B0-%EB%AC%B8%EC%A0%9C%EC%A7%91-12p","discovered_title":"중2-1 수학 연산 문제집 12p","expected_subject":"수학","source_page_count":12}
]

def utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

async def main():
    endpoint = "http://127.0.0.1:9222"
    with urlopen(endpoint+"/json/version",timeout=5) as response:
        info=json.loads(response.read(15000))
    if not str(info.get("Browser","")).startswith("Chrome/"):
        raise RuntimeError("Standalone Chrome debugger not ready")
    base=Path(os.environ.get("LOCALAPPDATA") or Path.home())/"HITEL"
    destination=base/"ScribdDownloads"
    output=Path("hitel-scribd-source-first-results").resolve()
    output.mkdir(parents=True,exist_ok=True)
    print("SCRIBD_FIRST_SOURCE_SAMPLE",json.dumps({
        "count":len(CANDIDATES),"ids":[c["document_id"] for c in CANDIDATES],
        "source":"public Scribd document pages, NOT Moonzip",
        "parallel_download_tabs":5,"button_click_timeout_seconds":20,
        "browser":"already-open standalone Chrome on localhost:9222"
    },ensure_ascii=False),flush=True)
    async with async_playwright() as p:
        browser=await p.chromium.connect_over_cdp(endpoint,timeout=15000)
        if not browser.contexts:
            raise RuntimeError("Signed-in Chrome context is unavailable")
        ctx=browser.contexts[0]
        async def worker(candidate,idx):
            started=utc()
            folder=output / candidate["document_id"]
            folder.mkdir(exist_ok=True)
            try:
                # Same script that successfully saved 10/10 documents in
                # two batches of five with 20-second button-click timeouts.
                record=await asyncio.wait_for(engine.one_permitted_download_test(
                    ctx,candidate,destination,folder
                ),timeout=180)
            except Exception as e:
                record={"document_id":candidate["document_id"],
                        "status":"verification_error",
                        "error":(type(e).__name__+": "+str(e))[:230],
                        "download_saved_on_pc":False}
            record.update({
                "source":"Scribd public document",
                "discovered_title":candidate["discovered_title"],
                "expected_subject_unverified":candidate["expected_subject"],
                "source_page_count_unverified":candidate["source_page_count"],
                "source_url":candidate["original_url"],"started_at":started,
                "finished_at":utc(),
                "document_body_and_edition_verified":False,
                "allowed_to_republish_copyrighted_pdf":False,
            })
            print("SCRIBD_FIRST_DOWNLOAD_RESULT",json.dumps({
                "id":record["document_id"],"status":record.get("status"),
                "bytes":record.get("file_size_bytes"),
                "pdf_valid":record.get("pdf_signature_valid")
            },ensure_ascii=False),flush=True)
            return record
        records=await asyncio.gather(*[worker(doc,i) for i,doc in enumerate(CANDIDATES)])
        # DO NOT close the user's standalone Chrome.

    records=sorted(records,key=lambda r:r["document_id"])
    success=sum(bool(r.get("download_saved_on_pc") and r.get("pdf_signature_valid"))
                for r in records)
    summary={
        "tested":len(records),
        "verified_actual_pdf_downloads":success,
        "failed_or_unverified":len(records)-success,
        "scribd_first_discovery":True,
        "moonzip_as_source":False,
        "file_location_on_pc":r"%LOCALAPPDATA%\HITEL\ScribdDownloads",
        "pdfs_uploaded_to_github":0,
        "distinct_documents":len(set(r["document_id"] for r in records)),
        "timestamp":utc(),
    }
    (output/"source-first-download-results.json").write_text(
        json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
    (output/"source-first-summary.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print("SCRIBD_FIRST_FINAL",json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
