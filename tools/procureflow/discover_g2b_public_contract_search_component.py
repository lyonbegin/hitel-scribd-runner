#!/usr/bin/env python3
"""Trace exact public contract-search WebSquare component dependencies and read routes."""
import asyncio,datetime as dt,json,re,hashlib,os
from pathlib import Path
from playwright.async_api import async_playwright
BASE="https://www.g2b.go.kr/"
SCREENS={
 "contract-search":"/_wpack_/ui/fi/fiu/fiua/CtrtCrstDtlSrchL.js",
 "contract-detail":"/_wpack_/ui/fi/fiu/fiua/LinkCtrtMngDtlV.js",
}
SRC=re.compile(r"src\s*:\s*['\x22]([^'\x22]{3,240})['\x22]")
ENDPOINT=re.compile(r"/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+){2,9}/[A-Za-z0-9_-]+\.do")
OUT=Path(os.environ.get("RUNNER_TEMP","."))/"pf2-contract-public-search-deps"
OUT.mkdir(parents=True,exist_ok=True)
async def main():
 report={"time":dt.datetime.now(dt.timezone.utc).isoformat(),"screens":{}}
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(channel="chrome",headless=False)
  ctx=await browser.new_context(locale="ko-KR")
  try:
   page=await ctx.new_page()
   resp=await page.goto(BASE,wait_until="domcontentloaded",timeout=35000)
   report["home_http"]=resp.status if resp else None
   for name,path in SCREENS.items():
    req=await ctx.request.get(BASE+path.lstrip("/"),timeout=20000)
    raw=await req.body()
    t=raw.decode("utf-8",errors="replace")
    info={"source":path,"http":req.status,
      "bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),
      "src":sorted(set(SRC.findall(t)))[:160],
      "urls_do":sorted(set(ENDPOINT.findall(t)))[:140],
      "fiSrchcom_calls":[],"require_modules":[],"module_paths":[]}
    for kw in ("fiSrchcom","selectUntySrchList","w2:require","CtrtCrstDtlSrchL","dlSrchParamM"):
     for m in list(re.finditer(re.escape(kw),t))[:9]:
      snippet=" ".join(t[max(0,m.start()-210):min(len(t),m.end()+200)].split())
      info["fiSrchcom_calls"].append({"keyword":kw,"snippet":snippet[:440]})
    for m in list(re.finditer("w2:require",t))[:90]:
     snippet=" ".join(t[max(0,m.start()-50):min(len(t),m.end()+370)].split())
     info["require_modules"].append(snippet[:440])
    if req.status==200:
     filename=name+".js";(OUT/filename).write_bytes(raw)
    report["screens"][name]=info
    print("PF2_CONTRACT_PUBLIC_SEARCH_DEPS",json.dumps(info,ensure_ascii=False),flush=True)
  finally:await ctx.close();await browser.close()
 (OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__":asyncio.run(main())
