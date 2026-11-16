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
        # Block all state-changing requests, including incidental SSO submissions.
        context.route("**/*", lambda route: route.continue_() if route.request.method in ("GET", "HEAD", "OPTIONS") else route.abort("blockedbyclient"))
        for idx, url in enumerate(URLS[site]):
            page = context.new_page()
            events, errors, failed_requests = [], [], []
            def on_response(res):
                u = urlsplit(res.url)
                if u.hostname and (u.hostname.endswith("g2b.go.kr")):
                    events.append({"host":u.hostname,"path":u.path[:220],
                                   "status":res.status,"method":res.request.method,
                                   "type":res.request.resource_type,
                                   "location_host":urlsplit(res.headers.get("location","")).hostname,
                                   "mime":res.headers.get("content-type","").split(";")[0]})
            page.on("response", on_response)
            page.on("requestfailed", lambda req: failed_requests.append({"url":req.url.split("?")[0][:240], "method":req.method, "failure":req.failure}))
            page.on("pageerror", lambda exc: errors.append(str(exc)[:300]))
            page.on("console", lambda msg: errors.append("console:"+msg.text[:300]) if msg.type=="error" else None)
            status = None
            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=35000)
                status = response.status if response else None
                page.wait_for_timeout(12000)
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
                dom["html_file"] = filename
                page.screenshot(path=str(out/f"{site}_{idx}.png"), timeout=12000)
            except Exception as exc:
                dom = {"error":type(exc).__name__ + ":" + str(exc)[:300]}
            report.append({"requested_url":url,"final_url":page.url,"http_status":status,
                           "dom":dom,"errors":errors[:40],"responses":events[-180:],
                           "response_total":len(events),"request_failures":failed_requests[:40],
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
