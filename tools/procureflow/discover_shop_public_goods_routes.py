#!/usr/bin/env python3
"""Locate actual public shop.g2b.go.kr goods/search JSON routes from served code."""
import asyncio,datetime as dt,hashlib,json,os,re
from pathlib import Path
from playwright.async_api import async_playwright

HOST="https://shop.g2b.go.kr/"
PATH=re.compile(r'(?:\\?/)?ui/[A-Za-z0-9_/-]{4,170}\.xml')
API=re.compile(r'/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+){2,10}/[A-Za-z0-9_-]+\.do')
KEYWORD=re.compile(r'(?i)shop|goods|prdt|srch|deta|ctrt|cart|prod|mas|dema|dlvgds|reqt|item|상품|납품요구|계약물품|구매')
SRC=re.compile(r"""src\s*:\s*['"]([^'"]{5,200})['"]""")
ROOT=Path(os.environ.get("RUNNER_TEMP","."))/"pf2-shop-route-discovery"
ROOT.mkdir(parents=True,exist_ok=True)

def sha(b):return hashlib.sha256(b).hexdigest()
def excerpts(t,needle,limit=16,side=120):
 out=[];seen=set()
 for m in needle.finditer(t):
  v=" ".join(t[max(0,m.start()-side):m.end()+side].split())[:300]
  if v not in seen:out.append(v);seen.add(v)
  if len(out)>=limit:break
 return out

async def main():
 report={"at":dt.datetime.now(dt.timezone.utc).isoformat(),"screens":[]}
 async with async_playwright() as p:
  br=await p.chromium.launch(channel="chrome",headless=False)
  ctx=await br.new_context(locale="ko-KR",timezone_id="Asia/Seoul")
  try:
   page=await ctx.new_page()
   home=await page.goto(HOST,wait_until="domcontentloaded",timeout=35000)
   raw=await home.body() if home else b""
   txt=raw.decode("utf-8",errors="replace").replace("\\/","/")
   allpaths=sorted(set("/"+s.lstrip("/") for s in PATH.findall(txt)))
   report["homepage"]={"http":home.status if home else None,"bytes":len(raw),
     "sha256":sha(raw),"screen_total":len(allpaths),"relevant_paths":[x for x in allpaths if KEYWORD.search(x)][:150],
     "labels":excerpts(txt,re.compile(r'(?i)종합쇼핑몰|상품검색|물품검색|계약물품|납품요구|쇼핑몰|다수공급자'),24,200)}
   print("PF2_SHOP_MENU",json.dumps(report["homepage"],ensure_ascii=False),flush=True)
   (ROOT/"shop_home.html").write_bytes(raw)
   paths=set()
   for s in allpaths:
    if KEYWORD.search(s):
     paths.add("/_wpack_/"+s[1:-4]+".js")
   paths.add("/_wpack_/kn/layout/shop/ShopPortal.js")
   paths.add("/_wpack_/layout/GnbTop.js")
   for i,path in enumerate(sorted(paths)[:75]):
    entry={"path":path}
    try:
     r=await ctx.request.get(HOST+path.lstrip("/"),timeout=20000)
     body=await r.body()
     entry.update(status=r.status,mime=r.headers.get("content-type","").split(";")[0],
        bytes=len(body),sha256=sha(body))
     if r.status==200 and "javascript" in entry["mime"] and len(body)<3000000:
      t=body.decode("utf-8",errors="replace")
      entry["do_paths"]=sorted(set(API.findall(t)))[:110]
      entry["relevant_do_paths"]=[s for s in entry["do_paths"] if KEYWORD.search(s)]
      entry["near_keyword"]=excerpts(t,KEYWORD,12)
      entry["deps"]=sorted(set(SRC.findall(t)))[:35]
      name="shop_js_"+sha(path.encode())[:14]+".js"
      (ROOT/name).write_bytes(body);entry["source"]=name
    except Exception as e:
     entry["error"]=type(e).__name__+":"+str(e)[:160]
    report["screens"].append(entry)
    if entry.get("relevant_do_paths") or entry.get("error"):
     print("PF2_SHOP_SOURCE",json.dumps(entry,ensure_ascii=False),flush=True)
  finally:await ctx.close();await br.close()
 (ROOT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
 print("PF2_SHOP_ROUTES_FINAL",json.dumps({
   "examined":len(report["screens"]),
   "relevant":sorted(set(x for e in report["screens"] for x in e.get("relevant_do_paths",[])))
 },ensure_ascii=False),flush=True)
if __name__=="__main__":asyncio.run(main())
