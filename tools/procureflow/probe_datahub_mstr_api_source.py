#!/usr/bin/env python3
"""Extract read-only MSTR report and CSV action from PUBLIC website JS scripts.

Every URL below is proven by data.g2b.go.kr HTML script tag. No code is
executed besides Chrome visiting public homepage; no authentication is attempted.
Do not publish session tokens or dynamic signed keys from page HTML.
"""
import asyncio,hashlib,json,os,re
from pathlib import Path
from playwright.async_api import async_playwright
ROOT="https://data.g2b.go.kr/"
SOURCES=("/dtap_com/js/mstr.js","/dtap_com/js/mstrConst.js","/dtap_com/js/mstrPopup.js")
OUT=Path(os.getenv("RUNNER_TEMP","."))/"pf2-report-api-source"
OUT.mkdir(parents=True,exist_ok=True)
KEYS=("getMstrResult","getMstrPrompt","downloadCsv","downloadExcel",
      "fetch(","ajax(","XMLHttpRequest","authorization","auth","login",
      "baseURL","baseUrl","report","/api/","getMstr","prompt",
      "mstrUrl","mstrApi","session","token")
URL_REGEX=re.compile(r'(?<![\w-])/(?:[A-Za-z0-9_-]+/){1,9}[A-Za-z0-9_-]+(?:\.do|\.json|\.jsp|\.action|\.xml)?')
def sha(b):return hashlib.sha256(b).hexdigest()
def selected(t,limit=75):
 arr=[];seen=set()
 pat=re.compile("|".join(re.escape(k) for k in KEYS),re.I)
 for m in pat.finditer(t):
  value=" ".join(t[max(0,m.start()-160):min(len(t),m.end()+270)].split())[:440]
  if re.search(r"(?i)(accessToken|refreshToken|JSESSIONID|secretKey|password|apiKey)",value):continue
  if value not in seen:arr.append(value);seen.add(value)
  if len(arr)>=limit:break
 return arr
async def main():
 report=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel="chrome",headless=False)
  ctx=await browser.new_context(locale="ko-KR",timezone_id="Asia/Seoul")
  try:
   page=await ctx.new_page()
   r=await page.goto(ROOT,wait_until="domcontentloaded",timeout=35000)
   if not r or r.status!=200:raise RuntimeError("Datahub homepage not accessible")
   for idx,path in enumerate(SOURCES):
    res=await ctx.request.get(ROOT+path.lstrip("/"),timeout=22000)
    raw=await res.body()
    mime=res.headers.get("content-type","").split(";")[0]
    x={"path":path,"http":res.status,"mime":mime,"bytes":len(raw),"sha256":sha(raw)}
    if res.status==200 and ("javascript" in mime or "text/plain" in mime):
     t=raw.decode("utf-8",errors="replace")
     x["symbols"]={k:len(list(re.finditer(re.escape(k),t,re.I))) for k in KEYS}
     x["do_paths"]=sorted(set(URL_REGEX.findall(t)))[:110]
     x["method_context"]=selected(t,85)
     (OUT/f"official_mstr_{idx}.js").write_bytes(raw)
    report.append(x)
    print("PF2_MSTR_PUBLIC_PROVIDER",json.dumps(x,ensure_ascii=False),flush=True)
  finally:await ctx.close();await browser.close()
 (OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__":asyncio.run(main())
