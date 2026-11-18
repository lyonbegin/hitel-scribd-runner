#!/usr/bin/env python3
"""Live G2B Data Hub report list JSON: direct same-session HTTP POST test.

The read-only path is extracted from the official WebSquare ReptLstM.js.
No writes, login, proxy, cookie export, or user-specific authenticated API.
"""
import asyncio,datetime as dt,hashlib,json,os
from pathlib import Path
from playwright.async_api import async_playwright

HOST="https://data.g2b.go.kr/"
SCREEN=HOST+"_wpack_/ui/ai/ais/aisc/ReptLstM.js"
API=HOST+"ai/ais/aisc/ReptLst/selectReptSrchV2Lst.do"
OUT=Path(os.getenv("RUNNER_TEMP","."))/"pf2-datahub-real-json"
OUT.mkdir(parents=True,exist_ok=True)

def checksum(x):return hashlib.sha256(x).hexdigest()
def log(name,obj):print(name,json.dumps(obj,ensure_ascii=False,sort_keys=True),flush=True)
def summary(raw):
 try:r=json.loads(raw)
 except ValueError:return {"is_json":False,"body_prefix":raw[:70].decode("utf-8",errors="replace")}
 s={"is_json":True,"root_type":type(r).__name__}
 if not isinstance(r,dict):return s
 s["error_code"]=r.get("ErrorCode")
 s["error_message"]=str(r.get("ErrorMsg") or "")[:160]
 s["top_keys"]=list(r)[:30]
 maps={}
 for k,v in r.items():
  if isinstance(v,list):maps[k]={"type":"list","rows":len(v),"first_fields":sorted(v[0])[:50] if v and isinstance(v[0],dict) else []}
  elif isinstance(v,dict):maps[k]={"type":"dict","keys":list(v)[:30]}
 s["maps"]=maps
 items=[(k,v) for k,v in r.items() if isinstance(v,list) and v and isinstance(v[0],dict)]
 samples=[]
 for key,rows in items:
  for row in rows[:3]:
   safe_fields=("hubReptNo","reptNm","reptSubNm","hubReptTyCd","hubReptDscrSummCn","reptKwSeTy","prcmBsneAreaCd","dataStndNm")
   samples.append({"list":key,"fields":{k:str(row[k])[:180] for k in safe_fields if k in row}})
 s["sample_rows"]=samples[:7]
 s["data_rows"]=sum(len(v) for k,v in items)
 return s

async def main():
 rep={"tested_at":dt.datetime.now(dt.timezone.utc).isoformat(),"host":HOST,"endpoint":API,
      "test_cases":[],"data_received":False}
 async with async_playwright() as pw:
  br=await pw.chromium.launch(channel="chrome",headless=False)
  ctx=await br.new_context(locale="ko-KR",timezone_id="Asia/Seoul")
  try:
   home=await ctx.new_page()
   r=await home.goto(HOST,wait_until="domcontentloaded",timeout=35000)
   rep["home_http"]=r.status if r else None
   rep["home_body_children"]=await home.evaluate("document.body?.childElementCount || 0")
   js=await ctx.request.get(SCREEN,timeout=22000)
   rawjs=await js.body()
   rep["screen_status"]=js.status
   rep["screen_sha256"]=checksum(rawjs)
   text=rawjs.decode("utf-8",errors="replace")
   if js.status!=200 or "/ai/ais/aisc/ReptLst/selectReptSrchV2Lst.do" not in text:
    raise RuntimeError("Official report list select endpoint not observed")
   variants=[
    ("contract",{"reptNm":"계약","reptKwSeTy":"","currentPage":1,"recordCountPerPage":"50"}),
    ("supplier",{"reptNm":"조달업체","reptKwSeTy":"","currentPage":1,"recordCountPerPage":"50"}),
    ("exact_report_id",{"reptNm":"UI-ADOXFA-113R","currentPage":1,"recordCountPerPage":"50"}),
    ("all_reports",{"reptNm":"","currentPage":1,"recordCountPerPage":"50"}),
   ]
   for i,(name,params) in enumerate(variants):
    for profile,menu in (("no_menu",None),("official_menu",'{"menuNo":"24045","scrnNo":"04949"}')):
     headers={"Content-Type":"application/json","Referer":HOST,"User-Agent":"Mozilla/5.0"}
     if menu:headers["Menu-Info"]=menu
     req={"dlSrchParamM":params}
     entry={"variant":name,"profile":profile,"params":list(params),"endpoint":"/ai/ais/aisc/ReptLst/selectReptSrchV2Lst.do"}
     try:
      rr=await ctx.request.post(API,headers=headers,data=json.dumps(req,ensure_ascii=False),timeout=30000)
      body=await rr.body()
      filename=f"datahub_report_{i}_{profile}.json"
      (OUT/filename).write_bytes(body)
      entry.update(http=rr.status,bytes=len(body),sha256=checksum(body),file=filename,**summary(body))
      if rr.status==200 and entry.get("data_rows",0)>0:
       rep["data_received"]=True
       rep["winner"]={"variant":name,"profile":profile,"rows":entry["data_rows"],"file":filename}
     except Exception as exc:entry["error"]=type(exc).__name__+":"+str(exc)[:180]
     log("PF2_REAL_DATAHUB_JSON",entry)
     rep["test_cases"].append(entry)
     if rep["data_received"]:break
    if rep["data_received"]:break
  finally:await ctx.close();await br.close()
 (OUT/"summary.json").write_text(json.dumps(rep,ensure_ascii=False,indent=2),encoding="utf-8")
 log("PF2_REAL_DATAHUB_SUMMARY",{k:rep.get(k) for k in ("home_http","home_body_children","screen_status","screen_sha256","data_received","winner")})
if __name__=="__main__":asyncio.run(main())
