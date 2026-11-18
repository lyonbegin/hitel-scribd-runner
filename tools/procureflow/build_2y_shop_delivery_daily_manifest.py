#!/usr/bin/env python3
"""Build exact daily *scope* for all shop delivery orders; NOT a collected dataset.

Source: official UI-ADOXAA-038R report uses approval date and D-1 freshness.
No false complete/zero counts. Separate raw delivery history from catalog goods.
"""
import argparse,datetime as dt,json,os
from pathlib import Path
from zoneinfo import ZoneInfo
SOURCE_ID="UI-ADOXAA-038R"
REPORT_NO="00118"
SOURCE_URL="https://data.g2b.go.kr/link/AISC001_01/?reptNm=UI-ADOXAA-038R"
SOURCE_VERSION="post-2021"
DATE_FIELD="결재일자"
START=dt.date(2024,11,18)
AS_OF=dt.date(2026,11,18)
def prepare(start=START,as_of=AS_OF):
 if as_of<start:raise ValueError("as_of before start")
 published_end=as_of-dt.timedelta(days=1)
 days=[start+dt.timedelta(days=n) for n in range((published_end-start).days+1)]
 data={"dataset":"procureflow_2y_shop_delivery_history","type":"date_scope_manifest_not_fetched",
  "source_site":"data.g2b.go.kr","source_report_id":SOURCE_ID,
  "source_report_number":REPORT_NO,"report_variant":SOURCE_VERSION,
  "source_url":SOURCE_URL,"date_column_korean":DATE_FIELD,
  "start_date":start.isoformat(),"requested_through":as_of.isoformat(),
  "eligible_through":published_end.isoformat(),
  "publication_lag":"D-1; today's original data must remain pending",
  "scope":{"all_items":True,"all_suppliers":True,"all_agencies":True,
          "keyword":None,"historical_transactions":True},
  "actual_deliveries_verified":0,"source_report_metadata_verified":True,
  "source_report_csv_verified":False,
  "rows_expected":None,"collected_unique_rows":0,
  "days": [{"date":d.isoformat(),"status":"not_collected",
     "raw_page_count":None,"source_rows":None,"raw_sha256":None} for d in days],
  "asof_pending":{"date":as_of.isoformat(),"status":"D-1_NOT_YET_AVAILABLE"}}
 assert all((dt.date.fromisoformat(b["date"])-dt.date.fromisoformat(a["date"])).days==1
    for a,b in zip(data["days"],data["days"][1:])), "daily partitions have gaps or overlap"
 assert len({x["date"] for x in data["days"]})==len(data["days"])
 assert data["actual_deliveries_verified"]==0
 return data

if __name__=="__main__":
 ap=argparse.ArgumentParser()
 ap.add_argument("--start",default=START.isoformat())
 ap.add_argument("--as-of",default=AS_OF.isoformat())
 ap.add_argument("--out",default=os.path.join(os.getenv("RUNNER_TEMP","."),"procureflow-shop-delivery-2y-manifest.json"))
 args=ap.parse_args()
 v=prepare(dt.date.fromisoformat(args.start),dt.date.fromisoformat(args.as_of))
 p=Path(args.out);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding="utf-8")
 print("PF2_SHOP_DELIVERY_DATE_SCOPE",json.dumps({
  "start":v["start_date"],"end":v["eligible_through"],
  "days":len(v["days"]),"missing_report_data_days":len(v["days"]),
  "actual_delivery_rows_verified":0,"keyword":None,
  "source_report_id":SOURCE_ID,"raw_csv_verified":False,
  "current_day_pending":v["asof_pending"]["date"]},ensure_ascii=False))
