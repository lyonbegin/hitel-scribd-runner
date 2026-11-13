#!/usr/bin/env python3
"""Resumable public Scribd first-preview review with ten bounded Chrome tabs.

The input is an audited document-ID queue, not a web search. Previously attempted
IDs (including redirects/errors) and prior artifact results are excluded.
This script does not download PDFs, log in, or bypass access challenges.
"""
import argparse
import asyncio
import base64
import csv
import hashlib
import json
import os
import re
import tempfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

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
KNOWN_1149_SHA = "cf5d264472ed819942872027763cda64c853d0a530476d388b226018a17eeea5"


def read_ids(path):
    source = Path(path)
    data = source.read_bytes()
    if source.name.endswith((".zlib64", ".zlib.b64")):
        data = zlib.decompress(base64.b64decode(data.strip(), validate=True))
    ids = [line.strip() for line in data.decode("utf-8-sig").splitlines() if line.strip()]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r"\d{6,12}", x) for x in ids):
        raise ValueError("ID queue must contain unique numeric document IDs")
    expected = 1149 if "pending_1149" in source.name else (
        2623 if "remaining_unclassified_2623" in source.name else None
    )
    if expected is not None and len(ids) != expected:
        raise ValueError(f"Audited queue size mismatch: {len(ids)} != {expected}")
    if expected == 1149:
        digest = hashlib.sha256(("\n".join(ids) + "\n").encode()).hexdigest()
        if digest != KNOWN_1149_SHA:
            raise ValueError("Audited 1149 queue checksum mismatch")
    return ids


def prior_ids(path):
    if not path:
        return set()
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Required visit checkpoint missing: {source}")
    seen = set()
    for line in source.read_text(encoding="utf-8-sig").splitlines():
        first = line.split(",", 1)[0].strip()
        if re.fullmatch(r"\d{6,12}", first):
            seen.add(first)
    return seen


def csv_rows(path):
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Required artifact CSV missing: {source}")
    with source.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or "document_id" not in rows[0]:
        raise ValueError(f"Invalid or empty checkpoint CSV: {source}")
    return rows


def atomic_csv(path, rows):
    tmp = path.with_name(path.name + ".new")
    with tmp.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)


def atomic_json(path, value):
    tmp = path.with_name(path.name + ".new")
    tmp.write_text(json.dumps(value, ensure_ascii=True, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def result_error(doc_id, kind, message):
    return {
        **dict.fromkeys(FIELDS, ""),
        "document_id": doc_id,
        "source_url": f"https://www.scribd.com/document/{doc_id}",
        "status": kind, "preview_visible": False,
        "error": str(message)[:700], "utc": datetime.now(timezone.utc).isoformat()
    }


async def inspect(page, doc_id, output):
    row = result_error(doc_id, "error", "")
    try:
        response = await page.goto(row["source_url"], wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(1200)
        row["http_status"] = response.status if response else ""
        row["final_url"] = page.url
        # Playwright page.title() stalled prior 10-tab jobs. Title metadata is optional.
        # Use a bounded DOM locator and continue checking the preview on failure.
        try:
            row["page_title"] = ((await page.locator("title").first.text_content(timeout=1800)) or "")[:240]
        except Exception as exc:
            row["error"] = f"title_lookup_optional:{type(exc).__name__}"
        try:
            heading = page.locator("h1").first
            if await heading.count():
                row["heading"] = (await heading.inner_text(timeout=1500))[:200]
        except Exception:
            pass
        try:
            reject = page.get_by_role("button", name="Reject Non-Essential")
            if await reject.count():
                await reject.first.click(timeout=1500)
        except Exception:
            pass
        body = await page.locator("body").inner_text(timeout=4500)
        row["body_excerpt"] = " ".join(body.split())[:600]
        if CHALLENGE.search(row["page_title"] + " " + body[:1500]):
            row["status"] = "blocked"
        elif row["http_status"] and int(row["http_status"]) >= 400:
            row["status"] = "http_error"
        elif "/document/" not in page.url:
            row["status"] = "unexpected_redirect"
        else:
            row["status"] = "loaded_no_preview"
            for selector in PREVIEW_SELECTORS:
                try:
                    candidate = page.locator(selector).first
                    if await candidate.count() and await candidate.is_visible(timeout=500):
                        await candidate.scroll_into_view_if_needed(timeout=1500)
                        row["preview_visible"] = True
                        row["status"] = "preview_visible"
                        break
                except Exception:
                    continue
        screenshot = output / f"{doc_id}.png"
        try:
            await page.screenshot(path=str(screenshot), full_page=False,
                                  timeout=10000, animations="disabled")
            row["screenshot"] = str(screenshot)
        except Exception as exc:
            row["error"] = ("Screenshot: " + str(exc))[:700]
    except Exception as exc:
        row["status"] = "timeout" if isinstance(exc, asyncio.TimeoutError) else "error"
        row["error"] = f"inspect:{type(exc).__name__}: {str(exc)}"[:700]
    return row


def silence_future(task):
    if task.cancelled():
        return
    try:
        task.exception()
    except Exception:
        pass


async def bounded(awaitable, seconds):
    """Enforce a hard await budget even when a Playwright cancellation stalls."""
    task = asyncio.create_task(awaitable)
    task.add_done_callback(silence_future)
    done, _ = await asyncio.wait({task}, timeout=seconds)
    if not done:
        task.cancel()
        raise asyncio.TimeoutError(f"Operation exceeded {seconds}s")
    return task.result()


async def review_document(context, doc_id, output, args):
    for attempt in range(args.retries + 1):
        page = None
        try:
            page = await bounded(context.new_page(), 20)
            row = await bounded(inspect(page, doc_id, output), args.document_timeout)
        except asyncio.TimeoutError as exc:
            row = result_error(doc_id, "timeout", str(exc))
        except Exception as exc:
            row = result_error(doc_id, "error", f"{type(exc).__name__}: {str(exc)}")
        finally:
            if page is not None:
                try:
                    await bounded(page.close(run_before_unload=False), 5)
                except Exception:
                    pass
        if row["status"] not in ("timeout", "error") or attempt == args.retries:
            return row
        print("RETRY", json.dumps({"document_id": doc_id, "attempt": attempt + 2,
                                   "reason": row["status"]}), flush=True)
        await asyncio.sleep(0.5)
    return result_error(doc_id, "error", "Retry exhausted")


def summarize(ids, excluded, rows, output, reason, tabs):
    counts = {}
    for row in rows:
        status = row.get("status") or "unknown"
        counts[status] = counts.get(status, 0) + 1
    previous = len(excluded)
    eligible = len(ids) - previous
    summary = {
        "queue_total": len(ids),
        "previously_attempted_excluded": previous,
        "eligible_new_total": eligible,
        "newly_attempted": len(rows),
        "remaining_new": max(0, eligible - len(rows)),
        "preview_visible_new": counts.get("preview_visible", 0),
        "status_counts": counts, "stop_reason": reason,
        "browser_instances_per_batch": 1, "concurrent_tabs": tabs,
        "note": "Public first preview only; not PDF download or full-book verification."
    }
    atomic_json(output / "summary.json", summary)
    print("FINAL_REVIEW_SUMMARY", json.dumps(summary), flush=True)
    return summary


async def crawl(args, ids):
    # Restore the previous Action artifact into a separate directory; never overwrite it.
    prior = set()
    for path in (args.skip_prior_file, args.skip_current_file, args.skip_latest_file):
        prior |= prior_ids(path)
    if args.prior_results_file:
        prior |= {r["document_id"] for r in csv_rows(args.prior_results_file)}
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    results_path = output / "results.csv"
    rows = csv_rows(results_path) if results_path.exists() else []
    allowed = set(ids)
    rows = [r for r in rows if r.get("document_id") in allowed]
    deduped = {}
    for row in rows:
        deduped[row["document_id"]] = row
    rows = list(deduped.values())
    excluded = prior & allowed
    already = {r["document_id"] for r in rows}
    excluded |= already
    pending = [doc_id for doc_id in ids if doc_id not in excluded]
    print(f"QUEUE total={len(ids)} excluded_previous={len(excluded)} "
          f"eligible_new={len(pending)} resumed_new={len(already)} "
          f"tabs={args.tabs} batch_size={args.batch_size}", flush=True)
    if args.dry_run:
        summarize(ids, excluded - already, rows, output, "dry_run", args.tabs)
        return 0
    if args.limit:
        pending = pending[:args.limit]
        print(f"PROBE_LIMIT selected={len(pending)}", flush=True)
    if not pending:
        summarize(ids, excluded - already, rows, output, "nothing_new", args.tabs)
        return 0

    # Previous visits excluded from this run, excluding current output rows.
    old_excluded = excluded - already
    blocked = 0
    fatal = None
    from playwright.async_api import async_playwright

    for start in range(0, len(pending), args.batch_size):
        batch = pending[start:start + args.batch_size]
        q = asyncio.Queue()
        for doc_id in batch:
            q.put_nowait(doc_id)
        stop = asyncio.Event()
        try:
            # Restart Chrome and its context between batches to cap long-running resource leaks.
            async with async_playwright() as playwright:
                browser = await bounded(playwright.chromium.launch(
                    channel="chrome", headless=args.headless,
                    args=["--no-sandbox", "--disable-dev-shm-usage"]
                ), 45)
                context = await bounded(browser.new_context(
                    locale="ko-KR", viewport={"width": 1366, "height": 950}
                ), 25)

                async def worker(number):
                    nonlocal blocked, fatal
                    while not stop.is_set():
                        try:
                            doc_id = q.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                        row = await review_document(context, doc_id, output, args)
                        # A dead browser is not a valid visit: keep it for later recovery.
                        if row["status"] == "error" and (
                            "TargetClosedError" in row["error"] or
                            "Target page, context or browser has been closed" in row["error"]
                        ):
                            fatal = "browser_disconnected"
                            stop.set()
                            q.task_done()
                            break
                        rows.append(row)
                        atomic_csv(results_path, rows)
                        print("PREVIEW_RESULT", json.dumps({
                            "tab": number, "done_new": len(rows),
                            "document_id": doc_id, "status": row["status"],
                            "preview_visible": row["preview_visible"]
                        }), flush=True)
                        if row["status"] == "blocked":
                            blocked += 1
                            if blocked >= 3:
                                stop.set()
                                fatal = "site_challenge"
                                print("STOP_SITE_CHALLENGE blocked=3", flush=True)
                        q.task_done()
                        if not stop.is_set():
                            await asyncio.sleep(0.4)

                tasks = [asyncio.create_task(worker(n + 1)) for n in range(args.tabs)]
                try:
                    done, unfinished = await asyncio.wait(tasks, timeout=args.batch_timeout)
                    if unfinished:
                        fatal = "batch_watchdog_timeout"
                        stop.set()
                        for task in unfinished:
                            task.cancel()
                        print("BATCH_WATCHDOG_TIMEOUT", json.dumps({
                            "batch_start": start, "unfinished_workers": len(unfinished)
                        }), flush=True)
                    for task in done:
                        if not task.cancelled() and task.exception():
                            raise task.exception()
                finally:
                    try:
                        await bounded(context.close(), 12)
                    except Exception:
                        pass
                    try:
                        await bounded(browser.close(), 12)
                    except Exception:
                        pass
        except Exception as exc:
            fatal = fatal or ("browser_failure: " + str(exc)[:200])
            print("BROWSER_FAILURE", json.dumps({"reason": fatal}), flush=True)
        summarize(ids, old_excluded, rows, output, fatal or "batch_checkpoint", args.tabs)
        if fatal:
            break
    summary = summarize(ids, old_excluded, rows, output, fatal or "complete", args.tabs)
    if fatal:
        return 2
    if not args.limit and summary["remaining_new"]:
        return 3
    return 0


def self_test():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "results.csv"
        row = result_error("123456789", "preview_visible", "")
        atomic_csv(path, [row])
        loaded = csv_rows(path)
        assert len(loaded) == 1 and loaded[0]["document_id"] == "123456789"
        ckpt = Path(directory) / "visits.csv"
        ckpt.write_text("# comment\n123456789,preview_visible\n111111111,error\n", encoding="utf-8")
        assert prior_ids(ckpt) == {"123456789", "111111111"}

        async def test_timeout():
            async def stuck():
                await asyncio.sleep(10)
            try:
                await bounded(stuck(), 0.02)
            except asyncio.TimeoutError:
                return True
            return False
        assert asyncio.run(test_timeout()), "Per-document watchdog failed"
    print("SELF_TEST_OK checkpoint_io=1 exclusion=1 async_timeout=1", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids-file", default="tools/zocbo/remaining_unclassified_2623_ids.txt")
    parser.add_argument("--skip-prior-file", default="tools/zocbo/attempted_43224551981_ids.txt")
    parser.add_argument("--skip-current-file", default="tools/zocbo/attempted_43344449923_ids.csv")
    parser.add_argument("--skip-latest-file", default="tools/zocbo/attempted_43377032832_from_logs.csv")
    parser.add_argument("--prior-results-file", default="",
                        help="Optional verified prior results.csv; existing attempt-ID checkpoints also apply")
    parser.add_argument("--out", default="scribd-remaining-results")
    parser.add_argument("--tabs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=80)
    parser.add_argument("--document-timeout", type=int, default=80)
    parser.add_argument("--batch-timeout", type=int, default=1200)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.tabs != 10 or args.batch_size < 10 or not 20 <= args.document_timeout <= 180:
        parser.error("Use 10 tabs, batch_size >= 10, and timeout between 20 and 180s")
    if not 60 <= args.batch_timeout <= 3600 or args.retries not in (0, 1, 2):
        parser.error("Invalid batch timeout or retry count")
    ids = read_ids(args.ids_file)
    raise SystemExit(asyncio.run(crawl(args, ids)))


if __name__ == "__main__":
    main()
