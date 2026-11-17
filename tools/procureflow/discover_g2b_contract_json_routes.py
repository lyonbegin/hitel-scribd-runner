#!/usr/bin/env python3
"""Discover real public G2B contract search route from served HTML/JS.

This tool does not guess .do endpoint names or submit unknown POSTs.
It records provenance, HTML/script bytes SHA256, navigation/GET URLs,
and bounded code snippets near contract keywords for exact route discovery.
"""
import asyncio, datetime as dt, hashlib, json, os, re, urllib.parse
from pathlib import Path
from playwright.async_api import async_playwright

ROOT=Path(os.environ.get("RUNNER_TEMP","."))/"pf2-contract-json-discovery"
ROOT.mkdir(parents=True, exist_ok=True)
SITES={
 "g2b":"https://www.g2b.go.kr/",
 "data":"https://data.g2b.go.kr/link/AISC001_01/?reptNm=UI-ADOXFA-113R",
 "shop":"https://shop.g2b.go.kr/",
}
KEYWORD=re.compile(r"(?i)계약현황|계약정보|계약체결|수의계약|계약내역|cntrct|cntrc|contract|ctrt|ctrct|prvtcntrct")
ENDPOINT=re.compile(r'(?i)(?:https?://[a-z0-9_.-]+)?/[a-z0-9_-]+(?:/[a-z0-9_-]+){2,9}/[a-z0-9_-]+\.(?:do|xml|wq|js)')
READ=re.compile(r"(?i)(select|search|list|inq|query|find|retrieve|detail|detl)")
RISK=re.compile(r"(?i)(submit|insert|delete|update|save|pay|purchase|login|logout|register|write|upload|sign)")
AUTH=re.compile(r"(?i)(password|Authorization|client_secret|access_token|id_token|refresh_token|sessionid|JSESSIONID)")
MAX_SOURCE=2000000

def sha(raw):return hashlib.sha256(raw).hexdigest()
def sample(t,k=22):
 snippets=[];s=set()
 for m in KEYWORD.finditer(t):
  st=max(0,m.start()-155);en=min(len(t),m.end()+185)
  q=" ".join(t[st:en].split())[:320]
  if q in s or AUTH.search(q):continue
  s.add(q);snippets.append(q)
  if len(snippets)>=k:break
 return snippets

def paths(t):
 allp=set()
 for m in ENDPOINT.finditer(t):
  p=m.group(0)
  if len(p)<230 and not RISK.search(p):
   allp.add(p)
 return sorted(allp)

async def main():
 report={"started_at":dt.datetime.now(dt.timezone.utc).isoformat(),"sites":{},"scope":"read-only public HTML and public scripts"}
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(channel="chrome",headless=False)
  try:
   for site,url in SITES.items():
    context=await browser.new_context(locale="ko-KR",timezone_id="Asia/Seoul",service_workers="allow")
    # Only GET/HEAD and OPTIONS; never submit contract, bid or authentication.
    await context.route("**/*", lambda route:route.continue_() if route.request.method in ("GET","HEAD","OPTIONS") else route.abort())
    page=await context.new_page()
    log={"url":url,"assets":[],"request_events":[],"page_errors":[]}
    page.on("pageerror",lambda err:log["page_errors"].append(str(err)[:220]))
    def onresponse(resp):
     if len(log["request_events"])>=300:return
     parsed=urllib.parse.urlsplit(resp.url)
     log["request_events"].append({"path":parsed.path,"host":parsed.hostname,
       "method":resp.request.method,"status":resp.status,
       "mime":resp.headers.get("content-type","").split(";")[0]})
    page.on("response",onresponse)
    try:
     r=await page.goto(url,wait_until="domcontentloaded",timeout=40000)
     await page.wait_for_timeout(9000)
     html=await page.content();raw=html.encode("utf-8")
     name=f"{site}_rendered.html";(ROOT/name).write_bytes(raw)
     log.update(status=r.status if r else None,final_url=page.url.split("?")[0],
       raw_html=name,html_bytes=len(raw),html_sha256=sha(raw),
       dom_children=await page.evaluate("document.body?.childElementCount || 0"),
       html_keyword_snippets=sample(html,20),
       html_public_endpoint_candidates=paths(html)[:80])
     if site=="data":assets=[
      "/_wpack_/layout/GnbTop.js","/_wpack_/layout/GnbMenuDev.js",
      "/_wpack_/kn/layout/GnbTop.js",
      "/_wpack_/kn/layout/GnbMenuDev.js",
      "/_wpack_/ai/layout/GnbTop.js",
     ]
     elif site=="shop": assets=[
      "/_wpack_/kn/layout/shop/ShopGnbTop.js",
      "/_wpack_/kn/layout/shop/ShopPortal.js",
     ]
     else: assets=[
      "/_wpack_/kn/layout/GnbMenuDev.js",
      "/_wpack_/kn/layout/GnbTop.js",
      "/_wpack_/kn/layout/GnbBtm.js",
     ]
     scripts=await page.locator("script[src]").evaluate_all("els=>els.map(e=>e.src).filter(Boolean)")
     # Each origin's real static script paths and a tiny explicit list; no site crawling.
     seen=set()
     for p in scripts+assets:
      target=urllib.parse.urljoin(page.url,p)
      parsed=urllib.parse.urlsplit(target)
      if parsed.hostname!=urllib.parse.urlsplit(url).hostname:continue
      if not parsed.path.endswith(".js") and not parsed.path.endswith("javascriptLoader.wq"):continue
      if target in seen:continue
      seen.add(target)
      if len(seen)>75:break
      entry={"url_path":parsed.path}
      try:
       rj=await context.request.get(target,timeout=15000,max_redirects=3)
       b=await rj.body()
       entry.update(status=rj.status,mime=rj.headers.get("content-type","").split(";")[0],
                    length=len(b),sha256=sha(b))
       if rj.status==200 and len(b)<MAX_SOURCE and (
          "javascript" in entry["mime"] or parsed.path.endswith(".js")
       ):
        txt=b.decode("utf-8",errors="replace")
        hints=sample(txt,10)
        endpoints=paths(txt)
        entry.update(contract_snippets=hints,
                     contract_endpoints=[x for x in endpoints if KEYWORD.search(x)][:45],
                     endpoint_around_contract=[x for x in endpoints if READ.search(x)][:20])
        if hints or entry["contract_endpoints"]:
         safe=hashlib.sha256(parsed.path.encode()).hexdigest()[:14]
         filename=f"{site}_script_{safe}.js"
         (ROOT/filename).write_bytes(b)
         entry["source_file"]=filename
      except Exception as exc:entry["error"]=type(exc).__name__+":"+str(exc)[:180]
      log["assets"].append(entry)
    except Exception as exc:log["error"]=type(exc).__name__+":"+str(exc)[:250]
    await context.close()
    report["sites"][site]=log
  finally:await browser.close()
 (ROOT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
 for name,s in report["sites"].items():
  relevant=[x for x in s["assets"] if x.get("contract_snippets") or x.get("contract_endpoints")]
  print("PF2_CONTRACT_ROUTE_DISCOVERY",json.dumps({
   "site":name,"status":s.get("status"),"body_children":s.get("dom_children"),
   "html_snippets":s.get("html_keyword_snippets",[])[:10],
   "html_endpoint_candidates":s.get("html_public_endpoint_candidates",[])[:30],
   "assets_checked":len(s["assets"]), "relevant_assets":relevant[:12],
   "errors":s.get("error"),"page_errors":s.get("page_errors",[])[:4]
  },ensure_ascii=False),flush=True)

if __name__=="__main__":asyncio.run(main())
