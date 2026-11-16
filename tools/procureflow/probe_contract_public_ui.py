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
        "errors": [], "console_errors": [], "page_errors": [], "browser_pages": [],
        "request_failures": [], "http_errors": [], "tracked_post_responses": [],
        "response_count_total": 0, "late_script_paths": [], "xhr_paths": [],
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=False, timeout=30000)
        context = browser.new_context(
            locale="ko-KR", timezone_id="Asia/Seoul",
            viewport={"width": 1440, "height": 900},
            service_workers="allow",
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
        page.on("pageerror", lambda error: report["page_errors"].append(short(error, 200)))
        page.on("console", lambda msg: report["console_errors"].append(short(msg.text, 220)) if msg.type == "error" and len(report["console_errors"]) < 25 else None)

        def on_response(response):
            report["response_count_total"] += 1
            info = network_info(response.request)
            info["status"] = response.status
            info["mime"] = (response.headers.get("content-type") or "").split(";")[0]
            # Collect late failures and POST metadata independently of the static resource flood.
            if response.status >= 400 and len(report["http_errors"]) < 60:
                report["http_errors"].append(info)
            if info["method"] in ("GET","POST") and len(report["late_script_paths"]) < 240:
                if info["path"].endswith((".js",".xml",".json",".do",".wq")):
                    report["late_script_paths"].append(info)
            if info["method"] == "POST" or (".do" in info["path"] and response.status == 200):
                if len(report["xhr_paths"]) < 100:
                    report["xhr_paths"].append(info)
            if response.request.method == "POST" and len(report["tracked_post_responses"]) < 40:
                report["tracked_post_responses"].append(info)
            if len(report["events"]) < MAX_EVENTS:
                report["events"].append(info)

        page.on("response", on_response)
        page.on("requestfailed", lambda req: report["request_failures"].append(
            {**network_info(req), "failure": short(req.failure, 180)}
        ) if len(report["request_failures"]) < 40 else None)

        def capture(name):
            try:
                page.wait_for_timeout(9500)
                filename = name + ".png"
                page.screenshot(path=str(output / filename), full_page=False, timeout=12000)
                report["screenshots"].append(filename)
                labels = nav_candidates(page)
                entry = {
                    "step": name, "current_url": page.url,
                    "title": short(page.title(), 160),
                    "body_excerpt": short(page.locator("body").inner_text(timeout=5000), 1600),
                    "document_probe": page.evaluate("""() => ({
                        ready: document.readyState,
                        htmlLength: document.documentElement?.outerHTML?.length || 0,
                        bodyCount: document.body?.childElementCount || 0,
                        bodyTextLength: document.body?.innerText?.length || 0,
                        webSquareDefined: typeof window.WebSquare !== 'undefined',
                        websquareObject: typeof window.$w !== 'undefined',
                        inlinePathHints: [...new Set(
                            Array.from(document.documentElement.outerHTML.matchAll(/\\/(?:[a-zA-Z0-9_-]+\\/){2,9}[a-zA-Z0-9_-]+\\.(?:do|xml|json)/g))
                              .map(x => x[0])
                        )].filter(s => s.length < 170).slice(0,90),
                        inlineScriptCount: Array.from(document.scripts).filter(x => !x.src).length
                    })"""),
                    "visible_controls": labels[:80],
                    "frame_urls": [short(frame.url, 180) for frame in page.frames],
                    "context_pages": [short(p.url, 180) for p in context.pages],
                    "script_sources": page.locator("script[src]").evaluate_all("els=>els.map(x=>x.src).slice(0,35)"),
                    "body_html_prefix": short(page.locator("body").inner_html(timeout=5000), 800),

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
            elif args.site == "data":
                reports = [
                    ("01_contract_method_report", "https://data.g2b.go.kr/link/AISC001_01/?reptNm=UI-ADOXFA-113R"),
                    ("02_business_report", "https://data.g2b.go.kr/link/AISC001_01/?reptNm=UI-ADOXFA-112R"),
                ]
                for name, target in reports:
                    try:
                        r = page.goto(target, wait_until="domcontentloaded", timeout=25000)
                        report[name + "_http_status"] = r.status if r else None
                        capture(name)
                    except Exception as exc:
                        report["errors"].append({"step": name, "error": type(exc).__name__ + ":" + short(exc)})
        except Exception as exc:
            report["errors"].append({"step": "initial_navigation", "error": type(exc).__name__ + ":" + short(exc)})
        finally:
            report["browser_pages"] = [short(p.url, 200) for p in context.pages]
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
        "response_count_total": report["response_count_total"],
        "http_errors": report["http_errors"], "request_failures": report["request_failures"],
        "observed_script_paths": sorted(set(x["path"] for x in report["late_script_paths"]))[-110:],
        "xhr_paths": report["xhr_paths"][:30],
        "tracked_post_responses": report["tracked_post_responses"],
        "document_probes": [p.get("document_probe") for p in report["pages"]],
        "block_count": len(report["blocked_non_read_only_requests"]),
        "errors": report["errors"], "browser_pages": report["browser_pages"],
        "page_errors": report["page_errors"], "console_errors": report["console_errors"],
        "get_paths": sorted(set(x["path"] for x in report["events"] if x["method"] == "GET"))[:70],
        "report_http_statuses": {k:v for k,v in report.items() if k.endswith("_http_status")},
        "oidc_responses": [x for x in report["events"] if "/oidc/" in x["path"]][:12],
        "context_page_metadata": [{
            "frames": p.get("frame_urls", []), "scripts": p.get("script_sources", []),
            "body_html_prefix": p.get("body_html_prefix", "")[:500]
        } for p in report["pages"]],
    }
    print("PROCUREFLOW_PUBLIC_WEB_PROBE", json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
