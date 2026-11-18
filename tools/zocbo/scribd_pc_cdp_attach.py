#!/usr/bin/env python3
"""Attach Playwright to standalone Chrome via localhost-only Chrome DevTools Protocol.

The user launches Chrome independently with a dedicated PC-local profile and
signs into Scribd BEFORE the GitHub Windows runner connects over CDP.
This program NEVER starts a browser, opens an automated Google sign-in page,
or exports browser cookies/profile. Only permitted public previews and one
explicitly requested, authorized download may be tested.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

CHALLENGE = re.compile(
    r"Client Challenge|captcha|verify you are human|a required part of this site couldn't load|"
    r"checking your browser|access denied|security verification", re.I
)
PAYMENT_HOLD = re.compile(
    r"Problem with your last payment|Your membership is on hold|"
    r"Your credit card information is invalid", re.I
)
PREVIEW_SELECTORS = (
    "[data-e2e='page']", "[data-testid='page']", "[data-testid*='page-container']",
    "[class*='PageList'] canvas", "[class*='pageContainer']", "canvas"
)
FIELDS = (
    "document_id", "original_title", "original_url", "final_url", "http_status",
    "page_title", "heading", "status", "preview_visible", "download_button_visible",
    "payment_warning_seen", "continue_anyway_clicked", "screenshot", "error", "checked_utc"
)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_documents(catalog_dir: Path, scope: str):
    manifest = json.loads((catalog_dir / "manifest.json").read_text(encoding="utf-8"))
    columns = manifest["schema"]["materials"]
    documents = {}
    for part in manifest["files"]:
        if part["type"] != "materials":
            continue
        source = json.loads((catalog_dir / part["file"]).read_text(encoding="utf-8"))
        for values in source["rows"]:
            record = dict(zip(columns, values))
            doc_id = str(record["id"])
            url = str(record.get("reference_url") or record.get("source_url") or "").strip()
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.netloc.lower() not in ("scribd.com", "www.scribd.com"):
                continue
            if not re.match(r"^/document/" + re.escape(doc_id) + r"(?:/|$)", parsed.path):
                continue
            documents[doc_id] = {"document_id": doc_id, "original_title": str(record.get("title") or ""),
                                 "original_url": url}
    if scope == "unlinked":
        ids = [v.strip() for v in (catalog_dir / "investigation-1208-ids.txt").read_text(encoding="utf-8").splitlines() if v.strip()]
        if len(ids) != 1208 or len(set(ids)) != 1208:
            raise ValueError("Saved original 1208-ID source list is incomplete")
        missing = [doc_id for doc_id in ids if doc_id not in documents]
        if missing:
            raise ValueError(f"Saved original URLs missing for {len(missing)} IDs")
        return [documents[doc_id] for doc_id in ids]
    if scope == "all":
        if len(documents) < 2000:
            raise ValueError(f"Expected the original 2000+ Scribd material links; got {len(documents)}")
        return list(documents.values())
    raise ValueError(scope)


def save_csv(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".new")
    with tmp.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(data)
    os.replace(tmp, path)


def load_csv(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


async def dismiss_continue_anyway(page):
    """Only dismiss the warning; NEVER touch payment details or payment buttons."""
    try:
        buttons = page.get_by_role("button", name=re.compile(r"continue anyway", re.I))
        if await buttons.count() and await buttons.first.is_visible(timeout=900):
            await buttons.first.click(timeout=2500)
            return True
    except Exception:
        pass
    return False


async def body_text(page):
    try:
        return (await page.locator("body").inner_text(timeout=4200))[:6000]
    except Exception:
        return ""


async def get_title(page):
    try:
        return ((await page.locator("title").first.text_content(timeout=1500)) or "")[:240]
    except Exception:
        return ""


async def review_one(context, item, shots_dir: Path, index: int, save_success_screens: bool):
    result = {key: "" for key in FIELDS}
    result.update(item)
    result["checked_utc"] = utc_now()
    result["preview_visible"] = False
    result["download_button_visible"] = False
    result["payment_warning_seen"] = False
    result["continue_anyway_clicked"] = False
    page = await context.new_page()
    try:
        response = await page.goto(item["original_url"], wait_until="domcontentloaded", timeout=35000)
        result["http_status"] = response.status if response else None
        await page.wait_for_timeout(1200)
        before = await body_text(page)
        result["payment_warning_seen"] = bool(PAYMENT_HOLD.search(before))
        result["continue_anyway_clicked"] = await dismiss_continue_anyway(page)
        if result["continue_anyway_clicked"]:
            await page.wait_for_timeout(500)
        result["final_url"] = page.url
        result["page_title"] = await get_title(page)
        try:
            result["heading"] = " | ".join(await page.locator("h1").all_inner_texts())[:200]
        except Exception:
            pass
        body = await body_text(page)
        result["payment_warning_seen"] = result["payment_warning_seen"] or bool(PAYMENT_HOLD.search(body))
        download_controls = page.get_by_role("button", name=re.compile(r"^download(\s|$)", re.I))
        try:
            result["download_button_visible"] = (await download_controls.count() > 0
                                                 and await download_controls.first.is_visible(timeout=600))
        except Exception:
            pass

        if CHALLENGE.search(result["page_title"] + " " + body[:2500]):
            result["status"] = "client_challenge"
        elif result["http_status"] and int(result["http_status"]) >= 400:
            result["status"] = "http_error"
        elif "/document/" not in page.url:
            result["status"] = "unexpected_redirect"
        else:
            result["status"] = "loaded_no_preview"
            for selector in PREVIEW_SELECTORS:
                try:
                    loc = page.locator(selector).first
                    if await loc.count() and await loc.is_visible(timeout=750):
                        result["status"] = "preview_visible"
                        result["preview_visible"] = True
                        break
                except Exception:
                    pass
        if result["status"] != "preview_visible" or save_success_screens:
            screenshot = shots_dir / f"{index:04d}-{item['document_id']}.png"
            try:
                await page.screenshot(path=str(screenshot), full_page=False, timeout=8000)
                result["screenshot"] = screenshot.name
            except Exception as e:
                result["error"] = "screenshot:" + type(e).__name__
    except Exception as e:
        result["status"] = "error"
        result["error"] = (type(e).__name__ + ": " + str(e))[:280]
    finally:
        await page.close()
    return result


async def one_permitted_download_test(context, item, destination: Path, results_dir: Path):
    """Test one user's authorized PDF download with the actual Scribd modal DOM.

    Exact workflow: open supplied full URL; dismiss Continue anyway if shown;
    open Download modal if needed; confirm PDF; click the actual anchor
    <a data-e2e="modal-download-button">Download document</a>;
    handle a further Continue anyway if shown; verify a browser download and
    saved PDF on the Windows PC. No direct file URL is invented.
    """
    given_url = (
        "https://www.scribd.com/document/1061417751/"
        "%EB%82%B4%EA%B3%B5%EC%9D%98-%ED%9E%98-%EC%A4%911-1-2013-"
        "%EB%B9%84%EC%83%81-%EA%B5%90%EC%9E%AC-Black#"
    )
    target_url = given_url if item["document_id"] == "1061417751" else item["original_url"]
    result = {
        "document_id": item["document_id"],
        "attempted_url": target_url,
        "status": "not_started",
        "download_saved_on_pc": False,
        "initial_download_clicked": False,
        "continue_anyway_clicked": False,
        "final_download_anchor_clicked": False,
        "pdf_format_verified": False,
        "steps": [],
        "click_timeout_ms": 20000,
    }
    page = await context.new_page()
    download_future = asyncio.get_running_loop().create_future()

    def on_download(download):
        if not download_future.done():
            download_future.set_result(download)

    page.on("download", on_download)
    try:
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            result["steps"].append("full_user_url_opened")
        except Exception as exc:
            # A download may cause page navigation to abort.
            result["navigation_note"] = (type(exc).__name__ + ": " + str(exc))[:180]
        result["final_url"] = page.url

        modal_anchor = page.locator(
            '[role="dialog"][data-e2e="modal"] a[data-e2e="modal-download-button"]'
        )
        payment_button = page.get_by_role("button", name=re.compile(r"^Continue anyway$", re.I))

        async def is_visible(locator):
            try:
                return bool(await locator.count() and await locator.first.is_visible(timeout=600))
            except Exception:
                return False

        async def click_continue():
            if await is_visible(payment_button):
                await payment_button.first.click(timeout=20_000)
                result["continue_anyway_clicked"] = True
                result["steps"].append("payment_continue_anyway_clicked")
                return True
            return False

        async def click_pdf_modal_anchor():
            if not await is_visible(modal_anchor):
                return False
            # User-provided HTML shows role=combobox "PDF (4.96 MB)" and
            # a final clickable <a> rather than a <button>.
            modal = page.locator('[role="dialog"][data-e2e="modal"]').filter(
                has=page.locator('a[data-e2e="modal-download-button"]')
            ).first
            selector = modal.get_by_role("combobox")
            selected_format = ""
            if await selector.count():
                selected_format = (await selector.first.inner_text(timeout=2500)).strip()
            result["selected_format"] = selected_format
            if not re.search(r"^PDF\b", selected_format, re.I):
                result["status"] = "modal_format_not_pdf"
                result["steps"].append("download_modal_format_not_pdf")
                return False
            result["pdf_format_verified"] = True
            result["steps"].append("download_modal_pdf_verified")
            await modal_anchor.first.click(timeout=20_000)
            result["final_download_anchor_clicked"] = True
            result["steps"].append("modal_download_anchor_clicked")
            return True

        # Direct URL is used first, as requested; only the actual site UI
        # can start the browser download if navigation did not.
        initial_download_attempted = False
        modal_clicks = 0
        for _ in range(48):
            if download_future.done():
                break
            # Membership hold may appear before OR after the download dialog.
            if await click_continue():
                await page.wait_for_timeout(300)
                continue
            if await is_visible(modal_anchor):
                if result.get("status") == "modal_format_not_pdf":
                    break
                if modal_clicks < 2:
                    did_click = await click_pdf_modal_anchor()
                    if did_click:
                        modal_clicks += 1
                else:
                    result["steps"].append("download_modal_reappeared_twice_no_retry")
                    break
                await page.wait_for_timeout(450)
                continue
            if not initial_download_attempted:
                # When the supplied /document/ID/slug URL only loads a detail
                # page, the site's actual Download control is necessary to
                # open the modal. Avoid treating the URL as a direct file link.
                detail_button = page.get_by_role(
                    "button", name=re.compile(r"^Download$", re.I)
                )
                detail_link = page.get_by_role(
                    "link", name=re.compile(r"^Download$", re.I)
                )
                control = detail_button if await is_visible(detail_button) else detail_link
                if await is_visible(control):
                    await control.first.click(timeout=20_000)
                    initial_download_attempted = True
                    result["initial_download_clicked"] = True
                    result["steps"].append("detail_download_opens_modal")
                    await page.wait_for_timeout(350)
                    continue
            await page.wait_for_timeout(400)

        if not download_future.done() and result.get("status") != "modal_format_not_pdf":
            try:
                await asyncio.wait_for(asyncio.shield(download_future), timeout=10)
            except asyncio.TimeoutError:
                pass

        if download_future.done():
            download = download_future.result()
            failure = await download.failure()
            if failure:
                result["status"] = "browser_download_failed"
                result["download_failure"] = str(failure)[:250]
            else:
                destination.mkdir(parents=True, exist_ok=True)
                safe = re.sub(r"[^\w.\-가-힣]+", "_", download.suggested_filename)[:110]
                path = destination / (item["document_id"] + "_" + (safe or "document.pdf"))
                await download.save_as(path)
                size = path.stat().st_size
                with path.open("rb") as fp:
                    signature = fp.read(5)
                result["local_file_name"] = path.name
                result["file_size_bytes"] = size
                result["pdf_signature_valid"] = signature == b"%PDF-"
                result["download_saved_on_pc"] = size > 0 and signature == b"%PDF-"
                result["status"] = ("pdf_saved_on_pc" if result["download_saved_on_pc"]
                                    else "file_saved_but_pdf_not_verified")
                result["steps"].append("download_event_and_file_checked")
        elif result.get("status") != "modal_format_not_pdf":
            result["status"] = "no_download_event"
            result["steps"].append("no_browser_download_event")
            result["final_url"] = page.url
            result["final_modal_anchor_visible"] = await is_visible(modal_anchor)
            result["payment_continue_visible"] = await is_visible(payment_button)
            try:
                await page.screenshot(
                    path=str(results_dir / "one-download-modal-result.png"),
                    full_page=False, timeout=6000
                )
            except Exception:
                pass
    except Exception as exc:
        result["status"] = "download_test_exception"
        result["error"] = (type(exc).__name__ + ": " + str(exc))[:300]
    finally:
        page.remove_listener("download", on_download)
        await page.close()
    return result

async def main_async(args):
    catalog = Path(args.catalog_dir).resolve()
    items = load_documents(catalog, args.scope)
    total = len(items)
    selected = items[:args.limit] if args.limit else items
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    shots = output / "screenshots"
    shots.mkdir(exist_ok=True)

    pc_base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    # The Chrome process and profile are started separately by the user.
    # Only local checkpoints/downloads live here. NO profile or cookie access.
    checkpoint = pc_base / "HITEL" / "ScribdReview" / args.scope / "results.csv"
    downloads = pc_base / "HITEL" / "ScribdDownloads"
    previous = load_csv(checkpoint) if args.resume else []
    by_id = {row["document_id"]: row for row in previous
             if row.get("status") not in ("error", "timeout", "client_challenge")}
    pending = [item for item in selected if item["document_id"] not in by_id]
    print("SAVED_LINKS", json.dumps({"scope": args.scope, "source_total": total,
         "selected": len(selected), "already_checked": len(selected)-len(pending),
         "pending": len(pending), "tabs": 10, "headless": False,
         "chrome_launched_independently": True, "cdp_endpoint": "localhost_only"}, ensure_ascii=False), flush=True)

    results = list(by_id.values())

    # Attach to an EXISTING standalone Chrome only, after the user signed in.
    # This must not launch a Playwright-controlled Chrome or open a Google login page.
    if args.cdp_endpoint != "http://127.0.0.1:9222":
        raise ValueError("Only the local Chrome debug endpoint 127.0.0.1:9222 is permitted")
    from urllib.request import urlopen
    try:
        with urlopen(args.cdp_endpoint + "/json/version", timeout=5) as response:
            cdp_info = json.loads(response.read(10000).decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(
            "LOCAL_CDP_OFFLINE: First run ops/start-scribd-cdp-chrome.ps1 on this PC, "
            "then sign into Scribd in that Chrome window before starting GitHub Actions"
        ) from exc
    if "Chrome/" not in str(cdp_info.get("Browser", "")):
        raise RuntimeError("LOCAL_CDP_WRONG_BROWSER: localhost:9222 is not a Google Chrome endpoint")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(args.cdp_endpoint, timeout=15000)
        if not browser.contexts:
            raise RuntimeError("LOCAL_CDP_NO_DEFAULT_CONTEXT")
        context = browser.contexts[0]
        login_mode = "standalone_chrome_local_cdp_existing_profile"
        print("STANDALONE_CHROME_CDP_ATTACHED", json.dumps({
            "host": "127.0.0.1", "port": 9222,
            "existing_browser": True, "headless": False,
            "login_by_user_before_attach": True,
            "chrome_profile_not_exported": True
        }, ensure_ascii=False), flush=True)
        try:
            first_batch = True
            new_reviewed = []
            stop_reason = "finished"
            for start in range(0, len(pending), 10):
                batch = pending[start:start+10]
                tasks = [review_one(context, item, shots, start+i,
                                    args.limit > 0 and start == 0) for i,item in enumerate(batch)]
                for row in await asyncio.gather(*tasks):
                    by_id[row["document_id"]] = row
                    new_reviewed.append(row)
                    results = list(by_id.values())
                    save_csv(checkpoint, results)
                    print("SIGNED_IN_CHROME_RESULT", json.dumps({
                        "document_id": row["document_id"], "status": row["status"],
                        "preview": row["preview_visible"], "payment_warning": row["payment_warning_seen"],
                        "continue_anyway": row["continue_anyway_clicked"],
                        "download_button": row["download_button_visible"]}, ensure_ascii=False), flush=True)

                statuses = Counter(row["status"] for row in new_reviewed)
                if sum(statuses.get(k,0) for k in ("client_challenge","error")) >= 3:
                    stop_reason = "blocked_or_errors_limit"
                    break
                if first_batch and args.limit == 0:
                    first_batch = False
                    passing = sum(row["status"]=="preview_visible" for row in new_reviewed[:10])
                    if passing < 7:
                        stop_reason = "ten_url_preflight_failed"
                        break
            # One authorized download test only. Prior successful previews from the
            # local CSV checkpoint must still be eligible when --resume skips visits.
            download_result = {"status": "disabled"}
            if args.test_download_one:
                existing_candidates = [by_id[item["document_id"]] for item in selected
                                       if item["document_id"] in by_id]
                first_visible = next(
                    (r for r in existing_candidates
                     if r.get("status") == "preview_visible"
                     and str(r.get("download_button_visible", "")).lower() == "true"), None)
                if first_visible:
                    item = next(v for v in selected if v["document_id"] == first_visible["document_id"])
                    download_result = await one_permitted_download_test(context, item, downloads, output)
                else:
                    download_result = {"status": "no_preview_with_download_control"}
                (output / "single-download-test.json").write_text(
                    json.dumps(download_result, ensure_ascii=False, indent=2), encoding="utf-8")
                print("ONE_AUTHORIZED_DOWNLOAD_TEST", json.dumps(download_result, ensure_ascii=False), flush=True)

            save_csv(output / "rows.csv", list(by_id.values()))
            stats = Counter(x["status"] for x in new_reviewed)
            summary = {"scope": args.scope, "source_count": total, "selected": len(selected),
                       "newly_checked": len(new_reviewed), "headless": False,
                       "login_mode": login_mode, "standalone_chrome_reused": True,
                       "payment_modal_action": "Continue anyway only",
                       "status_counts": dict(stats), "stop_reason": stop_reason,
                       "download_test": download_result,
                       "note": "A visible preview is not proof of full PDF or an exact book edition.",
                       "timestamp": utc_now()}
            (output / "summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            print("SIGNED_IN_CHROME_SUMMARY", json.dumps(summary, ensure_ascii=False), flush=True)
        finally:
            # The browser/context belongs to the USER, not to Playwright.
            # Exiting this CDP client must not close the standalone Chrome/profile.
            print("CDP_TASK_FINISHED: standalone Chrome remains open on the PC", flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--catalog-dir", required=True)
    p.add_argument("--scope", choices=["unlinked","all"], default="unlinked")
    p.add_argument("--limit", type=int, default=10, help="0=full after 10-url quality gate; 10=smoke test")
    p.add_argument("--output-dir", default="hitel-scribd-signed-in-results")
    p.add_argument("--cdp-endpoint", default="http://127.0.0.1:9222")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--test-download-one", action="store_true")
    args=p.parse_args()
    if args.limit < 0 or args.limit > 3000:
        p.error("limit must be 0..3000")
    asyncio.run(main_async(args))


if __name__=="__main__":
    main()
