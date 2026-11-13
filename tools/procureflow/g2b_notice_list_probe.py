#!/usr/bin/env python3
"""Validate public NURI bid-notice LIST discovery before any two-year backfill.

Only metadata, read-only public WebSquare search; no credentials or bypass.
Outputs raw response JSON + diagnostics with explicit date/filter verification.
"""
import asyncio, hashlib, json, os, sys
from pathlib import Path
from playwright.async_api import async_playwright

BASE="https://nuri.g2b.go.kr/"
URL=BASE+"nn/nnb/nnba/selectBidPbancList.do"
MENU='{"menuNo":"15401","menuCangVal":"NNBA001_01","bsneClsfCd":"%EC%97%85130031","scrnNo":"00777"}'
DATES=("20241113","20250701","20261113")
OUT=Path("g2b-notice-list-probe")

def payload(day,page,size):
    return {"dlParamM":{
        "bidPbancNo":"","bidPbancOrd":"","bidPbancNm":"",
        "prcmBsneSeCd":"","bidPbancPgstCd":"","bidMthdCd":"",
        "pbancPstgStDt":day,"pbancPstgEdDt":day,
        "onbsPrnmntStDt":"","onbsPrnmntEdDt":"",
        "recordCountPerPage":str(size),"rowNum":"","kbrdrId":"",
        "pbancInstUntyGrpNo":"","pdngYn":"",
        "currentPage":page,"pbancSttsCd":"","pbancKndCd":"",
        "stdCtrtMthdCd":"","scsbdMthdCd":"","untyGrpNo":"",
        "usrTyCd":"","pbancPstgYn":"Y","frgnrRprsvYn":""
    }}

def infer_lists(r):
    if isinstance(r,list):
        return [("result",r)]
    if isinstance(r,dict):
        return [(k,v) for k,v in r.items() if isinstance(v,list)]
    return []

def atomic(path,raw):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+".new")
    tmp.write_bytes(raw)
    os.replace(tmp,path)
    return hashlib.sha256(raw).hexdigest()

async def main():
    OUT.mkdir(exist_ok=True)
    result=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(channel="chrome",headless=False)
        context=await browser.new_context(locale="ko-KR",timezone_id="Asia/Seoul")
        page=await context.new_page()
        try:
            res=await page.goto(BASE,wait_until="domcontentloaded",timeout=35000)
            print("HOME",json.dumps({"status":res.status if res else None},ensure_ascii=False),flush=True)
            if not res or res.status>=400:raise RuntimeError("NURI home unavailable")
            for day in DATES:
                for size,page_num in ((20,1),(20,2),(100,1)):
                    request=payload(day,page_num,size)
                    urlheaders={"Accept":"application/json",
                                "Content-Type":"application/json;charset=UTF-8",
                                "Menu-Info":MENU,"Target-Id":"btnS0001","Usr-Id":"null",
                                "Origin":BASE.rstrip("/"),"Referer":BASE}
                    response=await context.request.post(URL, data=json.dumps(request,ensure_ascii=False),
                                                        headers=urlheaders, timeout=35000)
                    raw=await response.body()
                    target=OUT/(f"{day}_{size}_{page_num}.json")
                    sha=atomic(target,raw)
                    try:body=json.loads(raw)
                    except ValueError:body={}
                    data=body.get("result") if isinstance(body,dict) else None
                    lists=infer_lists(data)
                    candidates=[(k,v) for k,v in lists if v and isinstance(v[0],dict)]
                    key, rows=max(candidates,key=lambda z:len(z[1])) if candidates else ("",[])
                    samples=[]
                    for row in rows[:3]:
                        samples.append({k:row.get(k) for k in
                            ("bidPbancNo","bidPbancOrd","bidPbancNm",
                             "pbancPstgDt","pbancPstgYmd","pbancPstgTm",
                             "bidPbancDt","bidPbancPgstCd","bidPbancPgstCdNm",
                             "prcmBsneSeCd","bidClsfNo","bidPrgrsOrd")
                            if row.get(k) is not None})
                    record={"day":day,"page":page_num,"requested_rows":size,
                            "http":response.status,"sha256":sha,"raw_path":str(target),
                            "api_code":body.get("ErrorCode") if isinstance(body,dict) else None,
                            "api_message":str(body.get("ErrorMsg") or "")[:180] if isinstance(body,dict) else "",
                            "result_keys":list(data.keys()) if isinstance(data,dict) else [],
                            "list_keys":{k:len(v) for k,v in lists},
                            "chosen_list":key,"rows":len(rows),
                            "row_fields":sorted(rows[0].keys()) if rows else [],
                            "samples":samples}
                    result.append(record)
                    print("NOTICE_LIST_PROBE",json.dumps(record,ensure_ascii=False),flush=True)
                    await asyncio.sleep(0.4)
        finally:
            await context.close()
            await browser.close()
    index={"tested":len(result),"results":result,
           "verified_full_coverage":False,
           "note":"This validates visible list output only; not 2yr full coverage."}
    (OUT/"summary.json").write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding="utf-8")
    return 0 if any(x["http"]==200 and x["rows"] for x in result) else 2

if __name__=="__main__":
    sys.exit(asyncio.run(main()))
