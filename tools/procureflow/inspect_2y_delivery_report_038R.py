#!/usr/bin/env python3
"""Locate the public *delivery order history* report and its actual read request.

Do not confuse currently searchable shopping catalogue with historical deliveries.
Exact official catalogue report ID UI-ADOXAA-038R from data.go.kr 15053481.
Every HTTP response is retained with SHA256, and public read-only actions only.
"""
import asyncio,datetime as dt,hashlib,json,os,re
from pathlib import Path
from playwright.async_api import async_playwright

ROOT="https://data.g2b.go.kr/"
HOME=ROOT+"link/AISC001_01/?reptNm=UI-ADOXAA-038R"
LIST=ROOT+"ai/ais/aisc/ReptLst/selectReptSrchV2Lst.do"
SOURCES=(
 "/_wpack_/ui/ai/ais/aisc/ReptLstM.js",
 "/_wpack_/ui/ai/ais/aisc/SprnReptDtlT.js",
 "/_wpack_/ui/ai/ais/aisc/AtplReptDtlT.js",
 "/_wpack_/ui/ai/ais/aisc/SemReptDtlT.js",
 "/_wpack_/ui/ai/ais/aisc/VisReptDtlT.js",
)
OUT=Path(os.getenv("RUNNER_TEMP","."))/"procureflow-two-year-delivery-report"
OUT.mkdir(parents=True,exist_ok=True)
PATTERN=re.compile(r"(?i)action\s*:|(?:select|search|srch|query|inq)[a-zA-Z0-9_]*\.do|/[\w/-]{9,160}\.do|download|csv|excel|hubReptNo|reptId|reptNm")
def digest(b):return hashlib.sha256(b).hexdigest()
def write(name,b): (OUT/name).write_bytes(b);return {"file":name,"bytes":len(b),"sha256":digest(b)}
def safe_excerpt(t,rx,n=55):
 matches=[];seen=set()
 for m in rx.finditer(t):
  v=" ".join(t[max(0,m.start()-170):min(len(t),m.end()+280)].split())[:460]
  if "token" in v.lower() or "session" in v.lower() or "password" in v.lower():continue
  if v not in seen:
   seen.add(v);matches.append(v)
   if len(matches)>=n:break
 return matches
def obs(name,d):print(name,json.dumps(d,ensure_ascii=False,sort_keys=True),flush=True)
async def main():
 report={"window":{"from":"2024-11-18","through":"2026-11-18"},"run_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
         "official_report":"UI-ADOXAA-038R","catalogue":[],"screen_sources":[]}
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel="chrome",headless=False)
  ctx=await browser.new_context(locale="ko-KR",timezone_id="Asia/Seoul")
  try:
   pg=await ctx.new_page()
   rsp=await pg.goto(HOME,wait_until="domcontentloaded",timeout=35000)
   raw=await rsp.body() if rsp else b""
   report["entry"]={"http":rsp.status if rsp else None,"url":HOME,
      "source":write("report_038R_entry.html",raw)}
   # 038R is a report ID, not a product search keyword.
   for idx,name in enumerate(("나라장터쇼핑몰 납품요구","납품요구","UI-ADOXAA-038R","")):
    body={"dlSrchParamM":{"reptNm":name,"reptKwSeTy":"","currentPage":1,"recordCountPerPage":"100"}}
    item={"keyword":name,"input_map":"dlSrchParamM"}
    try:
     r=await ctx.request.post(LIST,data=json.dumps(body,ensure_ascii=False),
         headers={"Content-Type":"application/json","Referer":ROOT},timeout=28000)
     data=await r.body()
     item.update(http=r.status,source=write(f"report_catalogue_{idx}.json",data))
     j=json.loads(data)
     rows=j.get("result",[]) if isinstance(j,dict) else []
     item["error_code"]=j.get("ErrorCode") if isinstance(j,dict) else None
     item["row_count"]=len(rows) if isinstance(rows,list) else None
     if isinstance(rows,list):
      item["matches"]=[{k:str(row.get(k,""))[:220] for k in
       ("hubReptNo","reptNm","reptSubNm","hubReptDscrSummCn","mstrReptIdVal","mstrReptNoVal","hubReptTyCd")}
       for row in rows if isinstance(row,dict) and
       any(w in str(row.get("reptNm",""))+str(row.get("reptSubNm","")) for w in ("납품요구","납품","쇼핑몰","계약"))][:40]
    except Exception as e:item["error"]=type(e).__name__+":"+str(e)[:180]
    report["catalogue"].append(item)
    obs("PF2_DELIVERY_REPORT_CATALOGUE",item)
    if item.get("matches"):break
   for i,path in enumerate(SOURCES):
    entry={"path":path}
    try:
     r=await ctx.request.get(ROOT+path.lstrip("/"),timeout=20000)
     b=await r.body()
     entry.update(http=r.status,mime=r.headers.get("content-type","").split(";")[0],
        source=write(f"report_detail_{i}.js",b))
     if r.status==200 and "javascript" in entry["mime"]:
      t=b.decode("utf-8",errors="replace")
      entry["actions"]=safe_excerpt(t,PATTERN,80)
      entry["read_only_do_paths"]=sorted(set(x for x in re.findall(r"/[\w/-]{9,160}\.do",t)
         if not re.search(r"(?i)(update|save|delete|insert|submit|register|write|process)",x)))[:95]
    except Exception as e:entry["error"]=type(e).__name__+":"+str(e)[:150]
    report["screen_sources"].append(entry)
    obs("PF2_DELIVERY_REPORT_SCREEN",entry)
  finally:await ctx.close();await browser.close()
 (OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
 obs("PF2_DELIVERY_REPORT_SUMMARY",{"catalogue_queries":len(report["catalogue"]),
   "candidate_report_rows":sum(len(x.get("matches",[])) for x in report["catalogue"]),
   "screen_source_count":len(report["screen_sources"]),
   "report_data_download_verified":False})
if __name__=="__main__":asyncio.run(main())
