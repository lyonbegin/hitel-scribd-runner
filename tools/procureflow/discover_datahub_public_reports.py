#!/usr/bin/env python3
"""Read-only extraction of real data.g2b.go.kr report screens and compiled JS.

No unknown POSTs, sessions or account secrets. Discovers paths from HTML served
by data hub, then requests only the corresponding WebSquare compiled JS assets.
"""
import asyncio, datetime as dt, hashlib, json, os, re
from pathlib import Path
from playwright.async_api import async_playwright

ROOT="https://data.g2b.go.kr"
URLS=(ROOT+"/",ROOT+"/link/AISC001_01/?reptNm=UI-ADOXFA-113R",
      ROOT+"/link/AISC001_01/?reptNm=UI-ADOXFA-112R")
TARGET=re.compile(r"(?i)AISC001_01|reptNm|UI-ADOXFA|계약.*?업체|조달.*?통계|계약.*?내역|데이터.*?보고서")
SCREEN=re.compile(r"(?:\\?/)?ui/[A-Za-z0-9/_-]{5,150}\.(?:xml|js)")
ENDPOINT=re.compile(r"/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+){2,10}/[A-Za-z0-9_-]+\.do")
SRC=re.compile(r"""src\s*:\s*['"]([^'"]{5,230})['"]""")
OUT=Path(os.getenv("RUNNER_TEMP","."))/"pf2-datahub-discovery"
OUT.mkdir(parents=True,exist_ok=True)

def sha(b):return hashlib.sha256(b).hexdigest()
def excerpts(t,rx,n=40,side=160):
 acc=[];seen=set()
 for m in rx.finditer(t):
  v=" ".join(t[max(0,m.start()-side):m.end()+side].split())[:450]
  if v not in seen:
   seen.add(v);acc.append(v)
   if len(acc)>=n:break
 return acc

async def main():
 rep={"at":dt.datetime.now(dt.timezone.utc).isoformat(),"urls":[],"screens":[],"raw_sources":[]}
 async with async_playwright() as p:
  br=await p.chromium.launch(channel="chrome",headless=False)
  ctx=await br.new_context(locale="ko-KR",timezone_id="Asia/Seoul")
  try:
   for idx,url in enumerate(URLS):
    page=await ctx.new_page()
    try:
     response=await page.goto(url,wait_until="domcontentloaded",timeout=35000)
     # Source response body is more reliable than WebSquare empty DOM.
     raw=await response.body() if response else b""
     txt=raw.decode("utf-8",errors="replace")
     entry={"url":url,"http":response.status if response else None,
       "mime":response.headers.get("content-type","") if response else None,
       "bytes":len(raw),"sha256":sha(raw),"target_snippets":excerpts(txt,TARGET,30),
       "screen_paths":sorted(set(SCREEN.findall(txt)))[:95],
       "script_paths":await page.locator("script[src]").evaluate_all("xs=>xs.map(x=>x.getAttribute('src')).filter(Boolean)")[:45]}
     rep["urls"].append(entry)
     (OUT/f"entry_{idx}.html").write_bytes(raw)
     print("PF2_DATAHUB_HTML",json.dumps(entry,ensure_ascii=False),flush=True)
    except Exception as e:
     rep["urls"].append({"url":url,"error":type(e).__name__+":"+str(e)[:240]})
     print("PF2_DATAHUB_HTML_ERROR",json.dumps({"url":url,"error":type(e).__name__+":"+str(e)[:240]},ensure_ascii=False),flush=True)
    finally:await page.close()
   # Derive screen JS candidates from actual public menu definitions; don't
   # assume source file exists merely because a menu uses it.
   paths=set()
   for entry in rep["urls"]:
    for x in entry.get("screen_paths",[]):
     x=x.lstrip("/")
     if any(s in x.lower() for s in ("aisc","data","report","rept","ado","stats","stat")):
      if x.endswith(".xml"): paths.add("/_wpack_/"+x[:-4]+".js")
      elif x.endswith(".js"): paths.add("/"+x)
   # Screens published by data hub's menu definitions, plus landing bundles
   # already present in previous verified public JS captures.
   paths.update({"/_wpack_/layout/GnbTop.js","/_wpack_/ui/ai/ais/aisc/AISC001_01.js",
                 "/_wpack_/ui/ai/ais/aisc/Aisc001_01.js",
                 "/_wpack_/ui/ai/ais/aisc/ReptInqL.js"})
   for path in sorted(paths)[:65]:
    item={"path":path}
    try:
     r=await ctx.request.get(ROOT+path,timeout=18000)
     raw=await r.body()
     item.update(http=r.status,mime=r.headers.get("content-type","").split(";")[0],
         bytes=len(raw),sha256=sha(raw))
     if r.status==200 and "javascript" in item["mime"] and len(raw)<3_000_000:
      txt=raw.decode("utf-8",errors="replace")
      item["do_paths"]=sorted(set(ENDPOINT.findall(txt)))[:120]
      item["deps"]=sorted(set(SRC.findall(txt)))[:65]
      item["target_snippets"]=excerpts(txt,TARGET,28)
      item["read_query_snippets"]=excerpts(txt,re.compile(r"(?i)action\s*:|inData\s*:|reptNm|reptId|reptCd|dataSet|dataset"),28)
      filename="screen_"+sha(path.encode())[:14]+".js"
      (OUT/filename).write_bytes(raw)
      item["original_file"]=filename
    except Exception as e:
     item["error"]=type(e).__name__+":"+str(e)[:180]
    rep["screens"].append(item)
    print("PF2_DATAHUB_SCREEN",json.dumps(item,ensure_ascii=False),flush=True)
  finally:await ctx.close();await br.close()
 (OUT/"report.json").write_text(json.dumps(rep,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__":
 asyncio.run(main())
