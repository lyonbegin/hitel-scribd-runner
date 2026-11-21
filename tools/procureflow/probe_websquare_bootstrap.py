#!/usr/bin/env python3
"""Read-only WebSquare bootstrap diagnostics. No login, POST, form or transaction."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

URLS = {
 "g2b": ["https://www.g2b.go.kr/"],
 "data": ["https://data.g2b.go.kr/",
          "https://data.g2b.go.kr/link/AISC001_01/?reptNm=UI-ADOXFA-112R",
          "https://data.g2b.go.kr/link/AISC001_01/?reptNm=UI-ADOXFA-113R"],
 "shop": ["https://shop.g2b.go.kr/"]
}
def run(site, out):
    out.mkdir(parents=True, exist_ok=True)
    report = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=False)
        context = browser.new_context(locale="ko-KR", timezone_id="Asia/Seoul", service_workers="allow")
        # Explicitly log the guard's decision, not an inferred server HTTP status.
        # Keep only origin/path/method/resource type; never store query, body or headers.
        guard_decisions = []
        def readonly_guard(route):
            req = route.request
            if req.method in ("GET", "HEAD", "OPTIONS"):
                return route.continue_()
            u = urlsplit(req.url)
            guard_decisions.append({
                "host": u.hostname, "path": u.path[:240],
                "method": req.method, "resource_type": req.resource_type,
                "reason": "non_readonly_method_blocked_before_network",
                "server_http_status": None,
            })
            return route.abort("blockedbyclient")
        context.route("**/*", readonly_guard)
        for idx, url in enumerate(URLS[site]):
            page = context.new_page()
            events, errors, failed_requests = [], [], []
            guard_start = len(guard_decisions)
            def on_response(res):
                u = urlsplit(res.url)
                if u.hostname and (u.hostname.endswith("g2b.go.kr")):
                    events.append({"host":u.hostname,"path":u.path[:220],
                                   "status":res.status,"method":res.request.method,
                                   "type":res.request.resource_type,
                                   "location_host":urlsplit(res.headers.get("location","")).hostname,
                                   "mime":res.headers.get("content-type","").split(";")[0]})
            page.on("response", on_response)
            page.on("requestfailed", lambda req: failed_requests.append({"url":req.url.split("?")[0][:240], "host":urlsplit(req.url).hostname, "path":urlsplit(req.url).path[:240], "resource_type":req.resource_type, "method":req.method, "failure":req.failure, "client_guard_blocked": req.method not in ("GET", "HEAD", "OPTIONS") and "ERR_BLOCKED_BY_CLIENT" in str(req.failure).upper()}))
            page.on("pageerror", lambda exc: errors.append(str(exc)[:300]))
            page.on("console", lambda msg: errors.append("console:"+msg.text[:300]) if msg.type=="error" else None)
            status = None
            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=35000)
                status = response.status if response else None
                # Capture timed, non-interactive DOM snapshots to explain intermittent homepage rendering.
                timeline = []
                for elapsed in (2000, 5000, 9000, 12000):
                    page.wait_for_timeout(elapsed - (timeline[-1]["elapsed_ms"] if timeline else 0))
                    snapshot = page.evaluate("""() => ({
                        ready: document.readyState,
                        children: document.body?.childElementCount ?? null,
                        textLength: document.body?.innerText?.length ?? null,
                        controls: document.querySelectorAll('a,button,input,[role="button"]').length,
                        frameCount: document.querySelectorAll('iframe').length,
                        websquare: typeof window.WebSquare,
                        visibleLabels: [...document.querySelectorAll('a,button,[role="button"]')]
                            .filter(e => e.getClientRects().length)
                            .map(e => (e.innerText || e.getAttribute('aria-label') || '').trim())
                            .filter(Boolean).slice(0,40)
                    })""")
                    timeline.append({"elapsed_ms":elapsed, **snapshot})
                dom = page.evaluate("""() => ({
                    ready: document.readyState,
                    bodyChildren: document.body?.childElementCount ?? null,
                    bodyTextLength: document.body?.innerText?.length ?? null,
                    htmlLength: document.documentElement?.outerHTML.length ?? null,
                    websquare: typeof window.WebSquare,
                    scriptCount: document.scripts.length,
                    websquareVersion: window.WebSquare?.version || null,
                    documentBase: document.baseURI,
                    activeElement: document.activeElement?.tagName || null,
                    scripts: [...document.scripts].map(x=>({src:x.src.split("?")[0], loaded:!!x.src, type:x.type})).slice(-45),
                    frames: [...document.querySelectorAll('iframe')].map(x=>x.src).slice(0,15)
                })""")
                html = page.content().encode("utf-8")
                filename = f"{site}_{idx}_dom.html"
                (out/filename).write_bytes(html)
                dom["html_sha256"] = hashlib.sha256(html).hexdigest()
                dom["timeline"] = timeline
                dom["html_file"] = filename
                page.screenshot(path=str(out/f"{site}_{idx}.png"), timeout=12000)
            except Exception as exc:
                dom = {"error":type(exc).__name__ + ":" + str(exc)[:300]}
            report.append({"requested_url":url,"final_url":page.url,"http_status":status,
                           "dom":dom,"errors":errors[:40],"responses":events[-180:],
                           "response_total":len(events),"request_failures":failed_requests[:40],
                           "client_guard_decisions":guard_decisions[guard_start:][:80],
                           "client_guard_decision_count":len(guard_decisions)-guard_start,
                           "get_302":[e for e in events if e["status"]==302][-20:],
                           "non_static":[e for e in events if e["type"] in ("xhr","fetch","document")][-60:]})
            page.close()
        browser.close()
    (out/"bootstrap_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("BOOTSTRAP_REPORT",json.dumps([{"url":r["requested_url"],"status":r["http_status"],
        "dom":r["dom"],"response_total":r["response_total"],"get_302":r["get_302"],
        "non_static":r["non_static"],"errors":r["errors"]} for r in report],ensure_ascii=False),flush=True)

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--site",choices=URLS,required=True)
    p.add_argument("--outdir",type=Path,required=True)
    a=p.parse_args()
    run(a.site,a.outdir)
