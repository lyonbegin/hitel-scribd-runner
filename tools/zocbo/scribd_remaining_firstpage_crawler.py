#!/usr/bin/env python3
"""Browser-based *public* Scribd document preview inspection.

No CAPTCHA solving, bypasses, document downloading, or bulk PDF page copying.
Each accessible document is inspected at its public first preview only.
"""
import argparse, csv, json, re, time
from pathlib import Path
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

CHALLENGE = re.compile(
    r"Client Challenge|CAPTCHA|verify you are human|enter the characters seen|"
    r"security verification|access denied|unusual traffic|checking your browser",
    re.I,
)
PREVIEW_SELECTORS = [
    "[data-e2e='page']",
    "[data-testid='page']",
    "[data-testid*='page-container']",
    "[class*='PageList'] canvas",
    "[class*='pageContainer']",
    "[class*='page_container']",
    "canvas",
]
PROBE_IDS = [] # probe now checks first three IDs in the new unresolved queue

def write_rows(path, records):
    if not records:
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)

def inspect(page, doc_id, out):
    url = "https://www.scribd.com/document/" + doc_id
    row = {
        "document_id": doc_id,
        "source_url": url,
        "final_url": "",
        "status": "error",
        "http_status": None,
        "page_title": "",
        "heading": "",
        "preview_visible": False,
        "body_excerpt": "",
        "screenshot": "",
        "error": "",
        "utc": datetime.now(timezone.utc).isoformat(),
    }
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=35000)
        page.wait_for_timeout(1800)
        row["http_status"] = response.status if response else None
        row["final_url"] = page.url
        row["page_title"] = page.title()[:240]
        try:
            row["heading"] = page.locator("h1").first.inner_text(timeout=1500)[:200] if page.locator("h1").count() else ""
        except Exception:
            pass
        # Clear an optional cookie banner that may obscure document cover text.
        try:
            reject = page.get_by_role("button", name="Reject Non-Essential")
            if reject.count():
                reject.first.click(timeout=1600)
        except Exception:
            pass
        body = page.locator("body").inner_text(timeout=5000)
        row["body_excerpt"] = " ".join(body.split())[:600]
        if CHALLENGE.search(row["page_title"] + " " + body[:1500]):
            row["status"] = "blocked"
        elif row["http_status"] and row["http_status"] >= 400:
            row["status"] = "http_error"
        elif "/document/" not in page.url:
            row["status"] = "unexpected_redirect"
        else:
            row["status"] = "loaded_no_preview"
            # Bring the FIRST publicly visible preview into the viewport.
            for selector in PREVIEW_SELECTORS:
                try:
                    candidate = page.locator(selector).first
                    if candidate.count() and candidate.is_visible(timeout=500):
                        candidate.scroll_into_view_if_needed(timeout=2000)
                        row["preview_visible"] = True
                        break
                except Exception:
                    continue
            if row["preview_visible"]:
                row["status"] = "preview_visible"
            page.wait_for_timeout(800)
        screenshot = out / (f"{doc_id}.png")
        page.screenshot(path=str(screenshot), full_page=False, timeout=12000, animations="disabled")
        row["screenshot"] = str(screenshot)
    except Exception as exc:
        row["error"] = str(exc)[:700]
        try:
            screenshot = out / (f"{doc_id}_error.png")
            page.screenshot(path=str(screenshot), full_page=False, timeout=8000)
            row["screenshot"] = str(screenshot)
        except Exception:
            pass
    print("PREVIEW_RESULT", json.dumps({
        k: row[k] for k in ("document_id", "status", "http_status", "preview_visible", "page_title", "error")
    }, ensure_ascii=True), flush=True)
    return row

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids-file", default="tools/zocbo/remaining_unclassified_2623_ids.txt")
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--batch", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--out", default="scribd_remaining_results")
    args = parser.parse_args()
    all_ids = list(dict.fromkeys(
        x.strip() for x in Path(args.ids_file).read_text(encoding="utf-8").splitlines()
        if re.fullmatch(r"\d{6,12}", x.strip())
    ))
    if len(all_ids) != 2623:
        raise ValueError(f"Expected 2623 IDs, found {len(all_ids)}")
    selected = all_ids[:3] if args.probe else (
        all_ids[args.batch * args.batch_size: (args.batch + 1) * args.batch_size]
    )
    if not selected:
        raise ValueError("No documents in selected batch.")
    target = Path(args.out) / ("probe" if args.probe else f"batch_{args.batch}")
    target.mkdir(parents=True, exist_ok=True)
    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome", headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(locale="ko-KR", viewport={"width": 1366, "height": 950})
        page = context.new_page()
        consecutive_blocks = 0
        for doc_id in selected:
            row = inspect(page, doc_id, target)
            rows.append(row)
            # Persist each completed result so an interrupted batch remains auditable.
            write_rows(target / "results.csv", rows)
            consecutive_blocks = consecutive_blocks + 1 if row["status"] == "blocked" else 0
            # Stop rather than consume 2623 visits on a site-wide challenge.
            if consecutive_blocks >= 3:
                print("STOP_SITE_CHALLENGE three consecutive blocked pages", flush=True)
                break
            page.wait_for_timeout(1100)
        context.close()
        browser.close()
    summary = {
        "input_total": len(all_ids),
        "selected": len(selected),
        "attempted": len(rows),
        "blocked": sum(r["status"] == "blocked" for r in rows),
        "preview_visible": sum(r["preview_visible"] for r in rows),
        "other_loaded": sum(r["status"] == "loaded_no_preview" for r in rows),
        "errors": sum(r["status"] in ("error", "http_error", "unexpected_redirect") for r in rows),
        "not_attempted_in_selected": len(selected) - len(rows),
        "capture_complete": len(rows) == len(selected) and all(r["preview_visible"] for r in rows),
        "site_accessible": any(r["status"] in ("preview_visible", "loaded_no_preview") for r in rows),
        "note": "A successful Actions job is not evidence of PDF access. Inspect per-document status.",
    }
    write_rows(target / "results.csv", rows)
    (target / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("FINAL_PREVIEW_SUMMARY", json.dumps(summary, ensure_ascii=True), flush=True)
    if summary["blocked"] >= 3:
        raise SystemExit(3) # stop the workflow on site-wide access challenge

if __name__ == "__main__":
    main()
