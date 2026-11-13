#!/usr/bin/env python3
"""Verify real nationwide G2B PNPE001_01 notice list independently of bidder detail.

Uses public read-only WebSquare traffic with browser-issued anonymous session.
Based on the source-verified request contract, not the NURI/private-only index.
"""
import asyncio,hashlib,json,re,sys,os
from pathlib import Path
from playwright.async_api import async_playwright

HOME="https://www.g2b.go.kr/"
URL=HOME+"pn/pnp/pnpe/BidPbac/selectBidPbacScrollTypeList.do"
MENU='{"menuNo":"01175","menuCangVal":"PNPE001_01","bsneClsfCd":"%EC%97%85130026","scrnNo":"00941"}'
SUBMIT="mf_wfm_container_tacBidPbancLst_contents_tab2_body_sbmPbancBidPbancLst"
OUT=Path("g2b-main-notices-probe")
DATES=("20241113","20250701","20261113")
ALL_CODES="조070001 조070002 조070003 조070004 조070005"

def payload(day,start=1,count=100,codes=ALL_CODES,kind=""):
    return {"dlBidPbancLstM":{
        "prcmBsneSeCd":codes,"bidPbancNm":"","pbancKndCd":kind,
        "fromBidDt":day,"toBidDt":day,
        "bsneAllYn":"Y","frcpYn":"Y","rsrvYn":"Y","laseYn":"Y",
        "slprRcptDdlnYn":"N","infoSysCd":"정010029",
        "contxtSeCd":"콘010006","bidDateType":"R","srchTy":"0",
        "recordCountPerPage":str(count),"startIndex":start,"endIndex":start+count-1,
        "bidPbancNo":"","bidPbancOrd":"","untyBidPbancNo":"",
        "prcmBsneUntyNoOrd":"","pbancPstgDt":"","ldocNoVal":"",
        "bidPrspPrce":"","ctrtDmndRcptNo":"","dmstcOvrsSeCd":"",
        "ctrtTyCd":"","bidCtrtMthdCd":"","scsbdMthdCd":"",
        "minBidPrspPrce":"","maxBidPrspPrce":"","untyGrpGb":"",
        "dmstNm":"","pbancPicNm":"","odnLmtLgdngCd":"",
        "odnLmtLgdngNm":"","intpCd":"","intpNm":"",
        "dtlsPrnmNo":"","dtlsPrnmNm":"","lcrtTyCd":"",
        "isMas":"","isElpdt":"","oderInstUntyGrpNo":"",
        "instSearchRangeYn":"","esdacYn":"","brcoOrgnCd":"",
        "deptOrgnCd":"","isShop":"","cangParmVal":"","currentPage":""
    }}

def sha_write(path,raw):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".new")
    tmp.write_bytes(raw)
    os.replace(tmp,path)
    return hashlib.sha256(raw).hexdigest()

def report(item):
    print("G2B_MAIN_NOTICE_PROBE",json.dumps(item,ensure_ascii=False),flush=True)

async def main():
    OUT.mkdir(exist_ok=True)
    rows=[]
    headers={"Accept":"application/json","Content-Type":"application/json;charset=UTF-8",
        "Origin":HOME.rstrip("/"),"Referer":HOME,"Menu-Info":MENU,
        "Target-Id":"btnS0004","submissionid":SUBMIT,"Usr-Id":"null"}
    async with async_playwright() as p:
        browser=await p.chromium.launch(channel="chrome",headless=False)
        ctx=await browser.new_context(locale="ko-KR",timezone_id="Asia/Seoul")
        page=await ctx.new_page()
        try:
            resp=await page.goto(HOME,wait_until="domcontentloaded",timeout=40000)
            report({"home_http":resp.status if resp else None})
            if not resp or resp.status>=400:raise RuntimeError("G2B homepage blocked")
            for day in DATES:
                for label,codes,kind,start in (
                    ("all-codes",ALL_CODES,"",1),
                    ("all-blank","","",1),
                    ("default-kind",ALL_CODES,"공440002",1),
                    ("next-page",ALL_CODES,"",101)):
                    try:
                        res=await ctx.request.post(URL,data=json.dumps(payload(day,start,codes=codes,kind=kind),ensure_ascii=False),headers=headers,timeout=35000)
                        raw=await res.body()
                        digest=sha_write(OUT/(day+"_"+label+".json"),raw)
                        try:j=json.loads(raw)
                        except Exception:j={}
                        data=j.get("result") if isinstance(j,dict) else None
                        out=data if isinstance(data,list) else (data.get("list") if isinstance(data,dict) else [])
                        out=out if isinstance(out,list) else []
                        dates=[str(r.get("pbancPstgDt") or "") for r in out if isinstance(r,dict)]
                        cands=[{"id":r.get("bidPbancUntyNoOrd"),"posted":r.get("pbancPstgDt"),
                                "category":r.get("prcmBsneSeCdNm")}
                               for r in out[:3] if isinstance(r,dict)]
                        entry={"day":day,"case":label,"http":res.status,
                               "rows":len(out),"total_reported":j.get("totCnt") if isinstance(j,dict) else None,
                               "api_code":j.get("ErrorCode") if isinstance(j,dict) else None,
                               "api_error":str(j.get("ErrorMsg") or "")[:100] if isinstance(j,dict) else "",
                               "posted_date_matches":sum(day in d.replace("/","").replace("-","") for d in dates),
                               "first":cands,"result_type":type(data).__name__,
                               "response_keys":list(j.keys()) if isinstance(j,dict) else [],
                               "fields":sorted(out[0].keys())[:45] if out and isinstance(out[0],dict) else [],
                               "sha256":digest}
                        report(entry);rows.append(entry)
                    except Exception as e:
                        entry={"day":day,"case":label,"error":type(e).__name__+":"+str(e)[:200]}
                        report(entry);rows.append(entry)
                    await asyncio.sleep(0.5)
        finally:
            await ctx.close()
            await browser.close()
    summary={"results":rows,"national_coverage_verified":False,
        "description":"Only G2B main notice list request and one-day samples, not two-year count."}
    (OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    return 0 if any(z.get("http")==200 and z.get("rows",0)>0 for z in rows) else 2

if __name__=="__main__":
    sys.exit(asyncio.run(main()))
