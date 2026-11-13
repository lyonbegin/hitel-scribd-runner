#!/usr/bin/env python3
"""Stage 1: public G2B MAIN national bid-notice INDEX -> independent detail queue.

HITEL self-hosted Windows Chrome/Playwright. Public, anonymous, read-only.
Verified source: PNPE001_01 selectBidPbacScrollTypeList.do
Mandatory: slprRcptDdlnYn="" (N/Y silently exclude most expired notices).
Only a FULLY paginated date becomes "complete". No bidder details in this phase.
"""
from __future__ import annotations
import argparse,asyncio,csv,gzip,hashlib,json,os,re,sys
from datetime import date,timedelta,datetime,timezone
from pathlib import Path
from playwright.async_api import async_playwright

FROM=date(2024,11,13)
TO=date(2026,11,13)
HOME="https://www.g2b.go.kr/"
URL=HOME+"pn/pnp/pnpe/BidPbac/selectBidPbacScrollTypeList.do"
MENU='{"menuNo":"01175","menuCangVal":"PNPE001_01","bsneClsfCd":"%EC%97%85130026","scrnNo":"00941"}'
SUBMIT="mf_wfm_container_tacBidPbancLst_contents_tab2_body_sbmPbancBidPbancLst"
CODES="0000 조070001 조070002 조070003 조070004 조070005 민079999"
PATTERN=re.compile(r"^(R\d{2}BK\d{8}|\d{11})(?:[-－](\d{3}))?$")
DATE=re.compile(r"^(\d{4})/(\d{2})/(\d{2})")
COLUMNS=("bid_no","bid_ord","bid_clsfc_no","bid_prgrs_ord","notice_title",
         "published","category","agency","status","source_day","evidence_page")

def print_event(key,payload):
    print(key,json.dumps(payload,ensure_ascii=False,sort_keys=True),flush=True)

def atomic(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+".new")
    tmp.write_bytes(data)
    os.replace(tmp,path)

def atomic_json(path, j):
    atomic(path,json.dumps(j,ensure_ascii=False,indent=2,sort_keys=True).encode("utf-8"))

def atomic_csv(path, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+".new")
    with tmp.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=COLUMNS,extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp,path)

def request_body(d,page,page_size):
    begin=(page-1)*page_size+1
    end=begin+page_size-1
    return {"dlBidPbancLstM":{
        "prcmBsneSeCd":CODES,"bidPbancNm":"","pbancKndCd":"",
        "fromBidDt":d.strftime("%Y%m%d"),"toBidDt":d.strftime("%Y%m%d"),
        "bsneAllYn":"Y","frcpYn":"Y","rsrvYn":"Y","laseYn":"Y",
        "slprRcptDdlnYn":"",  # CRITICAL: closed historic tenders included
        "infoSysCd":"정010029","contxtSeCd":"콘010006",
        "bidDateType":"R","srchTy":"0",
        "recordCountPerPage":str(page_size),"startIndex":begin,"endIndex":end,
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

def parse_response(raw):
    try:j=json.loads(raw)
    except ValueError as e:raise ValueError("source_not_json") from e
    if (not isinstance(j,dict) or j.get("ErrorCode") not in (0,"0",None) or
        not isinstance(j.get("result"),list)):
        raise ValueError("source_bad_response:"+str(j.get("ErrorMsg") if isinstance(j,dict) else "")[:140])
    if not all(isinstance(x,dict) for x in j["result"]):
        raise ValueError("non_object_notice_rows")
    return j["result"]

def row_to_index(row,day,evidence):
    ident=str(row.get("bidPbancUntyNoOrd") or "").strip()
    match=PATTERN.fullmatch(ident)
    if not match:
        no=str(row.get("bidPbancUntyNo") or "").strip()
        ordinal=str(row.get("bidPbancUntyOrd") or "000").zfill(3)
        match=PATTERN.fullmatch(no+"-"+ordinal)
    if not match:raise ValueError("notice_identifier_unrecognized:"+ident[:70])
    posted=str(row.get("pbancPstgDt") or "")
    dmatch=DATE.match(posted)
    if not dmatch or "".join(dmatch.groups())!=day.strftime("%Y%m%d"):
        raise ValueError("notice_outside_requested_day:"+posted[:24])
    return {"bid_no":match.group(1),"bid_ord":match.group(2) or "000",
        "bid_clsfc_no":str(row.get("bidClsfNo") or "0"),
        "bid_prgrs_ord":str(row.get("bidPrgrsOrd") or "000"),
        "notice_title":str(row.get("bidPbancNm") or ""),
        "published":posted.split("&")[0],"category":str(row.get("prcmBsneSeCdNm") or ""),
        "agency":str(row.get("oderInstUntyGrpNm") or ""),
        "status":str(row.get("pbancSttsNm") or ""),
        "source_day":day.isoformat(),"evidence_page":evidence}

def headers():
    return {"Accept":"application/json","Content-Type":"application/json;charset=UTF-8",
        "Origin":HOME.rstrip("/"),"Referer":HOME,"Menu-Info":MENU,
        "Target-Id":"btnS0004","submissionid":SUBMIT,"Usr-Id":"null"}

async def bounded(a,timeout):
    task=asyncio.ensure_future(a)
    task.add_done_callback(lambda t:None if t.cancelled() else t.exception())
    done,_=await asyncio.wait({task},timeout=timeout)
    if not done:
        task.cancel()
        raise asyncio.TimeoutError(f"operation exceeded {timeout}s")
    return task.result()

async def get_page(ctx, gate, day, page, size):
    async with gate:
        res=await bounded(ctx.request.post(
            URL,data=json.dumps(request_body(day,page,size),ensure_ascii=False),
            headers=headers(),timeout=30000),38)
        raw=await bounded(res.body(),10)
        await asyncio.sleep(0.25)
    if res.status!=200:raise RuntimeError("source_http_"+str(res.status))
    return raw,parse_response(raw)

async def collect_day(ctx,gate,out,day,args):
    folder=out/"days"/day.strftime("%Y%m%d")
    status_path=folder/"status.json"
    if status_path.exists():
        try:
            old=json.loads(status_path.read_text(encoding="utf-8"))
            if old.get("status")=="complete" and (folder/"index.csv").is_file():
                print_event("INDEX_DAY_SKIPPED",{"day":str(day),"rows":old.get("rows",0)})
                return old
        except ValueError:pass
    folder.mkdir(parents=True,exist_ok=True)
    summaries=[]
    index_rows=[]
    seen=set()
    try:
        for page in range(1,args.max_pages+1):
            file=folder/("page_%05d.json.gz"%page)
            if file.exists():
                raw=gzip.decompress(file.read_bytes())
                records=parse_response(raw)
                cache="checkpoint_reuse"
            else:
                raw,records=await get_page(ctx,gate,day,page,args.page_size)
                atomic(file,gzip.compress(raw,compresslevel=6,mtime=0))
                cache="remote"
            digest=hashlib.sha256(raw).hexdigest()
            evidence=str(file.relative_to(out)).replace("\\","/")
            for rec in records:
                row=row_to_index(rec,day,evidence)
                key=tuple(row[c] for c in COLUMNS[:4])
                if key in seen:raise RuntimeError("duplicate_notice_key_across_pages:"+str(key))
                seen.add(key)
                index_rows.append(row)
            summaries.append({"page":page,"rows":len(records),
                              "sha256_uncompressed":digest,"origin":cache})
            print_event("INDEX_PAGE",{"day":str(day),"page":page,"rows":len(records),
                 "cumulative_unique":len(seen),"origin":cache})
            # Some days really may have 0 notices. Without independent official
            # confirmation treat an empty first page as unverified, not full.
            if len(records)<args.page_size or (
                records and str(records[-1].get("nextRowYn") or "").upper()=="N"):
                state="complete" if index_rows else "empty_unverified"
                break
        else:
            state="partial_page_limit"
        if state=="complete":
            atomic_csv(folder/"index.csv",index_rows)
        report={"day":day.isoformat(),"status":state,"rows":len(index_rows),
                "pages":len(summaries),"source":"G2B_main_PNPE001_01",
                "page_size":args.page_size,"evidence":summaries,
                "updated_at":datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        report={"day":day.isoformat(),"status":"error","rows":len(index_rows),
                "pages":len(summaries),"error":type(e).__name__+":"+str(e)[:220],
                "updated_at":datetime.now(timezone.utc).isoformat()}
    atomic_json(status_path,report)
    print_event("INDEX_DAY_RESULT",{k:report.get(k) for k in ("day","status","rows","pages","error")})
    return report

def rebuild_queue(out):
    combined={}
    days=out/"days"
    if not days.exists():return 0
    for f in sorted(days.glob("*/index.csv")):
        state_file=f.parent/"status.json"
        try:state=json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:continue
        if state.get("status")!="complete":continue
        with f.open("r",encoding="utf-8-sig",newline="") as stream:
            for row in csv.DictReader(stream):
                key=tuple(row[c] for c in COLUMNS[:4])
                if key not in combined:combined[key]=row
    atomic_csv(out/"notice_queue.csv",list(combined.values()))
    return len(combined)

async def main(args):
    days=[date.fromisoformat(args.start_date)+timedelta(days=i) for i in range(args.days)]
    if any(x<FROM or x>TO for x in days):raise ValueError("Dates outside fixed two-year scope")
    if args.dry_run:
        print_event("INDEX_PLAN",{"start_date":args.start_date,"days":args.days,
            "date_count_total":(TO-FROM).days+1,"page_size":args.page_size,
            "note":"Complete national historical notices require every day and page."})
        return 0
    output=Path(args.output)
    output.mkdir(parents=True,exist_ok=True)
    queue=asyncio.Queue()
    for day in days:queue.put_nowait(day)
    reports=[]
    gate=asyncio.Semaphore(min(3,args.tabs))
    async with async_playwright() as p:
        browser=await bounded(p.chromium.launch(channel="chrome",headless=False),45)
        ctx=await bounded(browser.new_context(locale="ko-KR",timezone_id="Asia/Seoul"),25)
        home=await ctx.new_page()
        initial=await bounded(home.goto(HOME,wait_until="domcontentloaded",timeout=40000),45)
        if not initial or initial.status>=400:raise RuntimeError("anonymous G2B Chrome home unavailable")
        async def worker(index):
            tab=await ctx.new_page()
            try:
                while True:
                    try:day=queue.get_nowait()
                    except asyncio.QueueEmpty:break
                    reports.append(await collect_day(ctx,gate,output,day,args))
                    queue.task_done()
            finally:
                try:await bounded(tab.close(),5)
                except Exception:pass
        try:await bounded(asyncio.gather(*(worker(i) for i in range(min(args.tabs,len(days))))),args.timeout)
        finally:
            await ctx.close()
            await browser.close()
    count=rebuild_queue(output)
    summary={"period":[FROM.isoformat(),TO.isoformat()],
       "run_days":[days[0].isoformat(),days[-1].isoformat()],
       "days_attempted":len(reports),"day_statuses":{d:sum(r.get("status")==d for r in reports)
            for d in ("complete","partial_page_limit","empty_unverified","error")},
       "queue_unique_bid_execs":count,
       "all_731_days_collected_and_validated":False,
       "source":"G2B_main_PNPE001_01",
       "note":"Notice index queue only; no claim of bidder-detail coverage."}
    atomic_json(output/"index_summary.json",summary)
    print_event("INDEX_FINAL",summary)
    return 0 if len(reports)==len(days) and all(r.get("status")=="complete" for r in reports) else 3

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--start-date",default=FROM.isoformat())
    parser.add_argument("--days",type=int,default=1)
    parser.add_argument("--tabs",type=int,default=10)
    parser.add_argument("--page-size",type=int,default=100)
    parser.add_argument("--max-pages",type=int,default=90)
    parser.add_argument("--timeout",type=int,default=4200)
    parser.add_argument("--output",default="g2b-index-stage1")
    parser.add_argument("--dry-run",action="store_true")
    a=parser.parse_args()
    if not (1<=a.days<=731 and 1<=a.tabs<=10 and a.page_size==100 and
            1<=a.max_pages<=1000 and 60<=a.timeout<=10200):
        parser.error("Invalid bounded options")
    sys.exit(asyncio.run(main(a)))
