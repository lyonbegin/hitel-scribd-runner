#!/usr/bin/env python3
"""Retrieve live G2B data hub 038R delivery report *metadata* via source-observed POST.

Differentiate report descriptive schema and actual delivered item records.
No guessed MicroStrategy data calls and no logged-in credentials.
"""
import asyncio,hashlib,json,os,re,datetime as dt
from pathlib import Path
from playwright.async_api import async_playwright
HOST="https://data.g2b.go.kr/"
SEARCH=HOST+"ai/ais/aisc/ReptLst/selectReptSrchV2Lst.do"
DETAIL=HOST+"ai/ais/aisc/ReptDtnr/selectReptBfPritm.do"
SRC=HOST+"_wpack_/ui/ai/ais/aisc/SprnReptDtlT.js"
OUT=Path(os.getenv("RUNNER_TEMP","."))/"pf2-038r-metadata"
OUT.mkdir(parents=True,exist_ok=True)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def show(name,object):print(name,json.dumps(object,ensure_ascii=False,sort_keys=True),flush=True)
def save(name,raw):
 (OUT/name).write_bytes(raw)
 return {"original_file":name,"bytes":len(raw),"sha256":sha(raw)}
def parse(raw):
 try:d=json.loads(raw)
 except ValueError:return {"valid_json":False,"prefix":raw[:120].decode("utf-8",errors="replace")}
 if not isinstance(d,dict):return {"type":type(d).__name__}
 p={"valid_json":True,"keys":list(d),"ErrorCode":d.get("ErrorCode"),"ErrorMsg":str(d.get("ErrorMsg") or "")[:140]}
 result=d.get("result")
 if isinstance(result,dict):
  p["result_type"]="dict"
  p["result_keys"]=list(result)
  p["result_fields"]={k:(str(v)[:230] if isinstance(v,(str,int,float,bool)) else type(v).__name__)
     for k,v in result.items() if not re.search(r"(?i)password|secret|accessToken|sessionKey",k)}
 elif isinstance(result,list):
  p["result_type"]="list"
  p["result_rows"]=len(result)
  if result and isinstance(result[0],dict):
   p["result_first_keys"]=list(result[0])

 for k,v in d.items():
  if isinstance(v,list):
   p[k+"_rows"]=len(v)
   if v and isinstance(v[0],dict):p[k+"_first_row_keys"]=sorted(v[0])
  elif isinstance(v,dict):
   p[k+"_fields"]={a:(str(b)[:170] if isinstance(b,(str,int,float)) else type(b).__name__) for a,b in v.items()
     if not re.search(r"(?i)password|secret|token|key",a)}
 return p
async def main():
 report={"started":dt.datetime.now(dt.timezone.utc).isoformat(),"source_report_id":"UI-ADOXAA-038R",
   "window":"20241118-20261118","results":[]}
 async with async_playwright() as pw:
  br=await pw.chromium.launch(channel="chrome",headless=False)
  ctx=await br.new_context(locale="ko-KR",timezone_id="Asia/Seoul")
  try:
   pg=await ctx.new_page()
   h=await pg.goto(HOST,wait_until="domcontentloaded",timeout=35000)
   report["home_http"]=h.status if h else None
   j=await ctx.request.post(SEARCH,
     data=json.dumps({"dlSrchParamM":{"reptNm":"나라장터쇼핑몰 납품요구",
           "reptKwSeTy":"","currentPage":1,"recordCountPerPage":"50"}},ensure_ascii=False),
     headers={"Content-Type":"application/json","Referer":HOST},timeout=23000)
   raw=await j.body();report["catalogue_source"]=save("catalogue.json",raw)
   data=json.loads(raw);rows=data.get("result",[])
   match=next((r for r in rows if r.get("mstrReptNoVal")=="UI-ADOXAA-038R"),None)
   if not match:
    raise RuntimeError("OFFICIAL_038R_NOT_IN_LIVE_CATALOGUE")
   report["report"]={key:match.get(key) for key in
      ("hubReptNo","reptNm","reptSubNm","mstrReptNoVal","hubReptTyCd")}
   # Metadata ID is a public MicroStrategy report object ID shown in catalogue.
   ids=str(match.get("mstrReptIdVal") or "").split(",")
   for i,objectid in enumerate(ids[:2]):
    payload={"dlSrchParamM":{"reptId":str(match.get("hubReptNo")),
      "hubReptNo":str(match.get("hubReptNo")),"objectType":"",
      "mstrReptIdVal":objectid}}
    r=await ctx.request.post(DETAIL,
       data=json.dumps(payload,ensure_ascii=False),
       headers={"Content-Type":"application/json","Referer":HOST},timeout=24000)
    dat=await r.body()
    item={"type":"report_metadata","variant":"all_period" if i==0 else "post_2021",
       "http":r.status,"source":save(f"metadata_{i}.json",dat),
       **parse(dat)}
    report["results"].append(item)
    show("PF2_038R_REPORT_METADATA",item)
   sr=await ctx.request.get(SRC,timeout=23000);sb=await sr.body()
   t=sb.decode("utf-8",errors="replace")
   report["ui_js_source"]={"http":sr.status,"file":save("SprnReptDtlT.js",sb)}
   # Exact, observed method mapping: report data is MicroStrategy instead of
   # the WebSquare selectReptBfPritm.do metadata endpoint.
   report["execution_flow"]={
      "metadata_url":DETAIL,
      "microstrategy_getMstrResult_mentioned":"mstr.getMstrResult(" in t,
      "microstrategy_downloadCsv_mentioned":"mstr.downloadCsv(" in t,
      "microstrategy_getMstrPrompt_mentioned":"mstr.getMstrPrompt(" in t,
      "data_csv_actual_verified":False}
  finally:await ctx.close();await br.close()
 (OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
 show("PF2_038R_METADATA_FINAL",{"report":report.get("report"),"flow":report.get("execution_flow"),
      "results":[{"variant":x.get("variant"),"http":x.get("http"),
         "ErrorCode":x.get("ErrorCode"),"result_keys":x.get("result_keys"),"result_fields":x.get("result_fields")}
         for x in report["results"]]})
if __name__=="__main__":asyncio.run(main())
