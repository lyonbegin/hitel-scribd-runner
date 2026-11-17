#!/usr/bin/env python3
"""Read the exact official public unified contract search library.

Proven source: CtrtCrstDtlSrchL.js declares /bsnejs/fi/fiCommonUntySrchLib.js.
This stage retrieves the real public JS and identifies its POST action/payload.
"""
import asyncio,datetime as dt,hashlib,json,os,re
from pathlib import Path
from playwright.async_api import async_playwright
BASE="https://www.g2b.go.kr/"
URL=BASE+"bsnejs/fi/fiCommonUntySrchLib.js"
OUT=Path(os.environ.get("RUNNER_TEMP","."))/"pf2-public-contract-list-js"
OUT.mkdir(parents=True,exist_ok=True)
ENDPOINT=re.compile(r"/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+){2,10}/[A-Za-z0-9_-]+\.do")
PAT=re.compile(r"(?i)selectUntySrchList|action\s*:|inData\s*:|outData\s*:|select[A-Za-z0-9_]+\.do|ctrtSrchItm0[1-9]")
async def main():
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(channel="chrome",headless=False)
  ctx=await browser.new_context(locale="ko-KR")
  try:
   p=await ctx.new_page()
   home=await p.goto(BASE,wait_until="domcontentloaded",timeout=35000)
   r=await ctx.request.get(URL,timeout=25000)
   raw=await r.body()
   txt=raw.decode("utf-8",errors="replace")
   report={"home_http":home.status if home else None,"source_url":URL,
    "http":r.status,"mime":r.headers.get("content-type","").split(";")[0],
    "size":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),
    "do_paths":sorted(set(ENDPOINT.findall(txt)))[:160],
    "function_segments":[],"snippets":[]}
   for mat in list(re.finditer("selectUntySrchList",txt))[:8]:
    report["function_segments"].append(txt[max(0,mat.start()-170):mat.end()+1750])
   for mat in list(PAT.finditer(txt))[:120]:
    q=" ".join(txt[max(0,mat.start()-90):mat.end()+170].split())[:290]
    if q not in report["snippets"]:report["snippets"].append(q)
   (OUT/"fiCommonUntySrchLib.js").write_bytes(raw)
   (OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
   print("PF2_PUBLIC_CONTRACT_SEARCH_LIBRARY",json.dumps({
    "url":URL,"http":r.status,"mime":report["mime"],"size":len(raw),
    "sha256":report["sha256"],
    "do_paths":report["do_paths"],
    "function_segments":report["function_segments"],
    "snippets":report["snippets"][:60],
   },ensure_ascii=False),flush=True)
  finally:await ctx.close();await browser.close()
if __name__=="__main__":asyncio.run(main())
