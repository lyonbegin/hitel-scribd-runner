#!/usr/bin/env python3
"""Stage 2: consume Stage1 notice_queue.csv and fetch ALL public G2B bidder rows.

Separate from bid notice discovery; uses the 2026-11-13 verified live WebSquare
detail request (2 records returned 3 and 52 full bidder rows). Read-only.
Never equates a public 422 "no opening data" with zero bidders or failure to bid.
"""
from __future__ import annotations
import argparse,asyncio,csv,gzip,hashlib,json,os,re,sys,shutil
from datetime import datetime,timezone
from pathlib import Path
from playwright.async_api import async_playwright

HOME="https://www.g2b.go.kr/"
URL=HOME+"pb/pbo/pboc/OnbsRslt/selectOnbsRsltSbidGods.do"
MENU='{"menuNo":"15620","scrnNo":"08542"}'
COLUMNS=("bid_no","bid_ord","bid_clsfc_no","bid_prgrs_ord",
         "bidder_name","business_no","rank","bid_amount","bid_rate",
         "qualified","remarks","bid_time","evidence_page")
PATTERN=re.compile(r"^(R\d{2}BK\d{8}|\d{11})$")

def log(event,obj):
    print(event,json.dumps(obj,ensure_ascii=False,sort_keys=True),flush=True)

def atomic(path,body):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+".new")
    tmp.write_bytes(body)
    os.replace(tmp,path)

def json_out(path,j):
    atomic(path,json.dumps(j,ensure_ascii=False,sort_keys=True,indent=2).encode("utf-8"))

def csv_out(path,records):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+".new")
    with tmp.open("w",encoding="utf-8-sig",newline="") as stream:
        w=csv.DictWriter(stream,fieldnames=COLUMNS,extrasaction="ignore")
        w.writeheader()
        w.writerows(records)
    os.replace(tmp,path)

def key(row):
    return [str(row.get(k) or v) for k,v in (
        ("bid_no",""),("bid_ord","000"),("bid_clsfc_no","0"),("bid_prgrs_ord","000"))]

def folder_for(out,entry):
    parts=key(entry)
    if not PATTERN.fullmatch(parts[0]):raise ValueError("Invalid bid number")
    if not all(re.fullmatch(r"\d{1,3}",s) for s in parts[1:]):
        raise ValueError("Invalid notice round")
    return out/"bids"/(parts[0]+"_"+parts[1]+"_"+parts[2]+"_"+parts[3])

def payload(entry,page):
    no,ord_,clsfc,progress=key(entry)
    return {"dlSrchOnbsRsltBidInM":{
        "bidPbancNo":no,"bidPbancOrd":ord_,"bidClsfNo":clsfc,
        "bidPrgrsOrd":progress,"prcmBsneSeCd":"",
        "bidPgstCd":"개찰완료","bzmnRegNo":"","reOpenPbancYN":"",
        "currentPage":page,"recordCountPerPage":"999"}}

def parse_response(status,raw):
    try:body=json.loads(raw)
    except ValueError:raise RuntimeError("detail_not_json")
    if not isinstance(body,dict):raise RuntimeError("detail_bad_schema")
    message=str(body.get("ErrorMsg") or "")
    if status==422 and "개찰결과 데이터가 존재하지 않습니다" in message:
        return None,"no_data"
    if status!=200 or body.get("ErrorCode") not in (None,0,"0"):
        raise RuntimeError("detail_http_"+str(status)+":"+message[:90])
    r=body.get("result")
    if not isinstance(r,dict) or not isinstance(r.get("successBidInfo"),list):
        raise RuntimeError("detail_missing_bidder_list")
    if not all(isinstance(x,dict) for x in r["successBidInfo"]):
        raise RuntimeError("detail_bidders_bad_rows")
    return r["successBidInfo"],"ok"

async def bounded(awaitable,secs):
    task=asyncio.ensure_future(awaitable)
    task.add_done_callback(lambda t:None if t.cancelled() else t.exception())
    done,_=await asyncio.wait({task},timeout=secs)
    if not done:
        task.cancel()
        raise asyncio.TimeoutError("operation exceeded "+str(secs)+"s")
    return task.result()

async def get_page(ctx,gate,entry,page):
    # Back off on transient transport/HTTP failures; never overwrite a valid raw page.
    last=None
    for attempt in range(4):
        try:
            async with gate:
                resp=await bounded(ctx.request.post(
                    URL,data=json.dumps(payload(entry,page),ensure_ascii=False),
                    headers={"Content-Type":"application/json","Menu-Info":MENU,
                             "Referer":HOME,"User-Agent":"Mozilla/5.0"},
                    timeout=30000),38)
                body=await bounded(resp.body(),12)
                await asyncio.sleep(.25)
            if resp.status in (429,500,502,503,504):
                raise RuntimeError("transient_http_"+str(resp.status))
            records,state=parse_response(resp.status,body)
            return records,state,body
        except Exception as exc:
            last=exc
            if attempt==3:
                break
            log("DETAIL_PAGE_RETRY",{"bid_no":entry.get("bid_no"),"page":page,
                                     "attempt":attempt+1,"error":str(exc)[:150]})
            await asyncio.sleep(min(2**attempt,8))
    raise last

def normalized(row,entry,page):
    a=key(entry)
    return {"bid_no":a[0],"bid_ord":a[1],
        "bid_clsfc_no":a[2],"bid_prgrs_ord":a[3],
        "bidder_name":str(row.get("grpNm") or ""),
        "business_no":str(row.get("bzmnRegNo") or ""),
        "rank":str(row.get("onbsRnkg") or ""),
        "bid_amount":str(row.get("bdngAmt") or ""),
        "bid_rate":str(row.get("bdrt") or ""),
        "qualified":str(row.get("bidUfnsRsnCd") or ""),
        "remarks":str(row.get("etc") or ""),
        "bid_time":str(row.get("slprRcptnDt") or ""),
        "evidence_page":page}

def cached_complete(directory,previous):
    """Skip prior results only after checking actual retained raw evidence and CSV."""
    state=previous.get("status")
    if state not in ("verified_complete","no_opening_data"):return False
    pages=previous.get("pages") or []
    if not pages:return False
    for p in pages:
        try:
            n=int(p["page"])
            raw=gzip.decompress((directory/("raw_%05d.json.gz"%n)).read_bytes())
            if hashlib.sha256(raw).hexdigest()!=p["sha256_uncompressed"]:return False
        except (OSError,KeyError,ValueError,EOFError):
            return False
    if state=="no_opening_data":
        return len(pages)==1 and int(previous.get("bidder_count",-1))==0
    bidder_file=directory/"bidders.csv"
    if not bidder_file.is_file():return False
    try:
        with bidder_file.open("r",encoding="utf-8-sig",newline="") as f:
            actual=sum(1 for _ in csv.DictReader(f))
        return actual>0 and actual==int(previous.get("bidder_count",-1))
    except (OSError,ValueError,UnicodeError):return False

async def inspect_bid(ctx,gate,out,entry,args):
    try:
        directory=folder_for(out,entry)
    except ValueError as exc:
        raw=json.dumps(entry,sort_keys=True,ensure_ascii=False).encode("utf-8")
        directory=out/"invalid_queue_rows"/hashlib.sha256(raw).hexdigest()[:24]
        json_out(directory/"original_queue_row.json",entry)
        report={"bid_no":entry.get("bid_no"),"bid_ord":entry.get("bid_ord"),
                "status":"error","error":"invalid_queue_row:"+str(exc),
                "bidder_count":0,"pages":[]}
        json_out(directory/"status.json",report)
        log("BID_DETAIL_RESULT",report)
        return report
    st=directory/"status.json"
    if st.exists():
        try:
            previous=json.loads(st.read_text(encoding="utf-8"))
            if cached_complete(directory,previous):
                log("BID_SKIP_EXISTING",{"no":entry["bid_no"],"status":previous["status"]})
                return previous
        except (ValueError,TypeError,UnicodeError):
            pass
    pages=[]
    records=[]
    page_signatures=set()
    try:
        for n in range(1,args.max_pages+1):
            file=directory/("raw_%05d.json.gz"%n)
            if file.exists():
                try:
                    raw=gzip.decompress(file.read_bytes())
                    try:
                        rows,state=parse_response(200,raw)
                    except RuntimeError:
                        rows,state=parse_response(422,raw)
                except (OSError,EOFError,RuntimeError,ValueError):
                    quarantine=directory/"quarantine"/file.name
                    quarantine.parent.mkdir(parents=True,exist_ok=True)
                    if not quarantine.exists():shutil.move(str(file),str(quarantine))
                    rows,state,raw=await get_page(ctx,gate,entry,n)
                    atomic(file,gzip.compress(raw,compresslevel=6,mtime=0))
            else:
                rows,state,raw=await get_page(ctx,gate,entry,n)
                atomic(file,gzip.compress(raw,compresslevel=6,mtime=0))
            sha=hashlib.sha256(raw).hexdigest()
            pages.append({"page":n,"count":len(rows) if rows is not None else 0,
                          "sha256_uncompressed":sha})
            if state=="no_data":
                if n!=1:raise RuntimeError("detail_next_page_missing")
                status="no_opening_data"
                break
            # Exact repeats across different pages indicate broken pagination, not more bids.
            current_signatures={hashlib.sha256(
                json.dumps(row,sort_keys=True,ensure_ascii=False).encode("utf-8")
            ).hexdigest() for row in rows}
            if page_signatures.intersection(current_signatures):
                raise RuntimeError("duplicate_bidder_rows_across_pages")
            page_signatures.update(current_signatures)
            records.extend(normalized(row,entry,n) for row in rows)
            # Public G2B returns total count and next page flag per row.
            expected=0
            try:expected=int(rows[0].get("totCnt") or len(records)) if rows else len(records)
            except Exception:expected=len(records)
            has_more=bool(rows and str(rows[-1].get("nextRowYn") or "N").upper()=="Y")
            if not has_more:
                if expected!=len(records):
                    raise RuntimeError("detail_total_mismatch:"+str(expected)+"/"+str(len(records)))
                status="verified_complete"
                break
        else:
            status="partial_page_limit"
        if status=="verified_complete":
            if not records:status="no_bidder_rows_unverified"
            else:csv_out(directory/"bidders.csv",records)
        report={"bid_no":entry["bid_no"],"bid_ord":entry["bid_ord"],
                "status":status,"bidder_count":len(records),
                "pages":pages,"source":"G2B_public_WebSquare_detail",
                "updated_at":datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        report={"bid_no":entry["bid_no"],"bid_ord":entry["bid_ord"],
                "status":"error","error":type(e).__name__+":"+str(e)[:220],
                "bidder_count":len(records),"pages":pages}
    json_out(st,report)
    log("BID_DETAIL_RESULT",{k:report.get(k) for k in ("bid_no","status","bidder_count","error")})
    return report

def load_queue(path,start,limit):
    if not path.exists():raise FileNotFoundError(str(path))
    seen=set(); rows=[]
    with path.open("r",encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f):
            if not PATTERN.fullmatch(str(row.get("bid_no") or "")):continue
            idx=tuple(key(row))
            if idx in seen:continue
            seen.add(idx)
            rows.append(row)
    selected=rows[start:start+limit if limit else None]
    log("DETAIL_QUEUE",{"total_unique":len(rows),"selected":len(selected),
                        "start_index":start,"requested_limit":limit})
    return selected,len(rows)

async def main(args):
    items,all_items=load_queue(Path(args.input),args.start_index,args.limit)
    if args.dry_run:return 0
    out=Path(args.output)
    out.mkdir(parents=True,exist_ok=True)
    queue=asyncio.Queue()
    for item in items:queue.put_nowait(item)
    gate=asyncio.Semaphore(min(args.tabs,5))
    reports=[]
    interrupted=None
    async with async_playwright() as p:
        browser=await bounded(p.chromium.launch(channel="chrome",headless=False),45)
        ctx=await bounded(browser.new_context(locale="ko-KR",timezone_id="Asia/Seoul"),25)
        home=await ctx.new_page()
        response=await bounded(home.goto(HOME,wait_until="domcontentloaded",timeout=35000),40)
        if not response or response.status>=400:raise RuntimeError("G2B Chrome homepage unavailable")
        async def worker(worker_no):
            tab=await ctx.new_page()
            try:
                while True:
                    try:entry=queue.get_nowait()
                    except asyncio.QueueEmpty:break
                    try:
                        report=await inspect_bid(ctx,gate,out,entry,args)
                    except Exception as exc:
                        # A malformed record must never terminate other workers.
                        report={"bid_no":entry.get("bid_no"),"bid_ord":entry.get("bid_ord"),
                                "status":"error","error":"worker_exception:"+str(exc)[:180],
                                "bidder_count":0,"pages":[]}
                        quarantine=out/"worker_errors"/hashlib.sha256(
                            json.dumps(entry,sort_keys=True,ensure_ascii=False).encode("utf-8")
                        ).hexdigest()[:24]
                        json_out(quarantine/"original_queue_row.json",entry)
                        json_out(quarantine/"status.json",report)
                        log("BID_DETAIL_RESULT",report)
                    finally:
                        queue.task_done()
                    reports.append(report)
            finally:
                try:await bounded(tab.close(),5)
                except Exception:pass
        try:
            await bounded(asyncio.gather(*(worker(i) for i in range(min(args.tabs,len(items))))),args.timeout)
        except Exception as exc:
            interrupted=type(exc).__name__+":"+str(exc)[:220]
            log("DETAIL_RUN_INTERRUPTED",{"error":interrupted,"processed":len(reports)})
        finally:
            await ctx.close()
            await browser.close()
    counts={state:sum(x.get("status")==state for x in reports)
        for state in ("verified_complete","no_opening_data","no_bidder_rows_unverified",
                      "partial_page_limit","error")}
    summary={"total_notice_queue":all_items,"selected":len(items),
        "processed":len(reports),"detail_status_counts":counts,
        "verified_bidder_rows":sum(x.get("bidder_count",0) for x in reports
                if x.get("status")=="verified_complete"),
        "two_year_all_details_complete":False,
        "interrupted":interrupted,
        "note":"no_opening_data != no bidders; contracts/awards separately required."}
    json_out(out/"detail_summary.json",summary)
    log("DETAIL_FINAL",summary)
    return 0 if not interrupted and len(reports)==len(items) and not any(
        x.get("status") in ("error","partial_page_limit","no_bidder_rows_unverified")
        for x in reports) else 3

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--input",default="g2b-index-stage1/notice_queue.csv")
    p.add_argument("--output",default="g2b-detail-stage2")
    p.add_argument("--start-index",type=int,default=0)
    p.add_argument("--limit",type=int,default=25,help="0 means whole queue")
    p.add_argument("--tabs",type=int,default=5)
    p.add_argument("--max-pages",type=int,default=20)
    p.add_argument("--timeout",type=int,default=3600)
    p.add_argument("--dry-run",action="store_true")
    a=p.parse_args()
    if not (0<=a.start_index and a.limit>=0 and 1<=a.tabs<=10 and
            1<=a.max_pages<=100 and 60<=a.timeout<=10200):p.error("Invalid bounds")
    sys.exit(asyncio.run(main(a)))
