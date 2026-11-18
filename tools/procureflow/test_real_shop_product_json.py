#!/usr/bin/env python3
"""Read-only real shop.g2b.gov Chrome-session product-list JSON direct POST.

Actual paths, 'searchVO=dlShopSrchM', and searchKeyword/currentPage fields
are grounded in /_wpack_/ui/gl/gla/glab/LomkGdsSrchLst.js.
No order, cart, registration, purchase or delivery submissions.
"""
import asyncio,datetime as dt,hashlib,json,os
from pathlib import Path
from playwright.async_api import async_playwright

HOST="https://shop.g2b.go.kr/"
SOURCE=HOST+"_wpack_/ui/gl/gla/glab/LomkGdsSrchLst.js"
CANDIDATES=(
"/gm/gms/gmsd/newShopUntySrchApi.do",
"/gm/gms/gmsd/shopUntyOnlyLstSrchApi.do",
)
OUT=Path(os.getenv("RUNNER_TEMP","."))/"pf2-shop-real-products"
OUT.mkdir(parents=True,exist_ok=True)

def sha(b):return hashlib.sha256(b).hexdigest()
def log(k,d):print(k,json.dumps(d,ensure_ascii=False,sort_keys=True),flush=True)

def parse(raw):
 try:j=json.loads(raw)
 except ValueError:return {"is_json":False,"head":raw[:100].decode("utf-8",errors="replace")}
 res={"is_json":True,"root_type":type(j).__name__}
 if not isinstance(j,dict):return res
 res["root_keys"]=list(j)[:55]
 res["ErrorCode"]=j.get("ErrorCode")
 res["ErrorMsg"]=str(j.get("ErrorMsg") or j.get("message") or "")[:160]
 res["totalSize"]=j.get("totalSize")
 fields=("prodNm","itemCfnm","itemIdnfNo","ctrtItemMngNo","etpsNm","bzmnRegNo",
         "unitPrice","ctrtAmt","shopCtrtTyCd","ctrtNo","itemClsfNm","itemNm","itemPrce")
 arrays=[]
 for k,v in j.items():
  if isinstance(v,list):
   arrays.append((k,v))
  elif isinstance(v,dict):
   for kk,vv in v.items():
    if isinstance(vv,list):arrays.append((str(k)+"."+str(kk),vv))
 res["arrays"]=[{"name":k,"count":len(v),
    "sample_keys":sorted(v[0])[:55] if v and isinstance(v[0],dict) else [],
    "first_row":{key:str(v[0][key])[:150] for key in fields if key in v[0]}
      if v and isinstance(v[0],dict) else {}}
   for k,v in arrays][:24]
 res["real_goods_rows"]=sum(len(v) for k,v in arrays
   if v and isinstance(v[0],dict) and
      any(any(s in str(field).lower() for s in ("goods","item","prod","prce","etps","ctrt"))
          for field in v[0].keys())
   )
 return res

async def main():
 report={"at":dt.datetime.now(dt.timezone.utc).isoformat(),
         "origin":HOST,"source":SOURCE,"verified_goods_rows":0,"requests":[]}
 async with async_playwright() as pw:
  br=await pw.chromium.launch(channel="chrome",headless=False)
  ctx=await br.new_context(locale="ko-KR",timezone_id="Asia/Seoul")
  try:
   page=await ctx.new_page();home=await page.goto(HOST,wait_until="domcontentloaded",timeout=35000)
   report["home_status"]=home.status if home else None
   report["home_body_count"]=await page.evaluate("document.body?.childElementCount||0")
   sr=await ctx.request.get(SOURCE,timeout=20000)
   sourcebytes=await sr.body()
   js=sourcebytes.decode("utf-8",errors="replace")
   report["source_status"]=sr.status
   report["source_sha256"]=sha(sourcebytes)
   for endpoint in CANDIDATES:
    if endpoint not in js:
     raise RuntimeError("Expected read-only goods-search path not in official source: "+endpoint)
    # Explicitly confirm left-side WebSquare submission binding.
    near=js.find(endpoint)
    if "searchVO=dlShopSrchM" not in js[near:near+400]:
     raise RuntimeError("Request map not source-verified for "+endpoint)
   values=[
    ("simple_chair",{"searchKeyword":"의자","currentPage":1,"recordCountPerPage":"30"}),
    ("office_chair",{"searchKeyword":"사무용의자","currentPage":1,"recordCountPerPage":"30","tabDiv":"L"}),
    ("LED",{"searchKeyword":"LED","currentPage":1,"recordCountPerPage":"30"}),
   ]
   for endpoint in CANDIDATES:
    for idx,(name,search) in enumerate(values):
     entry={"path":endpoint,"variant":name,"search_keys":list(search),
            "request_map":"searchVO=dlShopSrchM"}
     try:
      resp=await ctx.request.post(HOST+endpoint.lstrip("/"),
        data=json.dumps({"searchVO":search},ensure_ascii=False),
        headers={"Content-Type":"application/json","Referer":HOST,"User-Agent":"Mozilla/5.0"},
        timeout=30000)
      raw=await resp.body()
      file=endpoint.split("/")[-1].replace(".do","")+f"_{idx}.json"
      (OUT/file).write_bytes(raw)
      entry.update(http=resp.status,bytes=len(raw),sha256=sha(raw),file=file,**parse(raw))
     except Exception as e:entry["error"]=type(e).__name__+":"+str(e)[:180]
     report["requests"].append(entry)
     log("PF2_SHOP_REAL_PRODUCT_JSON",entry)
     if entry.get("http")==200 and entry.get("real_goods_rows",0)>0:
      report["verified_goods_rows"]=entry["real_goods_rows"]
      report["winning_endpoint"]=endpoint
      report["winning_variant"]=name
      second=dict(search);second["currentPage"]=2
      nextresp=await ctx.request.post(HOST+endpoint.lstrip("/"),
        data=json.dumps({"searchVO":second},ensure_ascii=False),
        headers={"Content-Type":"application/json","Referer":HOST},timeout=30000)
      content=await nextresp.body()
      (OUT/"shop_products_page2.json").write_bytes(content)
      report["page2"]={"http":nextresp.status,"bytes":len(content),"sha256":sha(content),**parse(content)}
      log("PF2_SHOP_PRODUCT_PAGE2",report["page2"])
      break
    if report["verified_goods_rows"]>0:break
  finally:await ctx.close();await br.close()
 (OUT/"summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
 log("PF2_SHOP_PRODUCT_FINAL",{
    "home_status":report.get("home_status"),"home_body_count":report.get("home_body_count"),
    "source_status":report.get("source_status"),"source_sha256":report.get("source_sha256"),
    "requests":len(report["requests"]),"verified_goods_rows":report.get("verified_goods_rows"),
    "winning_endpoint":report.get("winning_endpoint"),
    "winning_variant":report.get("winning_variant"),
    "page2_rows":report.get("page2",{}).get("real_goods_rows")
 })
if __name__=="__main__":asyncio.run(main())
