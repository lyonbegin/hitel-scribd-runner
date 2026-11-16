#!/usr/bin/env python3
"""Read-only G2B UI/network reconnaissance. No data collection or login."""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

SITES = {
    "g2b": "https://www.g2b.go.kr/",
    "data": "https://data.g2b.go.kr/",
    "shop": "https://shop.g2b.go.kr/",
}
PUBLIC_CONTRACT = re.compile(
    r"계약정보|계약실적검색|계약현황|계약조회|수의계약현황|계약결과|계약실적|계약정보조회"
)
EXCLUDE_CLICK = re.compile(
    r"로그인|회원가입|계약체결|계약작성|계약신청|계약요청|계약서작성|계약서제출|입찰|투찰|제출|전자서명|신청|수정|삭제|주문|구매|결제"
)
READ_ONLY_POST = re.compile(r"(?i)(select|search|list|find|inq|query|retrieve)")
DANGEROUS = re.compile(r"(?i)(insert|update|delete|save|register|sign|submit|create|pay|order|login|logout)")
MAX_EVENTS = 90


def short(value, n=220):
    return re.sub(r"\s+", " ", str(value or ""))[:n]


def network_info(req):
    parsed = urlparse(req.url)
    body_keys = []
    if req.method == "POST":
        try:
            data = req.post_data
            if data:
                j = json.loads(data)
                if isinstance(j, dict):
                    body_keys = sorted(str(x) for x in j.keys())[:30]
        except (ValueError, TypeError):
            body_keys = ["non-json-form-or-opaque"]
    return {
        "host": parsed.hostname,
        "path": parsed.path[:220],
        "query_keys": sorted(parse_qs(parsed.query).keys())[:24],
        "method": req.method,
        "post_top_level_keys": body_keys,
    }


def nav_candidates(page):
    try:
        return page.locator("a,button,[role=menuitem],[role=button]").evaluate_all(
            """els => els.filter(e => {
                  const rect = e.getBoundingClientRect();
                  return rect.width > 0 && rect.height > 0;
               }).map(e => ({
                  tag: e.tagName, text: (e.innerText || e.textContent || '').replace(/\\s+/g,' ').trim().slice(0,130),
                  href: e.getAttribute('href') || '',
                  role: e.getAttribute('role') || '',
                  title: e.getAttribute('title') || ''
               })).filter(x => x.text).slice(0, 300)"""
        )
    except Exception as exc:
        return [{"error": type(exc).__name__ + ":" + short(exc, 150)}]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", choices=SITES, default="g2b")
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    output = Path(args.outdir)
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "site": args.site, "url": SITES[args.site],
        "at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "scope": "PUBLIC_READ_ONLY_UI_INSPECTION",
        "events": [], "screenshots": [], "pages": [],
        "blocked_non_read_only_requests": [],
        "errors": [],
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=False, timeout=30000)
        context = browser.new_context(
            locale="ko-KR", timezone_id="Asia/Seoul",
            viewport={"width": 1440, "height": 900},
            service_workers="block",
            accept_downloads=False,
        )

        # An accidental click must never submit an order, bid, contract or login form.
        def guard(route):
            req = route.request
            parsed = urlparse(req.url)
            path = parsed.path
            if req.method not in ("GET", "HEAD", "OPTIONS"):
                if (
                    req.method == "POST" and
                    parsed.hostname and parsed.hostname.endswith(".g2b.go.kr") and
                    READ_ONLY_POST.search(path) and
                    not DANGEROUS.search(path)
                ):
                    return route.continue_()
                if len(report["blocked_non_read_only_requests"]) < 40:
                    report["blocked_non_read_only_requests"].append(network_info(req))
                return route.abort()
            return route.continue_()

        context.route("**/*", guard)
        page = context.new_page()

        def on_response(response):
            if len(report["events"]) >= MAX_EVENTS:
                return
            info = network_info(response.request)
            info["status"] = response.status
            info["mime"] = (response.headers.get("content-type") or "").split(";")[0]
            # Request metadata only: never log auth headers or full post bodies.
            report["events"].append(info)

        page.on("response", on_response)

        def capture(name):
            try:
                page.wait_for_timeout(1800)
                filename = name + ".png"
                page.screenshot(path=str(output / filename), full_page=False, timeout=12000)
                report["screenshots"].append(filename)
                labels = nav_candidates(page)
                entry = {
                    "step": name, "current_url": page.url,
                    "title": short(page.title(), 160),
                    "body_excerpt": short(page.locator("body").inner_text(timeout=5000), 1600),
                    "visible_controls": labels[:80],
                    "contract_controls": [x for x in labels if PUBLIC_CONTRACT.search(x.get("text", ""))][:30],
                }
                report["pages"].append(entry)
                return entry
            except Exception as exc:
                report["errors"].append({"step": name, "error": type(exc).__name__ + ":" + short(exc)})
                return None

        try:
            response = page.goto(SITES[args.site], wait_until="domcontentloaded", timeout=45000)
            report["homepage_status"] = response.status if response else None
            start = capture("00_home")
            if args.site == "g2b" and start:
                # Navigate only to one demonstrably public CONTRACT READ link.
                candidates = start.get("contract_controls", [])
                for c in candidates:
                    label = c.get("text", "")
                    href = c.get("href", "")
                    if not PUBLIC_CONTRACT.search(label) or EXCLUDE_CLICK.search(label):
                        continue
                    if href and not href.startswith("javascript:"):
                        try:
                            target = page.locator("a").filter(has_text=label).first
                            if target.count() and target.is_visible(timeout=2500):
                                target.click(timeout=9000)
                                capture("01_contract_menu")
                                break
                        except Exception as exc:
                            report["errors"].append({"step": "contract_menu", "error": type(exc).__name__ + ":" + short(exc)})
                    else:
                        try:
                            target = page.get_by_text(label, exact=True).first
                            if target.count() and target.is_visible(timeout=2500):
                                target.click(timeout=9000)
                                capture("01_contract_menu")
                                break
                        except Exception as exc:
                            report["errors"].append({"step": "contract_menu", "error": type(exc).__name__ + ":" + short(exc)})
        except Exception as exc:
            report["errors"].append({"step": "initial_navigation", "error": type(exc).__name__ + ":" + short(exc)})
        finally:
            browser.close()

    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "site": args.site,
        "homepage_status": report.get("homepage_status"),
        "pages": [{"step": p["step"], "url": p["current_url"],
                   "title": p["title"], "body_excerpt": p["body_excerpt"], "visible_controls": [x.get("text") for x in p["visible_controls"][:35]], "contract_labels": [c.get("text") for c in p["contract_controls"]]}
                  for p in report["pages"]],
        "post_paths": sorted(set(
            x["path"] for x in report["events"] if x["method"] == "POST"
        )),
        "request_count": len(report["events"]),
        "block_count": len(report["blocked_non_read_only_requests"]),
        "errors": report["errors"],
    }
    print("PROCUREFLOW_PUBLIC_WEB_PROBE", json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
