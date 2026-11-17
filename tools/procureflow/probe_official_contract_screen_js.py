#!/usr/bin/env python3
"""Read-only source extraction for exact G2B contract menu screens seen in HTML.

Do not fabricate POST paths. Fetch the WebSquare XML and known _wpack_ JS
translations; print only observed .do URLs and source map IDs. Keep raw bytes.
"""
import asyncio, datetime as dt, hashlib, json, os, re
from pathlib import Path
from playwright.async_api import async_playwright

BASE="https://www.g2b.go.kr/"
NAMES=("CtrtCrstDtlSrchL","CtrtMoreL","LinkCtrtMngDtlV")
OUT=Path(os.getenv("RUNNER_TEMP","."))/"pf2-contract-screen-source"
OUT.mkdir(parents=True,exist_ok=True)
KW=re.compile(r"(?i)select|search|inq|query|list|ctrt|cntrct|contract|계약|mapId|sbm|submission")
DOPATH=re.compile(r"/[a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_-]+){2,9}/[a-zA-Z0-9_-]+\.do")
MAPID=re.compile(r"(?:dl|dc|ds)[A-Z][A-Za-z0-9_]{3,85}")
SCREENID=re.compile(r"[A-Z]{4}[0-9]{3}_[0-9]{2}")

def h(b):return hashlib.sha256(b).hexdigest()
def snip(t,needle,limit=18):
 out=[];seen=set()
 for m in needle.finditer(t):
  a=" ".join(t[max(0,m.start()-95):min(len(t),m.end()+125)].split())[:260]
  if a in seen:continue
  seen.add(a);out.append(a)
  if len(out)>=limit:break
 return out

async def main():
 paths=[]
 for name in NAMES:
  paths.extend((f"/ui/fi/fiu/fiua/{name}.xml",
                f"/_wpack_/fi/fiu/fiua/{name}.js",
                f"/_wpack_/ui/fi/fiu/fiua/{name}.js"))
 report={"at":dt.datetime.now(dt.timezone.utc).isoformat(),"screens":list(NAMES),"resources":[]}
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(channel="chrome",headless=False)
  ctx=await browser.new_context(locale="ko-KR",timezone_id="Asia/Seoul")
  try:
   page=await ctx.new_page()
   home=await page.goto(BASE,wait_until="domcontentloaded",timeout=35000)
   report["home_status"]=home.status if home else None
   gate=asyncio.Semaphore(4)
   async def get(path,index):
    async with gate:
     url=BASE+path.lstrip("/")
     d={"path":path}
     try:
      resp=await ctx.request.get(url,timeout=24000,max_redirects=3)
      b=await resp.body()
      d.update(status=resp.status,mime=resp.headers.get("content-type","").split(";")[0],
               bytes=len(b),sha256=h(b),final_url=resp.url.split("?")[0])
      t=b.decode("utf-8",errors="replace")
      if resp.status==200 and len(b)<2000000 and (".js" in path or "xml" in d["mime"]):
       d["do_paths"]=sorted(set(DOPATH.findall(t)))[:120]
       d["map_ids"]=sorted(set(MAPID.findall(t)))[:100]
       d["screen_ids"]=sorted(set(SCREENID.findall(t)))[:40]
       d["action_snippets"]=snip(t,re.compile(r"(?i)select[A-Za-z0-9_-]{3,100}\.do|sbm[A-Z][A-Za-z0-9_]+|dlSrch[A-Za-z0-9_]+"),30)
       d["contract_snippets"]=snip(t,re.compile("(?i)CtrtCrst|CtrtMore|계약현황|계약번호|계약일자"),20)
       if d["do_paths"] or d["map_ids"] or d["contract_snippets"]:
        f=OUT/f"g2b_contract_screen_{index:02d}{'.js' if '.js' in path else '.xml'}"
        f.write_bytes(b);d["saved_source"]=f.name
     except Exception as exc:d["error"]=type(exc).__name__+":"+str(exc)[:180]
     print("PF2_CONTRACT_SCREEN_SOURCE",json.dumps(d,ensure_ascii=False),flush=True)
     return d
   report["resources"]=await asyncio.gather(*(get(path,i) for i,path in enumerate(paths)))
  finally:
   await ctx.close()
   await browser.close()
 (OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
 print("PF2_CONTRACT_SCREEN_SUMMARY",json.dumps({
   "attempted":len(paths),
   "200_javascript":[x["path"] for x in report["resources"] if x.get("status")==200 and "javascript" in x.get("mime","")],
   "select_do_paths":sorted(set(p for x in report["resources"] for p in x.get("do_paths",[])))[:180],
 },ensure_ascii=False),flush=True)

if __name__=="__main__":asyncio.run(main())
