#!/usr/bin/env python3
"""Live public G2B contract status list JSON test: known route & map from served JS.

Source: /bsnejs/fi/fiCommonUntySrchLib.js; menu FIUA004_01, strURL=
/fi/fiu/fiua/UntySrch/srchCtrtSttus.do; inData dlSrchParamM;
outData dlTotalSrchL + dlSetParamM. Same context.request.post as old Stage2.
"""
import asyncio,datetime as dt,hashlib,json,os,re
from pathlib import Path
from playwright.async_api import async_playwright
BASE="https://www.g2b.go.kr/"
SOURCE=BASE+"bsnejs/fi/fiCommonUntySrchLib.js"
SCREEN=BASE+"_wpack_/ui/fi/fiu/fiua/CtrtCrstDtlSrchL.js"
API=BASE+"fi/fiu/fiua/UntySrch/srchCtrtSttus.do"
OUT=Path(os.environ.get("RUNNER_TEMP","."))/"pf2-real-public-contract-list"
OUT.mkdir(parents=True,exist_ok=True)
START,END="20261110","20261117"

def digest(b):return hashlib.sha256(b).hexdigest()
def log(k,v):print(k,json.dumps(v,ensure_ascii=False,sort_keys=True),flush=True)
def shape(raw):
 try:r=json.loads(raw)
 except ValueError:return {"is_json":False,"body_prefix":raw[:80].decode("utf-8",errors="replace")}
 d={"is_json":True,"top_type":type(r).__name__}
 if not isinstance(r,dict):return d
 d.update(error_code=r.get("ErrorCode"),error_message=str(r.get("ErrorMsg") or "")[:180],keys=list(r)[:30])
 result=r.get("result")
 d["result_type"]=type(result).__name__
 if isinstance(result,dict):
  d["result_keys"]=list(result)[:45]
  d["lists"]={k:len(v) for k,v in result.items() if isinstance(v,list)}
  d["first_item_keys"]={k:sorted(v[0])[:45] for k,v in result.items()
        if isinstance(v,list) and v and isinstance(v[0],dict)}
  d["map_shapes"]={k:{kk:(str(vv)[:80] if isinstance(vv,(str,int,float)) else type(vv).__name__)
     for kk,vv in v.items() if len(str(kk))<60}
     for k,v in result.items() if isinstance(v,dict) and ("Param" in k or "Set" in k)}
  d["real_contract_rows"]=sum(len(v) for k,v in result.items()
      if isinstance(v,list) and len(v)>0 and ("ctrt" in str(k).lower() or "srch" in str(k).lower()))
 else:d["real_contract_rows"]=0
 return d

async def main():
 doc={"checked":dt.datetime.now(dt.timezone.utc).isoformat(),
      "api":API,"source_js":SOURCE,"requests":[],"data_received":False}
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(channel="chrome",headless=False)
  ctx=await browser.new_context(locale="ko-KR",timezone_id="Asia/Seoul")
  try:
   page=await ctx.new_page();home=await page.goto(BASE,wait_until="domcontentloaded",timeout=35000)
   doc["homepage_status"]=home.status if home else None
   doc["homepage_children"]=await page.evaluate("document.body?.childElementCount||0")
   a=await ctx.request.get(SOURCE);js=(await a.body()).decode("utf-8",errors="replace")
   doc["source_http"]=a.status;doc["source_sha256"]=digest(js.encode("utf-8"))
   if 'strSrchURL = "/fi/fiu/fiua/UntySrch/srchCtrtSttus.do"' not in js:
    raise RuntimeError("PUBLIC_CONTRACT_STATUS_ROUTE_NOT_PRESENT_IN_OFFICIAL_JS")
   doc["reference_menu_found"]='FIUA004_01' in js
   s=await ctx.request.get(SCREEN);st=(await s.body()).decode("utf-8",errors="replace")
   pos=st.find("id:'dlSrchParamM'")
   subset=st[pos:pos+18000] if pos>=0 else ""
   doc["screen_key_hints"]=list(dict.fromkeys(re.findall(r"w2:key',A:{id:'([^']+)'",subset)))[:80]
   contract_positions=[m.start() for m in re.finditer("strSrchType == \"CTRT\"",js)]
   doc["ctrt_branch_hints"]=[js[max(0,i-100):i+600] for i in contract_positions[:7]]
   variants={
    "minimal":{"startBizYmd":START,"endBizYmd":END,"currentPage":1,"recordCountPerPage":"100"},
    "ctrt_dates":{"startBizYmd":START,"endBizYmd":END,
      "bizYmdDiv":"ctrtCntgYmd","srchSeCd":"CC CUC",
      "currentPage":1,"recordCountPerPage":"100"},
    "contract_fields":{"startBizYmd":START,"endBizYmd":END,
      "ctrtSrchItm01":START,"ctrtSrchItm02":END,
      "prcmBsneAreaCd":"","bizNo":"","srchSeCd":"CTRT",
      "currentPage":1,"recordCountPerPage":"100"},
    "search_code":{"startBizYmd":START,"endBizYmd":END,
      "intpBidRfrcCndt":"CC CUC","srchSeCd":"CC CUC",
      "currentPage":1,"recordCountPerPage":"100"}
   }
   for idx,(name,values) in enumerate(variants.items()):
    for hname,menu in (("no_menu",None),("official_menu",{"menuCangVal":"FIUA004_01"})):
     headers={"Content-Type":"application/json","Referer":BASE,"User-Agent":"Mozilla/5.0"}
     if menu:headers["Menu-Info"]=json.dumps(menu,ensure_ascii=False)
     req={"dlSrchParamM":values}
     info={"variant":name,"header_profile":hname,"post_path":"/fi/fiu/fiua/UntySrch/srchCtrtSttus.do",
           "map":"dlSrchParamM","request_keys":list(values)}
     try:
      resp=await ctx.request.post(API,data=json.dumps(req,ensure_ascii=False),headers=headers,timeout=30000)
      raw=await resp.body()
      filename=f"contract_list_{idx}_{hname}.json"
      (OUT/filename).write_bytes(raw)
      info.update(http=resp.status,bytes=len(raw),sha256=digest(raw),filename=filename,**shape(raw))
     except Exception as e:info["error"]=type(e).__name__+":"+str(e)[:180]
     doc["requests"].append(info)
     log("PF2_PUBLIC_REAL_CONTRACT_LIST_JSON",info)
     if info.get("http")==200 and info.get("real_contract_rows",0)>0:
      doc["data_received"]=True
      doc["winning_variant"]=name
      doc["winning_header"]=hname
      # Keep a minimal second-page proof as a separate original raw JSON.
      next_payload=json.loads(json.dumps(req));next_payload["dlSrchParamM"]["currentPage"]=2
      try:
       nxt=await ctx.request.post(API,data=json.dumps(next_payload,ensure_ascii=False),
         headers=headers,timeout=30000)
       original=await nxt.body()
       (OUT/"contract_list_page2.json").write_bytes(original)
       doc["second_page"]={"http":nxt.status,"bytes":len(original),
          "sha256":digest(original),**shape(original)}
       log("PF2_PUBLIC_REAL_CONTRACT_PAGE2_JSON",doc["second_page"])
      except Exception as e:doc["page2_error"]=str(e)[:190]
      break
    if doc["data_received"]:break
  finally:await ctx.close();await browser.close()
 (OUT/"summary.json").write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding="utf-8")
 log("PF2_PUBLIC_CONTRACT_JSON_SUMMARY",{k:doc.get(k) for k in
   ("homepage_status","homepage_children","source_http","reference_menu_found",
    "screen_key_hints","ctrt_branch_hints","data_received","winning_variant","winning_header","second_page")})
if __name__=="__main__":asyncio.run(main())
