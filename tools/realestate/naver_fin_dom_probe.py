#!/usr/bin/env python3
"""One-shot diagnostic for the public Npay Land map.

Do not log in, circumvent rate limits, or retry HTTP 429.
A successful runner execution is not the same as a successful property search.
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright


async def main():
    out = Path("naver-fin-dom-results")
    out.mkdir(exist_ok=True)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "target": "https://fin.land.naver.com/map",
        "status": "not_started",
        "listing_count": 0,
        "responses": [],
        "retries": 0,
        "note": "Single public Chrome visit; never bypass rate limiting.",
    }
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
        context = await browser.new_context(locale="ko-KR", viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        def observe(response):
            u = urlsplit(response.url)
            if u.hostname and u.hostname.endswith("land.naver.com"):
                if len(report["responses"]) < 50:
                    report["responses"].append({
                        "path": u.path[:160],
                        "status": response.status,
                    })
                if response.status == 429:
                    report["status"] = "rate_limited"
                    report["rate_limited_at"] = u.path[:160]

        page.on("response", observe)
        try:
            resp = await page.goto(report["target"], wait_until="commit", timeout=15000)
            report["main_http_status"] = resp.status if resp else None
            # One brief wait only; no reloads, retry loops or new contexts.
            await page.wait_for_timeout(3000)
            report["final_url"] = page.url
            if report["status"] == "rate_limited":
                report["note"] = "HTTP 429 from Naver; stopped without further requests."
            elif "/404" in urlsplit(page.url).path or "financial.pstatic.net/404" in page.url:
                report["status"] = "error_page"
            else:
                snapshot = await page.evaluate("""() => ({
                  title: document.title,
                  text: (document.body?.innerText || '').slice(0,1500),
                  inputs: [...document.querySelectorAll('input')].slice(0,12)
                    .map(e => ({placeholder: e.placeholder || '', type: e.type || ''})),
                  cardCount: document.querySelectorAll('.item_inner').length
                })""")
                report["snapshot"] = snapshot
                report["listing_count"] = snapshot["cardCount"]
                report["status"] = "ui_ready" if snapshot["inputs"] or snapshot["cardCount"] else "ui_not_ready"
            try:
                await page.screenshot(path=str(out / "map.png"), timeout=4000)
            except Exception as e:
                report["screenshot_note"] = type(e).__name__
        except Exception as e:
            if report["status"] != "rate_limited":
                report["status"] = "navigation_error"
            report["error"] = (type(e).__name__ + ": " + str(e))[:350]
        finally:
            await browser.close()

    (out / "ui.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = (
        "## Naver Land Chrome diagnostic\n\n"
        f"- Browser run: finished\n"
        f"- Site status: **{report['status']}**\n"
        f"- Listing cards verified: **{report['listing_count']}**\n"
        f"- HTTP 429 detected: **{report['status']=='rate_limited'}**\n"
        "- Scope: public page, one visit, zero retries; no listing verification on rate limit.\n"
    )
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(summary)
    print("NAVER_DIAGNOSTIC", json.dumps({
        "status": report["status"],
        "listing_count": report["listing_count"],
        "rate_limited_at": report.get("rate_limited_at"),
        "final_url": report.get("final_url"),
        "error": report.get("error"),
    }, ensure_ascii=True), flush=True)

if __name__ == "__main__":
    asyncio.run(main())
