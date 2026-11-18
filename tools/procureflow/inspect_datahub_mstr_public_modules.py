#!/usr/bin/env python3
"""Inspect already published WebSquare report module imports for real report-data API.

Only public static GET and source provenance. No authentication, tokens, mutations,
brute-force endpoint guessing or report-data success claims.
"""
import asyncio,hashlib,json,os,re,urllib.parse
from pathlib import Path
from playwright.async_api import async_playwright
HOST="https://data.g2b.go.kr/"
PATHS=(
 "/_wpack_/layout/Portal.js",
 "/_wpack_/layout/GnbTop.js",
 "/_wpack_/ui/ai/ais/aisc/SprnReptDtlT.js",
 "/_wpack_/ui/ai/ais/aisc/ReptLstM.js",
)
OUT=Path(os.getenv("RUNNER_TEMP","."))/"pf2-mstr-source"
OUT.mkdir(parents=True,exist_ok=True)
Rx=re.compile(r"(?i)\bmstr\b|microstrategy|showMstrReptPopup|getMstrResult|getMstrPrompt|downloadCsv|src\s*:|\.js|/api/|restAPI|/mstr")
PATH_RX=re.compile(r"(?:/|\.?\.?/)[A-Za-z0-9_\-./]{3,175}(?:\.js|\.do|\.xml)")
def sha(b):return hashlib.sha256(b).hexdigest()
def excerpts(t,limit=48):
 hits=[];seen=set()
 for m in Rx.finditer(t):
  s=" ".join(t[max(0,m.start()-150):min(len(t),m.end()+200)].split())[:380]
  if re.search(r"(?i)(authToken|accessToken|sessionId|password|secretKey)",s):continue
  if s not in seen:seen.add(s);hits.append(s)
  if len(hits)>=limit:break
 return hits
async def main():
 rep={"sources":[]}
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel="chrome",headless=False)
  ctx=await browser.new_context(locale="ko-KR",timezone_id="Asia/Seoul")
  try:
   pg=await ctx.new_page()
   h=await pg.goto(HOST,wait_until="domcontentloaded",timeout=35000)
   body=await h.body()
   html=body.decode("utf-8",errors="replace").replace("\\/","/")
   quoted=sorted(set(PATH_RX.findall(html)))
   candidates=[x for x in quoted if "bsnejs" in x.lower() or "mstr" in x.lower() or "mstr" in x.lower()]
   rep["home_http"]=h.status
   rep["html_public_mstr_source_hints"]=candidates[:35]
   print("PF2_MSTR_HOMEPAGE_SOURCE_HINTS",json.dumps(rep["html_public_mstr_source_hints"],ensure_ascii=False),flush=True)
   for i,path in enumerate(PATHS):
    r=await ctx.request.get(HOST+path.lstrip("/"),timeout=21000)
    raw=await r.body()
    info={"path":path,"http":r.status,"mime":r.headers.get("content-type","").split(";")[0],
      "bytes":len(raw),"sha256":sha(raw)}
    if r.status==200 and "javascript" in info["mime"]:
     t=raw.decode("utf-8",errors="replace")
     info["references"]=excerpts(t,45)
     info["relevant_source_paths"]=[x for x in sorted(set(PATH_RX.findall(t))) if "bsnejs" in x or "mstr" in x.lower()][:60]
     info["module_requires"]=list(dict.fromkeys(re.findall(r"(?i)src\s*:\s*['\"]([^'\"\n]+)['\"]",t)))[:50]
     (OUT/f"module_{i}.js").write_bytes(raw)
    rep["sources"].append(info)
    print("PF2_MSTR_SOURCE",json.dumps(info,ensure_ascii=False),flush=True)
  finally:await ctx.close();await browser.close()
 (OUT/"report.json").write_text(json.dumps(rep,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__":asyncio.run(main())
