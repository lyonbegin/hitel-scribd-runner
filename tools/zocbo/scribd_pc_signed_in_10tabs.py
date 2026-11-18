#!/usr/bin/env python3
"""Scribd source-link review in the Windows PC's *visible*, manually signed-in Chrome.

The GitHub self-hosted runner starts the browser, but sign-in happens only in the
local browser window. Chrome's dedicated profile stays on this Windows PC.
No credentials, cookies, storage state, downloaded books or payment details are
exported to GitHub. Public previews and permitted single-file download test only.
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


def make_control_file(path: Path, count: int, scope: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    page = """<!doctype html><html lang="ko"><meta charset="utf-8">
    <title>HITEL — Scribd 수동 로그인 확인</title>
    <style>body{font:18px/1.7 system-ui,'Malgun Gothic',sans-serif;background:#f8fafb;color:#18202b;
    margin:0 auto;padding:50px;max-width:780px}main{background:white;border:1px solid #d8e1e9;
    border-radius:16px;padding:32px}button{font-size:19px;padding:16px 30px;border:0;border-radius:10px;
    color:white;background:#047857;cursor:pointer}p{margin:8px 0 20px}</style>
    <main><h2>HITEL — Scribd 로그인 후 작업 시작</h2>
    <p>첫 번째 Scribd 탭에서 <strong>직접 로그인</strong>해 주십시오. 결제 안내가 나타나면
    <strong>Continue anyway</strong>로 닫으십시오.</p>
    <p>로그인이 끝나면 이 <strong>HITEL 작업 시작</strong> 탭으로 돌아와 아래 버튼을 눌러 주십시오.</p>
    <p>처리 예정: <strong>COUNT</strong>개 링크 (범위: SCOPE).
    사용자님의 비밀번호·로그인 세션·다운로드한 파일은 GitHub에 전송하지 않습니다.</p>
    <button onclick="window.HITEL_START=true;this.disabled=true;this.textContent='시작 신호 전송 완료';">
    로그인 완료 · 링크 검사 시작</button>
    <p id="notice">진행 시작 후 Chrome 창을 닫지 말아 주십시오.</p>
    </main></html>"""
    page = page.replace("COUNT", str(count)).replace("SCOPE", scope)
    path.write_text(page, encoding="utf-8")


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
    """Single file test only; no bulk download. The signed-in user's entitlement controls access."""
    result = {"document_id": item["document_id"], "original_url": item["original_url"],
              "status": "not_started", "download_saved_on_pc": False, "payment_warning_seen": False}
    page = await context.new_page()
    try:
        await page.goto(item["original_url"], wait_until="domcontentloaded", timeout=35000)
        await page.wait_for_timeout(1300)
        result["payment_warning_seen"] = bool(PAYMENT_HOLD.search(await body_text(page)))
        await dismiss_continue_anyway(page)
        button = page.get_by_role("button", name=re.compile(r"^download(\s|$)", re.I))
        if not await button.count():
            result["status"] = "download_control_absent"
            return result
        try:
            async with page.expect_download(timeout=12000) as download_signal:
                await button.first.click(timeout=4500)
            download = await download_signal.value
            destination.mkdir(parents=True, exist_ok=True)
            name = re.sub(r"[^\w.\-가-힣]+", "_", download.suggested_filename)[:120]
            path = destination / f"{item['document_id']}_{name}"
            await download.save_as(path)
            result["status"] = "download_saved_on_pc"
            result["download_saved_on_pc"] = True
            result["local_file_name"] = path.name
            result["file_size_bytes"] = path.stat().st_size
        except PlaywrightTimeout:
            result["status"] = "no_download_event"
            result["payment_warning_seen"] = result["payment_warning_seen"] or bool(
                PAYMENT_HOLD.search(await body_text(page)))
            result["continue_anyway_clicked"] = await dismiss_continue_anyway(page)
        except Exception as e:
            result["status"] = "download_error"
            result["error"] = (type(e).__name__ + ": " + str(e))[:220]
        if result["status"] != "download_saved_on_pc":
            await page.screenshot(path=str(results_dir / "single-download-test.png"),
                                  full_page=False, timeout=7000)
    except Exception as e:
        result["status"] = "navigation_error"
        result["error"] = (type(e).__name__ + ": " + str(e))[:220]
    finally:
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
    # Never put the persistent Chrome user profile in the GitHub runner workspace.
    profile = pc_base / "HITEL" / "ScribdSignedInChromeProfile"
    checkpoint = pc_base / "HITEL" / "ScribdReview" / args.scope / "results.csv"
    downloads = pc_base / "HITEL" / "ScribdDownloads"
    profile.mkdir(parents=True, exist_ok=True)
    previous = load_csv(checkpoint) if args.resume else []
    by_id = {row["document_id"]: row for row in previous
             if row.get("status") not in ("error", "timeout", "client_challenge")}
    pending = [item for item in selected if item["document_id"] not in by_id]
    print("SAVED_LINKS", json.dumps({"scope": args.scope, "source_total": total,
         "selected": len(selected), "already_checked": len(selected)-len(pending),
         "pending": len(pending), "tabs": 10, "headless": False,
         "profile_local_only": True}, ensure_ascii=False), flush=True)

    control_path = output / "HITEL-START.html"
    make_control_file(control_path, len(pending), args.scope)
    results = list(by_id.values())

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile), channel="chrome", headless=False,
            viewport={"width": 1366, "height": 900}, locale="ko-KR",
            accept_downloads=True, args=["--disable-dev-shm-usage"])
        try:
            signin = context.pages[0] if context.pages else await context.new_page()
            await signin.goto("https://www.scribd.com/document/746963536",
                              wait_until="domcontentloaded", timeout=35000)
            control = await context.new_page()
            await control.goto(control_path.as_uri())
            await signin.bring_to_front()
            print("MANUAL_LOGIN_REQUIRED: Sign into Scribd in the opened LOCAL PC Chrome window.",
                  "After logging in, open the HITEL-START tab and click the green start button.",
                  "No credentials or cookies are sent to GitHub.", flush=True)
            ready = False
            for _ in range(args.login_wait_seconds):
                try:
                    await dismiss_continue_anyway(signin)
                    if await control.evaluate("window.HITEL_START===true"):
                        ready = True
                        break
                except Exception:
                    pass
                await asyncio.sleep(1)
            if not ready:
                raise TimeoutError("Manual Scribd login confirmation did not arrive")
            print("MANUAL_LOGIN_CONFIRMED_BY_USER: Start button clicked. Account status not independently asserted.",
                  flush=True)
            await control.close()
            await signin.close()

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
            # Only one attempted download in the smoke test, never bulk download.
            download_result = {"status": "disabled"}
            if args.test_download_one and new_reviewed:
                first_visible = next((r for r in new_reviewed if r["status"]=="preview_visible"
                                      and r["download_button_visible"]), None)
                if first_visible:
                    item = next(v for v in selected if v["document_id"]==first_visible["document_id"])
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
                       "signed_in_by": "manual_user_click_confirmation_not_secret_inspection",
                       "payment_modal_action": "Continue anyway only",
                       "status_counts": dict(stats), "stop_reason": stop_reason,
                       "download_test": download_result,
                       "note": "A visible preview is not proof of full PDF or an exact book edition.",
                       "timestamp": utc_now()}
            (output / "summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            print("SIGNED_IN_CHROME_SUMMARY", json.dumps(summary, ensure_ascii=False), flush=True)
        finally:
            await context.close()


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--catalog-dir", required=True)
    p.add_argument("--scope", choices=["unlinked","all"], default="unlinked")
    p.add_argument("--limit", type=int, default=10, help="0=full after 10-url quality gate; 10=smoke test")
    p.add_argument("--output-dir", default="hitel-scribd-signed-in-results")
    p.add_argument("--login-wait-seconds", type=int, default=900)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--test-download-one", action="store_true")
    args=p.parse_args()
    if args.limit < 0 or args.limit > 3000:
        p.error("limit must be 0..3000")
    asyncio.run(main_async(args))


if __name__=="__main__":
    main()
