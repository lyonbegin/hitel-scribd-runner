#!/usr/bin/env python3
"""Test if keywordless shop catalogue can represent two-year delivery orders.

Keywordless goods are current catalog, NOT historical procurement events.
Source-valid searchVO=dlShopSrchM and official no-terms product API only.
"""
import asyncio,datetime as dt,hashlib,json,os,re
from pathlib import Path
from playwright.async_api import async_playwright
HOST="https://shop.g2b.go.kr/"
SRC=HOST+"_wpack_/ui/gl/gla/glab/LomkGdsSrchLst.js"
API=HOST+"gm/gms/gmsd/newShopUntySrchApi.do"
OUT=Path(os.getenv("RUNNER_TEMP","."))/"pf2-shop-unfiltered-scope"
OUT.mkdir(parents=True,exist_ok=True)
def sha(b):return hashlib.sha256(b).hexdigest()
async def main():
 report={"source_type":"current_catalogue_not_historical_delivery_orders",
    "required_delivery_period":"20241118-20261117","method":"direct_public_JSON_POST_no_keyword"}
 async with async_playwright() as p:
  br=await p.chromium.launch(channel="chrome",headless=False)
  ctx=await br.new_context(locale="ko-KR",timezone_id="Asia/Seoul")
  try:
   page=await ctx.new_page()
   h=await page.goto(HOST,wait_until="domcontentloaded",timeout=35000)
   report["home_http"]=h.status if h else None
   s=await ctx.request.get(SRC)
   text=(await s.body()).decode("utf-8",errors="replace")
   pos=text.find("id:'dlShopSrchM'")
   if pos<0:raise RuntimeError("Missing actual source search data map")
   js_part=text[pos:pos+12500]
   keys=list(dict.fromkeys(re.findall(r"w2:key',A:{id:'([^']+)'",js_part)))
   report["source_search_fields"]=keys[:90]
   report["date_search_fields"]=[k for k in keys if re.search(r"(?i)(date|ymd|dt)$",k)]
   report["no_date_condition_in_map"]=len(report["date_search_fields"])==0
   assert 'searchVO=dlShopSrchM' in text
   payload={"searchVO":{"searchKeyword":"","currentPage":1,"recordCountPerPage":"30"}}
   r=await ctx.request.post(API,data=json.dumps(payload,ensure_ascii=False),
        headers={"Content-Type":"application/json","Referer":HOST},timeout=28000)
   raw=await r.body()
   (OUT/"unfiltered_catalogue_page1.json").write_bytes(raw)
   obj=json.loads(raw)
   rows=obj.get("rsltList",[])
   report["response"]={"http":r.status,"bytes":len(raw),"sha256":sha(raw),
      "errorCode":obj.get("ErrorCode"),"message":obj.get("ErrorMsg"),
      "totalSize":obj.get("totalSize"),
      "product_rows":len(rows) if isinstance(rows,list) else None,
      "sample_contract_dates":sorted(set(str(x.get("ctrtYmd","")) for x in rows if isinstance(x,dict)))[:25],
      "sample_contract_count":len(set(str(x.get("ctrtNo","")) for x in rows if isinstance(x,dict))),
      "sample_delivery_order_number_fields":[k for k in (rows[0] if rows and isinstance(rows[0],dict) else {}) if re.search(r"(?i)dlreq|dlvgdsreqt|deliveryOrder",k)][:25]}
  finally:await ctx.close();await br.close()
 (OUT/"scope.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
 print("PF2_SHOP_UNFILTERED_SCOPE",json.dumps(report,ensure_ascii=False),flush=True)
if __name__=="__main__":asyncio.run(main())
