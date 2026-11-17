#!/usr/bin/env python3
"""Public read-only G2B direct-post method A/B live experiment.

Reuses the exact proven Stage2 request pattern, one Chrome context, and a ten-tab
bounded worker pool. Does NOT depend on a rendered homepage body or change site
data. Contract endpoints are *discovered*, not invented or invoked blindly.
"""
import asyncio, hashlib, json, re, os, datetime as dt
from pathlib import Path
from playwright.async_api import async_playwright

HOME="https://www.g2b.go.kr/"
BID_URL=HOME+"pb/pbo/pboc/OnbsRslt/selectOnbsRsltSbidGods.do"
MENU='{"menuNo":"15620","scrnNo":"08542"}'
# Two published public examples + one from the source repo's prior probe.
BIDS=("R26BK01795442","R25BK01199984","R25BK00965123")
EXPLICIT_PUBLIC_ASSETS=(
 "/kn/com/js/commonGlobal.js",
 "/kn/com/js/bsneComm.js",
 "/_wpack_/layout/GnbMenuDev.js",
 "/_wpack_/layout/GnbTop.js",
 "/_wpack_/layout/GnbBtm.js",
 "/_wpack_/kn/layout/GnbMenuDev.js",
)
CONTRACT_TERMS=re.compile(r"(?i)cntrct|contract|ctrt|cntr|계약현황|계약정보|계약관리|계약실적")
PATH_RE=re.compile(r"/[A-Za-z0-9_/-]{3,180}\.(?:do|xml|js)")
BLOCK_TERMS=re.compile(r"(?i)(insert|update|delete|save|submit|payment|sign|login|logout)")
ROOT=Path(os.environ.get("RUNNER_TEMP","."))/"pf2-direct-post-contract"
ROOT.mkdir(parents=True,exist_ok=True)

def log(event,data):
 print(event,json.dumps(data,ensure_ascii=False,sort_keys=True),flush=True)

def body(no,page):
 return {"dlSrchOnbsRsltBidInM":{
  "bidPbancNo":no,"bidPbancOrd":"000","bidClsfNo":"0","bidPrgrsOrd":"000",
  "prcmBsneSeCd":"","bidPgstCd":"개찰완료","bzmnRegNo":"","reOpenPbancYN":"",
  "currentPage":page,"recordCountPerPage":"999"
 }}

async def main():
 summary={"when":dt.datetime.now(dt.timezone.utc).isoformat(),
  "scope":"only public read-only known bidder endpoint and static resources",
  "method":"same-context-direct-request-post-without-rendered-UI",
  "workers_configured":10,"bids":[],"contract_route_candidates":[],
  "asset_checks":[],"contract_list_verified":False,"contract_rows_verified":0}
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel="chrome",headless=False)
  ctx=await browser.new_context(locale="ko-KR",timezone_id="Asia/Seoul")
  # Create 10 tabs exactly like working old script, but avoid unnecessary remote POST.
  tabs=[await ctx.new_page() for _ in range(10)]
  try:
   resp=await tabs[0].goto(HOME,wait_until="domcontentloaded",timeout=35000)
   summary["homepage_status"]=resp.status if resp else None
   summary["homepage_body_count"]=await tabs[0].evaluate("document.body?.childElementCount || 0")
   if not resp or resp.status>=400:
    raise RuntimeError("G2B_HOME_UNAVAILABLE")
   gate=asyncio.Semaphore(10)
   async def one(no):
    async with gate:
     item={"bid_no":no,"results":[]}
     for page in (1,):
      try:
       response=await ctx.request.post(
        BID_URL,data=json.dumps(body(no,page),ensure_ascii=False),
        headers={"Content-Type":"application/json","Menu-Info":MENU,
                 "Referer":HOME,"User-Agent":"Mozilla/5.0"},
        timeout=30000)
       raw=await response.body()
       filename=ROOT/(no+"_p"+str(page)+".json")
       filename.write_bytes(raw)
       info={"http":response.status,"bytes":len(raw),
        "sha256":hashlib.sha256(raw).hexdigest(),"page":page,
        "saved_raw":filename.name}
       try:
        parsed=json.loads(raw)
        result=parsed.get("result") if isinstance(parsed,dict) else None
        rows=result.get("successBidInfo") if isinstance(result,dict) else None
        info["error_code"]=parsed.get("ErrorCode") if isinstance(parsed,dict) else None
        info["error_message"]=str(parsed.get("ErrorMsg") or "")[:90] if isinstance(parsed,dict) else ""
        info["result_keys"]=sorted(result.keys())[:20] if isinstance(result,dict) else []
        info["row_count"]=len(rows) if isinstance(rows,list) else None
        info["real_row_verified"]=bool(response.status==200 and isinstance(rows,list) and len(rows)>0)
        if isinstance(rows,list) and rows:
         info["first_row_fields"]=sorted(rows[0])[:30] if isinstance(rows[0],dict) else []
         info["total_count"]=rows[0].get("totCnt") if isinstance(rows[0],dict) else None
       except ValueError:
        info["parse_error"]="invalid_json"
       item["results"].append(info)
       log("PF2_DIRECT_POST_BID",{"bid_no":no,**info})
      except Exception as e:
       item["results"].append({"error":type(e).__name__+":"+str(e)[:180]})
     return item
   summary["bids"]=await asyncio.gather(*(one(no) for no in BIDS))
   summary["proven_bidder_response_count"]=sum(
    int(x.get("real_row_verified") or False)
    for b in summary["bids"] for x in b["results"]
   )
   # Only public JS files already exposed by the website; no fabricated
   # contract endpoint requests. Candidates are source hints, not successes.
   for route in EXPLICIT_PUBLIC_ASSETS:
    entry={"asset":route}
    try:
     r=await ctx.request.get(HOME+route.lstrip("/"),timeout=20000)
     data=await r.body()
     entry.update(http=r.status,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
     if r.status==200 and len(data)<3500000:
      text=data.decode("utf-8",errors="replace")
      matches=[]
      for m in PATH_RE.finditer(text):
       match=m.group()
       near=text[max(m.start()-160,0):m.end()+160]
       if CONTRACT_TERMS.search(near) or CONTRACT_TERMS.search(match):
        if not BLOCK_TERMS.search(match):
         matches.append(match)
      entry["contract_nearby_paths"]=sorted(set(matches))[:35]
      summary["contract_route_candidates"].extend(entry["contract_nearby_paths"])
    except Exception as e:
     entry["error"]=type(e).__name__+":"+str(e)[:150]
    summary["asset_checks"].append(entry)
   summary["contract_route_candidates"]=sorted(set(summary["contract_route_candidates"]))
   # The only contract deep-link path tested below is published in official
   # procurement contract URL fields. No invented query, login, or mutation.
   public_contract_link=HOME+"link/FIU"
   try:
    response=await ctx.request.get(public_contract_link,timeout=20000,max_redirects=5)
    raw=await response.body()
    target=ROOT/"official_contract_link_FIU.html"
    target.write_bytes(raw)
    summary["contract_link_probe"]={
      "published_url":public_contract_link,
      "http":response.status,
      "final_url":response.url.split("?")[0],
      "mime":response.headers.get("content-type","").split(";")[0],
      "bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),
      "saved_raw":target.name,
      "has_contract_content":bool(
        CONTRACT_TERMS.search(raw.decode("utf-8",errors="replace"))
        and response.status==200
      ),
      "note":"Keyword in HTML is not verified contract data; absent contract ID/link params"
    }
    log("PF2_DIRECT_CONTRACT_LINK",summary["contract_link_probe"])
   except Exception as e:
    summary["contract_link_probe"]={"url":public_contract_link,"error":type(e).__name__+":"+str(e)[:180]}
    log("PF2_DIRECT_CONTRACT_LINK",summary["contract_link_probe"])
  finally:
   await ctx.close()
   await browser.close()
 (ROOT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
 log("PF2_DIRECT_POST_FINAL",{k:v for k,v in summary.items() if k not in ("asset_checks","bids")})
 log("PF2_ASSET_CANDIDATES",{"assets":summary["asset_checks"]})
 # This is a successful experiment even when the official contract route is not
 # yet identified; the report MUST explicitly distinguish those outcomes.
 return 0

if __name__=="__main__":
 raise SystemExit(asyncio.run(main()))
