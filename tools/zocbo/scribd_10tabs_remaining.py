#!/usr/bin/env python3
"""Inspect public first previews with one Chrome instance and 10 tabs.

Preselected IDs exclude title-resolved documents and all earlier visits.
No document downloading, login, challenge bypass, or automatic retry of previous errors.
"""
import argparse
import asyncio
import base64
import csv
import hashlib
import json
import os
import re
import zlib
from datetime import datetime, timezone
from pathlib import Path
from playwright.async_api import async_playwright

CHALLENGE = re.compile(
    r"Client Challenge|CAPTCHA|verify you are human|enter the characters seen|"
    r"security verification|access denied|unusual traffic|checking your browser", re.I
)
PREVIEW_SELECTORS = (
    "[data-e2e='page']", "[data-testid='page']", "[data-testid*='page-container']",
    "[class*='PageList'] canvas", "[class*='pageContainer']",
    "[class*='page_container']", "canvas",
)
FIELDS = (
    "document_id", "source_url", "final_url", "status", "http_status",
    "page_title", "heading", "preview_visible", "body_excerpt", "screenshot",
    "error", "utc"
)
EXPECTED_COUNT = 1149
EXPECTED_SHA256 = "cf5d264472ed819942872027763cda64c853d0a530476d388b226018a17eeea5"


def read_ids(path):
    path = Path(path)
    raw = path.read_bytes()
    if path.name.endswith((".zlib64", ".zlib.b64")):
        raw = zlib.decompress(base64.b64decode(raw.strip(), validate=True))
    ids = [x.strip() for x in raw.decode("utf-8-sig").splitlines() if x.strip()]
    if (len(ids) != EXPECTED_COUNT or len(set(ids)) != EXPECTED_COUNT
            or any(re.fullmatch(r"\d{6,12}", x) is None for x in ids)):
        raise ValueError(f"Invalid pending queue: count={len(ids)} expected={EXPECTED_COUNT}")
    normalized = ("\n".join(ids) + "\n").encode("utf-8")
    if hashlib.sha256(normalized).hexdigest() != EXPECTED_SHA256:
        raise ValueError("Pending ID queue SHA256 does not match audited list")
    return ids


def read_previously_visited(path):
    """Read GitHub-audited visit log; exclude even previously failed/redirected visits."""
    if not path:
        return set()
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Visit checkpoint missing: {source}")
    seen = set()
    for line in source.read_text(encoding="utf-8-sig").splitlines():
        first = line.split(",", 1)[0].strip()
        if re.fullmatch(r"\d{6,12}", first):
            seen.add(first)
    return seen


def save_atomic_csv(path, rows):
    tmp = path.with_name(path.name + ".new")
    with tmp.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)


def save_atomic_json(path, data):
    tmp = path.with_name(path.name + ".new")
    tmp.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
    os.replace(tmp, path)


async def inspect(page, doc_id, output):
    url = "https://www.scribd.com/document/" + doc_id
    row = dict.fromkeys(FIELDS, "")
    row.update(document_id=doc_id, source_url=url, status="error", preview_visible=False,
               utc=datetime.now(timezone.utc).isoformat())
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=35000)
        await page.wait_for_timeout(1800)
        row["http_status"] = response.status if response else None
        row["final_url"] = page.url
        row["page_title"] = (await page.title())[:240]
        try:
            heading = page.locator("h1").first
            if await heading.count():
                row["heading"] = (await heading.inner_text(timeout=1500))[:200]
        except Exception:
            pass
        try:
            reject = page.get_by_role("button", name="Reject Non-Essential")
            if await reject.count():
                await reject.first.click(timeout=1600)
        except Exception:
            pass
        body = await page.locator("body").inner_text(timeout=5000)
        row["body_excerpt"] = " ".join(body.split())[:600]
        if CHALLENGE.search(row["page_title"] + " " + body[:1500]):
            row["status"] = "blocked"
        elif row["http_status"] and row["http_status"] >= 400:
            row["status"] = "http_error"
        elif "/document/" not in page.url:
            row["status"] = "unexpected_redirect"
        else:
            row["status"] = "loaded_no_preview"
            for selector in PREVIEW_SELECTORS:
                try:
                    candidate = page.locator(selector).first
                    if await candidate.count() and await candidate.is_visible(timeout=500):
                        await candidate.scroll_into_view_if_needed(timeout=2000)
                        row["preview_visible"] = True
                        break
                except Exception:
                    continue
            if row["preview_visible"]:
                row["status"] = "preview_visible"
            await page.wait_for_timeout(800)
        picture = output / f"{doc_id}.png"
        await page.screenshot(path=str(picture), full_page=False, timeout=12000, animations="disabled")
        row["screenshot"] = str(picture)
    except Exception as error:
        row["error"] = str(error)[:700]
        try:
            picture = output / f"{doc_id}_error.png"
            await page.screenshot(path=str(picture), full_page=False, timeout=8000)
            row["screenshot"] = str(picture)
        except Exception:
            pass
    return row


async def run(args, ids):
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    results_path = output / "results.csv"
    existing = []
    if results_path.exists():
        with results_path.open(newline="", encoding="utf-8-sig") as file:
            existing = list(csv.DictReader(file))
    prior_2026_11_12 = read_previously_visited(args.skip_prior_file)
    prior_2026_11_13 = read_previously_visited(args.skip_current_file)
    excluded = (prior_2026_11_12 | prior_2026_11_13) & set(ids)
    known = {row["document_id"] for row in existing if row.get("document_id") in ids}
    pending = [doc_id for doc_id in ids if doc_id not in known and doc_id not in excluded]
    rows = [row for row in existing if row.get("document_id") in ids]
    eligible_total = len(ids) - len(excluded)
    print(f"QUEUE total={len(ids)} previously_visited_in_queue={len(excluded)} "
          f"eligible={eligible_total} resumed={len(known)} remaining={len(pending)} tabs={args.tabs}", flush=True)
    if not pending:
        return summarize(ids, rows, output, stopped=False, excluded=excluded)

    queue = asyncio.Queue()
    for doc_id in pending:
        queue.put_nowait(doc_id)
    stop = asyncio.Event()
    block_count = 0
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            channel="chrome", headless=args.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(locale="ko-KR", viewport={"width": 1366, "height": 950})

        async def worker(number):
            nonlocal block_count
            page = await context.new_page()
            try:
                while not stop.is_set():
                    try:
                        doc_id = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    result = await inspect(page, doc_id, output)
                    rows.append(result)
                    save_atomic_csv(results_path, rows)
                    print("PREVIEW_RESULT", json.dumps({
                        "tab": number, "done": len(rows), "total": len(ids),
                        "document_id": doc_id, "status": result["status"],
                        "preview_visible": result["preview_visible"]}, ensure_ascii=True), flush=True)
                    if result["status"] == "blocked":
                        block_count += 1
                        if block_count >= 3:
                            stop.set()
                            print("STOP_SITE_CHALLENGE: 3 blocked pages", flush=True)
                    queue.task_done()
                    if not stop.is_set():
                        await page.wait_for_timeout(1100)
            finally:
                await page.close()
        await asyncio.gather(*(worker(i + 1) for i in range(args.tabs)))
        await context.close()
        await browser.close()
    return summarize(ids, rows, output, stopped=stop.is_set(), excluded=excluded)


def summarize(ids, rows, output, stopped, excluded):
    statuses = {}
    for row in rows:
        statuses[row.get("status", "unknown")] = statuses.get(row.get("status", "unknown"), 0) + 1
    summary = {
        "queue_total": len(ids), "previously_visited_excluded": len(excluded),
        "eligible_total": len(ids) - len(excluded),
        "completed_or_attempted": len(rows),
        "left_unattempted": len(ids) - len(excluded) - len(rows),
        "preview_visible": statuses.get("preview_visible", 0),
        "status_counts": statuses, "stopped_on_challenge": stopped,
        "browser_count": 1, "concurrent_tabs": 10,
        "title_resolved_or_prior_attempts_in_queue": 0,
        "note": "First public preview only; not a PDF download or a completed book verification."
    }
    save_atomic_json(output / "summary.json", summary)
    print("FINAL_REVIEW_SUMMARY", json.dumps(summary, ensure_ascii=True), flush=True)
    return 2 if stopped else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids-file", default="tools/zocbo/pending_1149_ids.zlib64")
    parser.add_argument("--out", default="scribd-review-results")
    parser.add_argument("--tabs", type=int, default=10)
    parser.add_argument("--skip-prior-file", default="tools/zocbo/attempted_43224551981_ids.txt")
    parser.add_argument("--skip-current-file", default="tools/zocbo/attempted_43344449923_ids.csv")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.tabs != 10:
        parser.error("This audited workflow uses exactly ten tabs")
    ids = read_ids(args.ids_file)
    if args.dry_run:
        previous = read_previously_visited(args.skip_prior_file) | read_previously_visited(args.skip_current_file)
        excluded = set(ids) & previous
        print(json.dumps({"count": len(ids), "unique": len(set(ids)), 
                          "previously_visited_excluded": len(excluded),
                          "eligible": len(ids) - len(excluded),
                          "first": ids[:3], "last": ids[-3:]}, ensure_ascii=True))
        return
    raise SystemExit(asyncio.run(run(args, ids)))


if __name__ == "__main__":
    main()
