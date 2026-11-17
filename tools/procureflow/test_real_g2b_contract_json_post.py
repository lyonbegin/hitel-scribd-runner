#!/usr/bin/env python3
"""Live read-only G2B contract JSON test from exact official compiled screen code.

The *select* paths and input map are from the served
/_wpack_/ui/fi/fiu/fiua/LinkCtrtMngDtlV.js. This test uses public,
previously documented contract identifiers and the same Chrome API context
as the verified bidder-detail direct-post collector. Never logs in or
calls modify/endpoints.
"""
import asyncio, datetime as dt, hashlib, json, os, re
from pathlib import Path
from playwright.async_api import async_playwright

HOME="https://www.g2b.go.kr/"
JS=HOME+"_wpack_/ui/fi/fiu/fiua/LinkCtrtMngDtlV.js"
KNOWN=(
 "/fi/fiu/fiua/LinkCtrtMng/selectLinkCtrtMng.do",
 "/fi/fiu/fiua/LinkCtrtMng/selectLinkCtrtMngList.do",
)
SAMPLE_CONTRACT_IDS=("R26TA0225667201","R26TA0226116801")
OUT=Path(os.environ.get("RUNNER_TEMP","."))/"pf2-real-contract-json"
OUT.mkdir(parents=True,exist_ok=True)

def sha(d):return hashlib.sha256(d).hexdigest()
def log(k,d):print(k,json.dumps(d,ensure_ascii=False,sort_keys=True),flush=True)

def parsedata(raw):
 try:j=json.loads(raw)
 except ValueError:return {"valid_json":False,"head":raw[:70].decode("utf-8",errors="replace")}
 out={"valid_json":True,"root_type":type(j).__name__}
 if isinstance(j,dict):
  out["keys"]=list(j)[:35];out["error_code"]=j.get("ErrorCode")
  out["error_message"]=str(j.get("ErrorMsg") or "")[:180]
  r=j.get("result")
  out["result_type"]=type(r).__name__
  if isinstance(r,dict):
   out["result_keys"]=list(r)[:35]
   out["list_sizes"]={k:len(v) for k,v in r.items() if isinstance(v,list)}
   out["nonempty_list_fields"]={k:sorted(v[0])[:32] if isinstance(v[0],dict) else []
     for k,v in r.items() if isinstance(v,list) and len(v)>0}
   out["detail_object_fields"]={
     k:sorted(v)[:35] for k,v in r.items()
     if isinstance(v,dict) and len(v)>0
   }
  out["contract_payload_verifiable"]=bool(
    isinstance(r,dict) and any(
      (isinstance(v,list) and len(v)>0 and any(
         any(t in str(col).lower() for t in ("ctrt","cntrct","corp","etps","bzmn"))
         for row in v[:2] if isinstance(row,dict) for col in row)
       ) or
      (isinstance(v,dict) and v and any(
         any(t in str(col).lower() for t in ("ctrt","cntrct","corp","etps","bzmn"))
         for col in v))
      for v in r.values()
    )
  )
 return out

async def main():
 summary={"checked_at":dt.datetime.now(dt.timezone.utc).isoformat(),
    "origin":HOME,"source_js":JS,"tested_paths":list(KNOWN),
    "contract_ids":list(SAMPLE_CONTRACT_IDS),"records":[]}
 async with async_playwright() as pw:
  b=await pw.chromium.launch(channel="chrome",headless=False)
  ctx=await b.new_context(locale="ko-KR",timezone_id="Asia/Seoul")
  try:
   page=await ctx.new_page()
   h=await page.goto(HOME,wait_until="domcontentloaded",timeout=35000)
   summary["homepage_status"]=h.status if h else None
   summary["homepage_body_children"]=await page.evaluate("document.body?.childElementCount||0")
   html=await page.content()
   near=html.find("LinkCtrtMngDtlV.xml")
   if near>=0:
    snippet=html[max(0,near-550):near+100]
    summary["source_menu_hint"]=snippet[-650:]
   src=await ctx.request.get(JS,timeout=25000)
   jb=await src.body()
   summary["screen_js_status"]=src.status
   summary["screen_js_sha256"]=sha(jb)
   source=jb.decode("utf-8",errors="replace")
   summary["verified_read_actions"]=[x for x in KNOWN if x in source]
   summary["source_input_mapping"]=list(dict.fromkeys(re.findall(
      r'inData:\s*["\\\x27]([^"\\\x27]+)',source)))[:25]
   if src.status!=200 or len(summary["verified_read_actions"])!=len(KNOWN):
    raise RuntimeError("Observed contract read endpoints not verified in public JS")
   # Use precisely the same session request pattern as Stage2.
   sem=asyncio.Semaphore(3)
   requests=[]
   for idx,unty in enumerate(SAMPLE_CONTRACT_IDS):
    for endpoint in KNOWN:
     for variant in ("minimum","with_empty_options"):
      requests.append((idx,unty,endpoint,variant))
   async def one(idx,unty,endpoint,variant):
    async with sem:
     m={"untyCtrtMngNo":unty}
     if variant=="with_empty_options":
      m.update(prcmBsneAreaCd="",instSeCd="")
     payload={"dlLinkCtrtMngM":m}
     result={"contract_id":unty,"path":endpoint,"variant":variant,
       "input_map":"dlLinkCtrtMngM","json_keys_sent":list(m)}
     try:
      r=await ctx.request.post(HOME+endpoint.lstrip("/"),
          data=json.dumps(payload,ensure_ascii=False),
          headers={"Content-Type":"application/json","Referer":HOME,
                   "Menu-Info":'{"menuCangVal":"FIUA012_02","scrnNo":"012"}',
                   "User-Agent":"Mozilla/5.0"},
          timeout=30000)
      raw=await r.body()
      dest=OUT/f"contract_json_{idx}_{'detail' if endpoint.endswith('selectLinkCtrtMng.do') else 'list'}_{variant}.json"
      dest.write_bytes(raw)
      result.update(http=r.status,bytes=len(raw),sha256=sha(raw),raw_filename=dest.name)
      result.update(parsedata(raw))
     except Exception as exc:result["exception"]=type(exc).__name__+":"+str(exc)[:200]
     log("PF2_CONTRACT_REAL_POST",result)
     return result
   summary["records"]=await asyncio.gather(*(one(*item) for item in requests))
  finally:
   await ctx.close();await b.close()
 summary["verified_contract_json_rows"]=sum(int(x.get("contract_payload_verifiable") or False) for x in summary["records"])
 (OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
 log("PF2_CONTRACT_REAL_JSON_RESULT",{
    "source_js_http":summary.get("screen_js_status"),
    "homepage_body_children":summary.get("homepage_body_children"),
    "read_actions_found":summary.get("verified_read_actions"),
    "source_input_mapping":summary.get("source_input_mapping"),
    "responses":len(summary["records"]),
    "response_json_count":sum(bool(x.get("valid_json")) for x in summary["records"]),
    "verified_contract_json_rows":summary["verified_contract_json_rows"]
 })
if __name__=="__main__":asyncio.run(main())
