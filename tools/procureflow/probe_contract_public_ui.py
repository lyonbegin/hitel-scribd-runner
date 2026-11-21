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
try:
    from .public_readonly_raw import retain_public_json
except ImportError:
    # Direct execution as a script places this directory on sys.path.
    from public_readonly_raw import retain_public_json

SITES = {
    "g2b": "https://www.g2b.go.kr/",
    "data": "https://data.g2b.go.kr/",
    "shop": "https://shop.g2b.go.kr/",
}
PUBLIC_SHOP_SEARCH = re.compile(r"상품검색|물품검색|상품조회|상품정보|종합쇼핑몰")
PUBLIC_DELIVERY = re.compile(r"납품요구|납품실적|납품현황")
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


def summarize_post_paths(report):
    """Use the independent POST-response buffer, not the capped first events."""
    # The response sample stops at 40; the path/status counter does not.
    # Derive the complete path set from counters to avoid hiding later endpoints.
    counts = report.get("post_response_path_counts", {})
    if counts:
        return sorted({key.split("|", 2)[1] for key in counts
                       if len(key.split("|", 2)) == 3 and key.split("|", 2)[1]})
    return sorted({x["path"] for x in report.get("tracked_post_responses", [])
                   if x.get("method") == "POST" and x.get("path")})


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
        "blocked_non_read_only_requests": [], "blocked_request_count_total": 0,
        "errors": [], "console_errors": [], "page_errors": [], "browser_pages": [],
        "request_failures": [], "http_errors": [], "tracked_post_responses": [],
        "response_count_total": 0, "post_response_count_total": 0, "post_response_path_counts": {}, "late_script_paths": [], "xhr_paths": [],
        "read_only_response_proofs": [],
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
                report["blocked_request_count_total"] += 1
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
            # Digest observed public read responses without retaining body or credentials.
            path = info["path"]
            eligible = (info["method"] == "POST" and READ_ONLY_POST.search(path)
                        and not DANGEROUS.search(path)
                        and info["host"] and info["host"].endswith(".g2b.go.kr"))
            if eligible and len(report["read_only_response_proofs"]) < 30:
                proof = {**info, "status": response.status, "mime": info["mime"]}
                try:
                    payload = response.body()
                    proof["body_bytes"] = len(payload)
                    proof["body_sha256"] = hashlib.sha256(payload).hexdigest()
                    proof.update(retain_public_json(payload, info["mime"], output, len(report["read_only_response_proofs"])))
                except Exception as exc:
                    proof["body_hash_error"] = type(exc).__name__
                report["read_only_response_proofs"].append(proof)
            if response.request.method == "POST":
                report["post_response_count_total"] += 1
                # Count every observed response by public host/path/status, independent of 40-event samples.
                key = f"{info['host']}|{info['path']}|{response.status}"
                counts = report["post_response_path_counts"]
                counts[key] = counts.get(key, 0) + 1
                if len(report["tracked_post_responses"]) < 40:
                    report["tracked_post_responses"].append({**info, "status": response.status})
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
                    "visible_controls": labels[:300],
                    # Report controls can be inputs/selects rather than anchors.
                    # Metadata only: never read field values, credentials or submit forms.
                    "read_only_form_controls": page.evaluate("""() =>
                        Array.from(document.querySelectorAll('input,select,textarea'))
                          .filter(e => {
                              const r = e.getBoundingClientRect();
                              return r.width > 0 && r.height > 0;
                          }).slice(0,100).map(e => ({
                              tag: e.tagName.toLowerCase(),
                              type: (e.getAttribute('type') || '').slice(0,30),
                              id: (e.id || '').slice(0,100),
                              name: (e.getAttribute('name') || '').slice(0,100),
                              placeholder: (e.getAttribute('placeholder') || '').slice(0,100),
                              aria_label: (e.getAttribute('aria-label') || '').slice(0,100),
                              disabled: Boolean(e.disabled)
                          }))"""),
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
            # WebSquare public navigation can appear after 12 seconds.
            import time
            started = time.monotonic()
            report["visible_navigation_wait"] = {"timeout_ms": 20000, "visible": False}
            for _ in range(40):
                try:
                    count = page.locator('a:visible, button:visible, [role="menuitem"]:visible, [role="button"]:visible').count()
                    if count:
                        report["visible_navigation_wait"] = {"timeout_ms": 20000, "visible": True,
                            "elapsed_ms": int((time.monotonic() - started) * 1000),
                            "visible_control_count": count}
                        break
                except Exception as exc:
                    report["visible_navigation_wait_error"] = type(exc).__name__ + ":" + short(exc, 120)
                page.wait_for_timeout(500)
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
            elif args.site == "shop" and start:
                # Only inspect public search navigation; never click a delivery
                # request, which may be a buyer-only transaction.
                report["shop_public_search_candidates"] = [
                    c for c in start.get("visible_controls", [])
                    if PUBLIC_SHOP_SEARCH.search(c.get("text", ""))
                    and not EXCLUDE_CLICK.search(c.get("text", ""))
                    and not PUBLIC_DELIVERY.search(c.get("text", ""))
                ][:30]
                report["shop_delivery_labels_not_clicked"] = [
                    c.get("text", "") for c in start.get("visible_controls", [])
                    if PUBLIC_DELIVERY.search(c.get("text", ""))
                ][:30]
                for candidate in report["shop_public_search_candidates"]:
                    label = candidate.get("text", "")
                    try:
                        target = page.get_by_text(label, exact=True).first
                        if target.count() and target.is_visible(timeout=2500):
                            target.click(timeout=9000)
                            capture("01_public_product_search_navigation")
                            break
                    except Exception as exc:
                        report["errors"].append({"step": "shop_public_search_navigation",
                                                 "error": type(exc).__name__ + ":" + short(exc)})
            elif args.site == "data":
                reports = [
                    ("01_contract_method_report", "https://data.g2b.go.kr/link/AISC001_01/?reptNm=UI-ADOXFA-113R"),
                    ("02_business_report", "https://data.g2b.go.kr/link/AISC001_01/?reptNm=UI-ADOXFA-112R"),
                ]
                for name, target in reports:
                    try:
                        r = page.goto(target, wait_until="domcontentloaded", timeout=25000)
                        report[name + "_http_status"] = r.status if r else None
                        # The public report WebSquare shell may appear after 15s.
                        # Record a per-report readiness result rather than treating
                        # an early HTTP 200 / empty body as report data.
                        report[name + "_visible_wait"] = {"visible": False, "timeout_ms": 20000}
                        import time
                        wait_started = time.monotonic()
                        for _ in range(40):
                            try:
                                count = page.locator('a:visible, button:visible, [role="menuitem"]:visible, [role="button"]:visible').count()
                                if count:
                                    report[name + "_visible_wait"] = {
                                        "visible": True, "timeout_ms": 20000,
                                        "elapsed_ms": int((time.monotonic() - wait_started) * 1000),
                                        "visible_control_count": count,
                                    }
                                    break
                            except Exception as exc:
                                report[name + "_visible_wait_error"] = type(exc).__name__ + ":" + short(exc, 120)
                            page.wait_for_timeout(500)
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
        "visible_navigation_wait": report.get("visible_navigation_wait"),
        "pages": [{"step": p["step"], "url": p["current_url"],
                   "title": p["title"], "body_excerpt": p["body_excerpt"], "visible_controls": [x.get("text") for x in p["visible_controls"][:35]], "contract_labels": [c.get("text") for c in p["contract_controls"]]}
                  for p in report["pages"]],
        # The first MAX_EVENTS are often static assets. Do not silently report
        # zero POSTs when a later tracked response exists.
        "post_paths": summarize_post_paths(report),
        "post_response_count_observed": report["post_response_count_total"],
        "post_response_sample_count": len(report["tracked_post_responses"]),
        "post_response_sample_truncated": report["post_response_count_total"] > len(report["tracked_post_responses"]),
        "post_response_path_counts": report["post_response_path_counts"],
        "request_count": len(report["events"]),
        "response_count_total": report["response_count_total"],
        "http_errors": report["http_errors"], "request_failures": report["request_failures"],
        "observed_script_paths": sorted(set(x["path"] for x in report["late_script_paths"]))[-110:],
        "xhr_paths": report["xhr_paths"][:30],
        "tracked_post_responses": report["tracked_post_responses"],
        "read_only_response_proofs": report["read_only_response_proofs"],
        "document_probes": [p.get("document_probe") for p in report["pages"]],
        "block_count": report["blocked_request_count_total"],
        "blocked_request_sample_count": len(report["blocked_non_read_only_requests"]),
        "blocked_request_sample_truncated": report["blocked_request_count_total"] > len(report["blocked_non_read_only_requests"]),
        "errors": report["errors"], "browser_pages": report["browser_pages"],
        "page_errors": report["page_errors"], "console_errors": report["console_errors"],
        "get_paths": sorted(set(x["path"] for x in report["events"] if x["method"] == "GET"))[:70],
        "shop_public_search_candidates": report.get("shop_public_search_candidates", []),
        "shop_delivery_labels_not_clicked": report.get("shop_delivery_labels_not_clicked", []),
        "report_http_statuses": {k:v for k,v in report.items() if k.endswith("_http_status")},
        "report_visible_waits": {k:v for k,v in report.items() if k.endswith("_visible_wait")},
        "oidc_responses": [x for x in report["events"] if "/oidc/" in x["path"]][:12],
        "context_page_metadata": [{
            "frames": p.get("frame_urls", []), "scripts": p.get("script_sources", []),
            "body_html_prefix": p.get("body_html_prefix", "")[:500]
        } for p in report["pages"]],
    }
    print("PROCUREFLOW_PUBLIC_WEB_PROBE", json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
