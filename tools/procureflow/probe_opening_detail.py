#!/usr/bin/env python3
"""Read-only live check: public G2B complete bidder details, no API key.

References: yonghwan86/narajangteo-searcher/src/lib/openg-scraper.ts
and ProcureFlow g2b_bid_collector.py. This is a DIAGNOSTIC, not collection.
"""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime,timezone

URL="https://www.g2b.go.kr/pb/pbo/pboc/OnbsRslt/selectOnbsRsltSbidGods.do"
MENU='{"menuNo":"15620","scrnNo":"08542"}'
BIDS=[
  ("20240516360","000"),       # published public sample: old 11-digit number
  ("R25BK01199984","000"),     # public sample: new style
  ("R25BK00965123","000"),
]
def emit(key,data):
    print(key,json.dumps(data,ensure_ascii=False),flush=True)

async def main():
    from playwright.async_api import async_playwright
    results=[]
    out=Path("g2b-open-detail-probe")
    out.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch(channel="chrome",headless=False)
        context=await browser.new_context(locale="ko-KR",timezone_id="Asia/Seoul")
        page=await context.new_page()
        try:
            start=await page.goto("https://www.g2b.go.kr/",wait_until="domcontentloaded",timeout=35000)
            emit("G2B_HOME",{"http":start.status if start else None,"url":page.url})
            if start is None or start.status>=400:raise RuntimeError("G2B home unavailable")
            for number,order in BIDS:
                evidence={"bid_no":number,"bid_ord":order,"attempts":[],"verified":False,"bidder_count":0}
                for business in ("","03","01"):
                    body={"dlSrchOnbsRsltBidInM":{
                        "bidPbancNo":number,"bidPbancOrd":order,"bidClsfNo":"0",
                        "bidPrgrsOrd":"000","prcmBsneSeCd":business,
                        "bidPgstCd":"개찰완료","bzmnRegNo":"","reOpenPbancYN":"",
                        "currentPage":1,"recordCountPerPage":"999",
                    }}
                    try:
                        response=await context.request.post(URL,
                           data=json.dumps(body,ensure_ascii=False),
                           headers={"Content-Type":"application/json","Menu-Info":MENU,
                                    "User-Agent":"Mozilla/5.0","Referer":"https://www.g2b.go.kr/"},
                           timeout=30000)
                        raw=await response.body()
                        name=number+"_"+(business or "blank")
                        target=out/(name+".json")
                        target.write_bytes(raw)
                        digest=hashlib.sha256(raw).hexdigest()
                        try: parsed=json.loads(raw)
                        except ValueError:parsed={}
                        result=parsed.get("result") if isinstance(parsed,dict) else {}
                        rows=result.get("successBidInfo") if isinstance(result,dict) else None
                        rows=rows if isinstance(rows,list) else []
                        attempt={"business_code":business or "blank","http":response.status,
                           "row_count":len(rows),"sha256":digest,"raw_path":str(target),
                           "total_count":rows[0].get("totCnt") if rows else None,
                           "first_row_fields":sorted(rows[0]) if rows else [],
                           "error_code":parsed.get("ErrorCode") if isinstance(parsed,dict) else None,
                           "error_message":str(parsed.get("ErrorMsg",""))[:140] if isinstance(parsed,dict) else ""}
                        evidence["attempts"].append(attempt)
                        emit("DETAIL_ATTEMPT",{"bid":number,**attempt})
                        if response.status==200 and rows:
                            evidence["verified"]=True
                            evidence["bidder_count"]=len(rows)
                            # A result with 1 row is not a verified full bidder list.
                            evidence["full_list_verified"]=(
                                int(rows[0].get("totCnt") or len(rows)) == len(rows)
                                and str(rows[-1].get("nextRowYn") or "N").upper()!="Y"
                            )
                            break
                    except Exception as e:
                        evidence["attempts"].append({"business_code":business,
                          "exception":type(e).__name__+":"+str(e)[:160]})
                        emit("DETAIL_EXCEPTION",{"bid":number,"error":str(e)[:160]})
                    await asyncio.sleep(0.4)
                results.append(evidence)
        finally:
            await context.close()
            await browser.close()
    summary={"source":"G2B public WebSquare, no login","checked_at":datetime.now(timezone.utc).isoformat(),
      "bids":results,"verified_bid_count":sum(x["verified"] for x in results),
      "not_full_two_year_collection":True}
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    emit("DETAIL_PROBE_SUMMARY",{"verified":summary["verified_bid_count"],
      "counts":[{"id":x["bid_no"],"count":x["bidder_count"],
                 "verified":x["verified"],"full":x.get("full_list_verified")} for x in results]})
    return 0 if summary["verified_bid_count"] else 2

if __name__=="__main__":
    sys.exit(asyncio.run(main()))
