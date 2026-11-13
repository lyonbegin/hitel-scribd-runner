#!/usr/bin/env python3
"""Merge ALL independently completed 2024-11-13..2026-11-13 notice-index shards.

This checks 731 daily status records and last short page. Partial data remains
useful but NEVER receives a 2-year-complete flag. Streams through SQLite to
avoid keeping 1M+ notice rows in memory. Does not call G2B or bidder details.
"""
from __future__ import annotations
import argparse,csv,json,os,sqlite3,sys
from datetime import date,timedelta,datetime,timezone
from pathlib import Path

FROM=date(2024,11,13)
TO=date(2026,11,13)
FIELDS=("bid_no","bid_ord","bid_clsfc_no","bid_prgrs_ord","notice_title",
        "published","category","agency","status","source_day","evidence_page",
        "id_format","source_shard")
KEY=("bid_no","bid_ord","bid_clsfc_no","bid_prgrs_ord")

def atomic_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".new")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True),encoding="utf-8")
    os.replace(tmp,path)

def main(args):
    out=Path(args.output)
    out.mkdir(parents=True,exist_ok=True)
    temp=out/"merge_temp.sqlite"
    if temp.exists():temp.unlink()
    db=sqlite3.connect(temp)
    db.execute("PRAGMA journal_mode=OFF")
    db.execute("PRAGMA synchronous=OFF")
    db.execute("""CREATE TABLE queue(
        bid_no text not null,bid_ord text not null,
        bid_clsfc_no text not null,bid_prgrs_ord text not null,
        notice_title text,published text,category text,agency text,
        status text,source_day text,evidence_page text,
        id_format text,source_shard text,
        primary key (bid_no,bid_ord,bid_clsfc_no,bid_prgrs_ord)
    ) WITHOUT ROWID""")
    dates={}
    total_rows=0
    errors=[]
    try:
        artifacts=sorted(Path(args.input).glob("g2b-two-year-index-shard-*"))
        if not artifacts:raise RuntimeError("No shard artifacts were restored")
        for shard in artifacts:
            days=shard/"days"
            if not days.exists():
                errors.append(f"{shard.name}: no days folder")
                continue
            for state_file in sorted(days.glob("*/status.json")):
                day_folder=state_file.parent
                try:
                    state=json.loads(state_file.read_text(encoding="utf-8"))
                    day=date.fromisoformat(state["day"])
                    if day<FROM or day>TO:
                        raise ValueError("out of horizon "+str(day))
                    previous=dates.get(day.isoformat())
                    if previous is not None:raise ValueError("date in more than one shard")
                    evidence=state.get("evidence") or []
                    last_count=int(evidence[-1]["rows"]) if evidence else -1
                    completed=(state.get("status")=="complete" and last_count<100
                               and (day_folder/"index.csv").is_file())
                    if not completed:
                        dates[day.isoformat()]={"status":"unverified_or_partial",
                            "shard":shard.name,"raw_status":state.get("status"),
                            "last_page_count":last_count}
                        continue
                    with (day_folder/"index.csv").open("r",newline="",encoding="utf-8-sig") as f:
                        daily_rows=0
                        for row in csv.DictReader(f):
                            normalized={k:row.get(k,"") for k in FIELDS}
                            normalized["source_shard"]=shard.name
                            normalized["evidence_page"]=shard.name+"/"+row.get("evidence_page","")
                            if not normalized["bid_no"]:
                                raise ValueError("blank bid ID on "+str(day))
                            db.execute("INSERT OR IGNORE INTO queue VALUES ("+",".join("?" for _ in FIELDS)+")",
                                       [normalized[k] for k in FIELDS])
                            daily_rows+=1
                        if daily_rows!=int(state["rows"]):
                            raise ValueError("day CSV total mismatch "+str(day))
                    total_rows+=daily_rows
                    dates[day.isoformat()]={"status":"complete","shard":shard.name,
                                           "notice_rows":daily_rows,"pages":state.get("pages"),
                                           "last_page_count":last_count}
                    db.commit()
                except Exception as e:
                    errors.append(str(day_folder)+":"+type(e).__name__+":"+str(e)[:160])
        missing=[]
        day=FROM
        while day<=TO:
            if day.isoformat() not in dates:
                missing.append(day.isoformat())
            day+=timedelta(days=1)
        complete=(not missing and not errors and
                  len(dates)==731 and all(v["status"]=="complete" for v in dates.values()))
        fields=list(FIELDS)
        with (out/"notice_queue.csv").open("w",newline="",encoding="utf-8-sig") as f:
            w=csv.writer(f)
            w.writerow(fields)
            count=0;eligible=0
            for vals in db.execute("SELECT "+",".join(FIELDS)+" FROM queue"):
                w.writerow(vals)
                count+=1
                eligible+=int(vals[fields.index("id_format")]=="bid_detail_supported")
        summary={"period":[FROM.isoformat(),TO.isoformat()],
                 "required_days":731,
                 "days_found":len(dates),
                 "days_complete":sum(v["status"]=="complete" for v in dates.values()),
                 "days_missing":len(missing),"missing_dates":missing,
                 "errors":errors[:100],
                 "source_rows_before_dedup":total_rows,
                 "unique_bid_execution_keys":count,
                 "detail_eligible_keys":eligible,
                 "other_id_format_keys":count-eligible,
                 "two_year_index_complete":complete,
                 "detail_collection_completed":False,
                 "source":"G2B_main_PNPE001_01",
                 "at":datetime.now(timezone.utc).isoformat()}
        atomic_json(out/"coverage.json",summary)
        print("TWO_YEAR_INDEX_COVERAGE",json.dumps({
            k:v for k,v in summary.items() if k not in ("missing_dates","errors")},
            ensure_ascii=False),flush=True)
        if not complete:
            print("TWO_YEAR_INDEX_UNVERIFIED",
                  json.dumps({"missing_dates":missing[:12],"errors":errors[:12]},
                  ensure_ascii=False),flush=True)
        return 0 if complete else 3
    finally:
        db.close()
        if temp.exists():temp.unlink()

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--input",default="g2b-shards")
    p.add_argument("--output",default="g2b-index-2year-merged")
    a=p.parse_args()
    sys.exit(main(a))
