#!/usr/bin/env python3
"""ProcureFlow 2-year public G2B raw-evidence pilot on HITEL's Windows Chrome runner.

Read-only. Separates listing/award evidence from unimplemented notice/contract
sources. A successful request is not a claim of full national coverage.
No credentials, bidding, login, CAPTCHA handling, or access-control bypass.
"""
from __future__ import annotations
import argparse
import asyncio
from collections import Counter
from datetime import date, timedelta, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse

FROM = date(2024, 11, 13)
TO = date(2026, 11, 13)
G2B = "https://www.g2b.go.kr/"
NURI = "https://nuri.g2b.go.kr/"
OPEN_LIST = G2B+"pb/pbo/pboc/OnbsRslt/selectOnbsRsltClsfList.do"
OPEN_DETAIL = G2B+"pb/pbo/pboc/OnbsRslt/selectOnbsRsltSbidGods.do"
AWARD_LIST = NURI+"nn/nnb/nnba/selectBidPbancList.do"
AWARD_DETAIL = NURI+"nn/nnb/nnbd/selectOobsRsltDetl.do"
OPEN_MENU = '{"menuNo":"01522","menuCangVal":"PBOC006_01","bsneClsfCd":"%EC%97%85130028","scrnNo":"02117"}'
DETAIL_MENU = '{"menuNo":"15620","scrnNo":"08542"}'
AWARD_MENU = '{"menuNo":"15401","menuCangVal":"NNBA001_01","bsneClsfCd":"%EC%97%85130031","scrnNo":"00777"}'
ID = re.compile(r"^(R\d{2}BK\d{8}|\d{11})$")
STREAMS = ("opening", "award")
# The sources below MUST be added and independently verified before 'full'
# coverage can be claimed. See README.
UNIMPLEMENTED = ("notices_and_revisions", "contracts_including_sole_source",
                 "contract_changes_deletions", "attachments", "supplier_registry")


def windows():
    current = FROM
    while current <= TO:
        last = min(current + timedelta(days=6), TO)
        yield current, last
        current = last + timedelta(days=1)


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+".new")
    temp.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    os.replace(temp, path)


def atomic_bytes(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+".new")
    tmp.write_bytes(raw)
    os.replace(tmp, path)
    return hashlib.sha256(raw).hexdigest()


def checkpoint_path(out, stream, first, last):
    return out/"checkpoints"/stream/(first.isoformat()+"_"+last.isoformat()+".json")


def tasks_for(args):
    all_windows=list(windows())
    if args.mode=="smoke":
        ranges=[(FROM, FROM), (TO, TO)]
    else:
        ranges=all_windows[args.window_offset:]
        if args.max_windows:
            ranges=ranges[:args.max_windows]
    return [(stream, first, last) for first,last in ranges for stream in STREAMS]


def plan(args):
    tasks=tasks_for(args)
    print("PLAN", json.dumps({
        "full_horizon":[FROM.isoformat(), TO.isoformat()],
        "seven_day_windows":len(list(windows())),
        "streams_implemented":list(STREAMS),
        "sources_not_yet_implemented":list(UNIMPLEMENTED),
        "tasks_in_this_run":len(tasks),
        "mode":args.mode,
        "date_ranges_in_this_run":sorted(set((a.isoformat(),b.isoformat()) for _,a,b in tasks)),
        "warning":"No results are called complete until source pagination and raw evidence are verified.",
    }, ensure_ascii=False), flush=True)
    return tasks


async def bounded(awaitable, seconds):
    # Copied from successful HITEL ten-tabs engine: bounded task with cancel.
    task=asyncio.create_task(awaitable)
    task.add_done_callback(lambda t: None if t.cancelled() else t.exception())
    done,_=await asyncio.wait({task}, timeout=seconds)
    if not done:
        task.cancel()
        raise asyncio.TimeoutError("Operation exceeded %ss" % seconds)
    return task.result()


async def request_json(ctx, url, payload, headers, gate):
    # Public read-only WebSquare requests as observed in ProcureFlow sources.
    assert urlparse(url).hostname in ("www.g2b.go.kr","nuri.g2b.go.kr")
    async with gate:
        res=await bounded(ctx.request.post(
            url, data=json.dumps(payload, ensure_ascii=False),
            headers=headers, timeout=30000), 38)
        raw=await bounded(res.body(), 12)
        await asyncio.sleep(0.3)
    if res.status!=200:
        raise RuntimeError("source_http_%s:%s" % (res.status,raw[:100].decode("utf-8","replace")))
    try:
        data=json.loads(raw)
    except ValueError as e:
        raise RuntimeError("non_json_source_response") from e
    if not isinstance(data,dict) or not isinstance(data.get("result"),(dict,list)):
        raise RuntimeError("unexpected_source_schema")
    if data.get("ErrorCode") not in (None,0,"0"):
        raise RuntimeError("source_error_"+str(data.get("ErrorCode")))
    return data,raw


def opening_payload(first,last,page):
    index=(page-1)*10+1
    return {"dlSrchOnbsRsltClsfListInM":{
        "bidPbancNo":"","bidPbancOrd":"","bidPbancNm":"",
        "onbsYmdStr":first.strftime("%Y%m%d"),
        "onbsYmdEnd":last.strftime("%Y%m%d"),
        "prcmBsneSeCd":"0000 조070001 조070002 조070003 조070004 조070005",
        "frcpYn":"Y","rsrvYn":"Y","laseYn":"Y","chkBsneAllYn":"Y",
        "lastIndex":index+9,"firstIndex":index,
        "inqEnd":"","stepBarYn":"","pbancKndCd":"공440002"
    }}


def award_payload(first,last,page):
    # Search by actual opening date; publication start widened for revisions.
    prior=first-timedelta(days=30)
    return {"dlParamM":{
        "bidPbancNo":"","bidPbancOrd":"","bidPbancNm":"",
        "prcmBsneSeCd":"","bidPbancPgstCd":"입160010","bidMthdCd":"",
        "pbancPstgStDt":prior.strftime("%Y%m%d"),
        "pbancPstgEdDt":last.strftime("%Y%m%d"),
        "onbsPrnmntStDt":first.strftime("%Y%m%d"),
        "onbsPrnmntEdDt":last.strftime("%Y%m%d"),
        "recordCountPerPage":"20","rowNum":"","kbrdrId":"",
        "pbancInstUntyGrpNo":"","pdngYn":"","currentPage":page,
        "pbancSttsCd":"","pbancKndCd":"","stdCtrtMthdCd":"",
        "scsbdMthdCd":"","untyGrpNo":"","usrTyCd":"",
        "pbancPstgYn":"Y","frgnrRprsvYn":""
    }}


def list_items(stream, body):
    payload=body["result"]
    if stream=="opening":
        if not isinstance(payload,dict) or not isinstance(payload.get("onbsRsltClsfList"),list):
            raise RuntimeError("opening_items_missing")
        return payload["onbsRsltClsfList"],10
    if isinstance(payload,list):
        return payload,20
    candidates=[v for v in payload.values() if isinstance(v,list) and
                (not v or isinstance(v[0],dict))]
    if not candidates:
        raise RuntimeError("award_list_field_not_found")
    return max(candidates,key=len),20


async def detail(ctx, gate, stream, row):
    no=str(row.get("bidPbancNo") or "")
    if not ID.fullmatch(no):
        return None,"unverified_bid_id"
    order=str(row.get("bidPbancOrd") or "000")
    classification=str(row.get("bidClsfNo") or "0")
    progress=str(row.get("bidPrgrsOrd") or "000")
    if stream=="opening":
        payload={"dlSrchOnbsRsltBidInM":{
            "bidPbancNo":no,"bidPbancOrd":order,
            "bidClsfNo":classification,"bidPrgrsOrd":progress,
            "prcmBsneSeCd":str(row.get("prcmBsneSeCd") or ""),
            "bidPgstCd":str(row.get("bidPgstCd") or "개찰완료"),
            "bzmnRegNo":"","reOpenPbancYN":"","currentPage":1,
            "recordCountPerPage":"999"}}
        headers={"Content-Type":"application/json","Menu-Info":DETAIL_MENU,
                 "User-Agent":"Mozilla/5.0","Referer":G2B}
        url=OPEN_DETAIL
    else:
        payload={"dlSrchCndtM":{
            "bidPbancNo":no,"bidPbancOrd":order,
            "bidClsfNo":classification,"bidPrgrsOrd":progress,
            "bidPbancPgstCd":str(row.get("bidPbancPgstCd") or ""),
            "kbrdrId":"","etpsUntyGrpNo":"","prcrId":"",
            "prcsRsn":"","cvlnOrbySeCd":"","cvlnEtpsSrngPgstCd":"",
            "myBdonLisMovYn":""}}
        headers={"Accept":"application/json","Content-Type":"application/json;charset=UTF-8",
                 "Target-Id":"btnOnbsRslt","Usr-Id":"null","Origin":NURI,"Referer":NURI}
        url=AWARD_DETAIL
    try:
        data,raw=await request_json(ctx,url,payload,headers,gate)
        return (no+"_"+order+"_"+classification+"_"+progress,raw),"ok"
    except Exception as e:
        return None,type(e).__name__+":"+str(e)[:100]


async def process_window(ctx, gate, out, stream, first,last,args):
    location=checkpoint_path(out,stream,first,last)
    if location.exists():
        previous=json.loads(location.read_text(encoding="utf-8"))
        if previous.get("status")=="complete":
            print("WINDOW_SKIP_COMPLETE",stream,first,last,flush=True)
            return previous
    meta={"stream":stream,"from":first.isoformat(),"to":last.isoformat(),
          "status":"started","pages":[],"raw_list_count":0,"detail_ok":0,
          "detail_error":0,"detail_sample_count":0,"errors":[],
          "source_url":OPEN_LIST if stream=="opening" else AWARD_LIST,
          "updated_at":datetime.now(timezone.utc).isoformat()}
    headers=({"Accept":"application/json","Content-Type":"application/json;charset=UTF-8",
              "Menu-Info":OPEN_MENU,"submissionid":"mf_wfm_container_selectOnbsRsltClsfList",
              "Usr-Id":"null","Referer":G2B} if stream=="opening" else
             {"Accept":"application/json","Content-Type":"application/json;charset=UTF-8",
              "Menu-Info":AWARD_MENU,"Target-Id":"btnS0001",
              "Usr-Id":"null","Origin":NURI,"Referer":NURI})
    try:
        for page in range(1,args.max_pages+1):
            payload=(opening_payload(first,last,page) if stream=="opening"
                     else award_payload(first,last,page))
            data,raw=await request_json(ctx,meta["source_url"],payload,headers,gate)
            items,page_size=list_items(stream,data)
            dest=out/"raw"/stream/(first.isoformat()+"_"+last.isoformat())/("list_%05d.json"%page)
            digest=atomic_bytes(dest,raw)
            meta["pages"].append({"page":page,"count":len(items),"sha256":digest,"file":str(dest),
                                  "response_bytes":len(raw)})
            meta["raw_list_count"]+=len(items)
            if not all(isinstance(v,dict) for v in items):
                raise RuntimeError("list_contains_non_object")
            if args.details_per_window!=0:
                limit=max(0,args.details_per_window-meta["detail_sample_count"])
            else:
                limit=len(items)
            for item in items[:limit]:
                record,state=await detail(ctx,gate,stream,item)
                meta["detail_sample_count"]+=1
                if record:
                    key,body=record
                    p=out/"raw"/stream/(first.isoformat()+"_"+last.isoformat())/"details"/(key+".json")
                    atomic_bytes(p,body)
                    meta["detail_ok"]+=1
                else:
                    meta["detail_error"]+=1
                    meta["errors"].append(state)
            atomic_json(location,meta)
            print("WINDOW_PAGE",json.dumps({"stream":stream,"from":str(first),
                  "to":str(last),"page":page,"records":len(items),"detail_ok":meta["detail_ok"],
                  "sha256":digest},ensure_ascii=False),flush=True)
            if len(items)<page_size:
                meta["status"]="list_pages_complete"
                break
        if meta["status"]=="started":
            meta["status"]="partial_page_limit"
        if meta["status"]=="list_pages_complete" and meta["detail_error"]==0 and args.details_per_window==0:
            meta["status"]="complete"
        elif meta["status"]=="list_pages_complete":
            meta["status"]="partial_details"
    except Exception as e:
        meta["status"]="error"
        meta["errors"].append(type(e).__name__+":"+str(e)[:170])
    meta["updated_at"]=datetime.now(timezone.utc).isoformat()
    atomic_json(location,meta)
    print("WINDOW_RESULT",json.dumps({"stream":stream,"from":str(first),
          "to":str(last),"status":meta["status"],"list_rows":meta["raw_list_count"],
          "pages":len(meta["pages"]),"details":meta["detail_ok"],
          "errors":meta["errors"][:3]},ensure_ascii=False),flush=True)
    return meta


async def run(args):
    tasks=plan(args)
    if args.mode=="plan":
        return 0
    from playwright.async_api import async_playwright
    out=Path(args.output)
    out.mkdir(parents=True,exist_ok=True)
    results=[]
    queue=asyncio.Queue()
    for item in tasks:
        queue.put_nowait(item)
    gate=asyncio.Semaphore(3)  # 10 browser tabs, but only 3 concurrent requests to public G2B.
    async with async_playwright() as pw:
        browser=await bounded(pw.chromium.launch(channel="chrome",headless=False),45)
        context=await bounded(browser.new_context(locale="ko-KR",timezone_id="Asia/Seoul"),25)
        async def worker(num):
            page=await bounded(context.new_page(),20)
            try:
                while True:
                    try:
                        stream,first,last=queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    try:
                        base=G2B if stream=="opening" else NURI
                        response=await bounded(page.goto(base,wait_until="domcontentloaded",
                                                         timeout=30000),38)
                        if response is None or response.status>=400:
                            raise RuntimeError("official_browser_home_unavailable")
                        results.append(await process_window(context,gate,out,stream,first,last,args))
                    except Exception as e:
                        meta={"stream":stream,"from":str(first),"to":str(last),
                              "status":"error","errors":[type(e).__name__+":"+str(e)[:160]],
                              "pages":[],"raw_list_count":0}
                        atomic_json(checkpoint_path(out,stream,first,last),meta)
                        results.append(meta)
                    finally:
                        queue.task_done()
            finally:
                try:
                    await bounded(page.close(run_before_unload=False),5)
                except Exception:
                    pass
        workers=[asyncio.create_task(worker(i)) for i in range(args.tabs)]
        try:
            await bounded(asyncio.gather(*workers), args.run_timeout)
        except Exception as e:
            print("RUN_FAILURE",type(e).__name__+":"+str(e),flush=True)
        finally:
            try: await bounded(context.close(),12)
            except Exception:pass
            try: await bounded(browser.close(),12)
            except Exception:pass
    counts=Counter(r.get("status") for r in results)
    report={
        "period":[FROM.isoformat(),TO.isoformat()],
        "run_mode":args.mode,"task_count":len(tasks),
        "tasks_visited":len(results),"status_counts":dict(counts),
        "pages_captured":sum(len(r.get("pages",[])) for r in results),
        "listing_rows_observed":sum(r.get("raw_list_count",0) for r in results),
        "source_coverage":{x:"not_implemented_not_zero" for x in UNIMPLEMENTED},
        "complete_national_two_year_data":False,
        "warning":"Raw listing pages or selected details do not establish full notice, bid, contract or sole-source coverage.",
        "generated_at":datetime.now(timezone.utc).isoformat()
    }
    atomic_json(out/"summary.json",report)
    print("FINAL_COLLECTION_STATUS",json.dumps(report,ensure_ascii=False),flush=True)
    return 2 if counts.get("error") or len(results)!=len(tasks) else 0


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=("plan","smoke","batch","full"),default="plan")
    p.add_argument("--window-offset",type=int,default=0)
    p.add_argument("--max-windows",type=int,default=2)
    p.add_argument("--max-pages",type=int,default=2)
    p.add_argument("--details-per-window",type=int,default=2,
                   help="0=all details, positive=pilot sample")
    p.add_argument("--tabs",type=int,default=10)
    p.add_argument("--run-timeout",type=int,default=3000)
    p.add_argument("--output",default="procureflow-2y-evidence")
    a=p.parse_args()
    if not (1<=a.tabs<=10 and 1<=a.max_pages<=1000 and a.max_windows>=0 and
            a.window_offset>=0 and a.details_per_window>=0 and a.run_timeout>=60):
        p.error("Invalid bounded-run settings")
    if a.mode=="full":
        a.max_windows=0
    raise SystemExit(asyncio.run(run(a)))


if __name__=="__main__":
    main()
