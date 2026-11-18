#!/usr/bin/env python3
"""Extract actual parameters and search action for read-only shop goods JSON APIs."""
import asyncio,hashlib,json,os,re
from pathlib import Path
from playwright.async_api import async_playwright

HOST="https://shop.g2b.go.kr/"
PATHS=(
 "/_wpack_/ui/gl/gla/glab/LomkGdsSrchLst.js",
 "/_wpack_/ui/gm/gms/gmsc/DtlSrchV.js",
 "/_wpack_/ui/gm/gms/gmsa/ShopMain.js",
)
API_KEYWORDS=("newShopUntySrchApi.do","shopUntyOnlyLstSrchApi.do",
"lomkUntyOnlySrchApi.do","lomkUntySrchApi.do","newShopDtlsPrnmNoSrchApi.do")
OUT=Path(os.getenv("RUNNER_TEMP","."))/"pf2-shop-api-shapes"
OUT.mkdir(parents=True,exist_ok=True)
def h(b):return hashlib.sha256(b).hexdigest()

async def main():
 rep={"assets":[]}
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(channel="chrome",headless=False)
  ctx=await browser.new_context(locale="ko-KR")
  try:
   pg=await ctx.new_page()
   await pg.goto(HOST,wait_until="domcontentloaded",timeout=35000)
   for path in PATHS:
    r=await ctx.request.get(HOST+path.lstrip("/"),timeout=21000)
    raw=await r.body();t=raw.decode("utf-8",errors="replace")
    d={"path":path,"http":r.status,"mime":r.headers.get("content-type","").split(";")[0],
       "bytes":len(raw),"sha256":h(raw),"api_branches":[]}
    if "javascript" in d["mime"]:
     (OUT/(path.split("/")[-1])).write_bytes(raw)
     for kw in API_KEYWORDS:
      for m in list(re.finditer(re.escape(kw),t))[:4]:
       d["api_branches"].append({"api":kw,
         "preceding":t[max(0,m.start()-650):m.start()+200],
         "following":t[m.start():min(len(t),m.end()+630)]})
     for mapname in ("dlLomkSrchM","dlShopSrchM","dlSrchCndtM"):
      pos=t.find("id:'"+mapname+"'")
      if pos>=0:
       block=t[pos:pos+19000]
       d[mapname+"_keys"]=list(dict.fromkeys(re.findall(r"w2:key',A:{id:'([^']+)'",block)))[:105]
     for keyword in ("searchAPI","searchGoods","srchWrd","keyword","currentPage","sortOdrDiv"):
      ms=list(re.finditer(re.escape(keyword),t,re.I))
      d[keyword+"_snippets"]=[t[max(0,m.start()-90):m.end()+130] for m in ms[-5:]]
    rep["assets"].append(d)
    print("PF2_SHOP_API_SHAPES",json.dumps(d,ensure_ascii=False),flush=True)
  finally:await ctx.close();await browser.close()
 (OUT/"report.json").write_text(json.dumps(rep,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__":asyncio.run(main())
