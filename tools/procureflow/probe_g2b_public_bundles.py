#!/usr/bin/env python3
"""Inspect known *public* WebSquare JavaScript bundles for contract-navigation hints.

Read-only: never downloads tender/contract datasets, logs in, submits forms,
or stores credentials/cookies. URLs are explicitly observed app asset paths.
"""
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

ROOTS = (
    "https://www.g2b.go.kr/",
    "https://data.g2b.go.kr/",
    "https://shop.g2b.go.kr/",
)
SCRIPT_PATHS = (
    "/kn/com/js/commonGlobal.js",
    "/kn/com/js/commonScope.js",
    "/kn/com/js/bsneComm.js",
    "/_wpack_/layout/GnbMenuDev.js",
    "/_wpack_/layout/GnbTop.js",
    "/_wpack_/layout/GnbBtm.js",
    "/dtap_com/js/dtap_com.js",
)
KEYWORD = re.compile(r"(?i)계약|contract|cntrct|cntrc|ctrt|ctrct|계약실적|계약현황|수의")
PUBLIC_PATH = re.compile(r"/[A-Za-z0-9_./-]{6,180}\.(?:do|xml|json|js)")
NOISE = re.compile(r"(?i)password|authorization|cookie|token|secret|key|nonce|state|client_id")


def inspect_text(text):
    snippets = []
    seen = set()
    for match in KEYWORD.finditer(text):
        # Only explicitly labeled source hints, not raw script bodies.
        piece = text[max(0, match.start()-95):match.end()+120]
        piece = re.sub(r"\s+", " ", piece)
        if NOISE.search(piece):
            continue
        if piece in seen:
            continue
        seen.add(piece)
        snippets.append(piece[:260])
        if len(snippets) >= 14:
            break
    paths = sorted(set(x.group(0) for x in PUBLIC_PATH.finditer(text)))
    return snippets, paths[:80]


def run():
    report = {"at":dt.datetime.now(dt.timezone.utc).isoformat(),"description":"public-bundle-readonly",
              "results":[]}
    with sync_playwright() as pw:
        req = pw.request.new_context(locale="ko-KR",ignore_https_errors=False,timeout=20000)
        try:
            for origin in ROOTS:
                for path in SCRIPT_PATHS:
                    url = urljoin(origin,path)
                    result = {"host":origin,"path":path}
                    try:
                        r = req.get(url,max_redirects=4)
                        body = r.body()
                        result.update(http=r.status,mime=r.headers.get("content-type","").split(";")[0],
                                      bytes=len(body),sha256=hashlib.sha256(body).hexdigest())
                        if r.status==200 and len(body)<=3_000_000 and b"\x00" not in body:
                            text = body.decode("utf-8-sig",errors="replace")
                            snippets,paths=inspect_text(text)
                            result["safe_keyword_snippets"]=snippets
                            result["public_path_hints"]=paths
                    except Exception as exc:
                        result["error"] = type(exc).__name__+":"+str(exc)[:150]
                    report["results"].append(result)
        finally:
            req.dispose()
    relevant=[x for x in report["results"] if x.get("safe_keyword_snippets")]
    summary={"total_requests":len(report["results"]),"200":sum(x.get("http")==200 for x in report["results"]),
             "relevant":relevant[:20],
             "status_for_non200":[{"host":x["host"],"path":x["path"],"status":x.get("http"),"error":x.get("error")}
                    for x in report["results"] if x.get("http")!=200][:20]}
    print("PF2_PUBLIC_G2B_BUNDLE_HINTS",json.dumps(summary,ensure_ascii=False),flush=True)
    outfile=Path("procureflow_bundle_report.json")
    outfile.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")


if __name__=="__main__":
    run()
