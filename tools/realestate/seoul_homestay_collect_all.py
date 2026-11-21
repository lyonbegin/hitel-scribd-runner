#!/usr/bin/env python3
"""Acquire all 25 Seoul district original foreign-tourist homestay licensing CSV files.
No credentials or private endpoints. Exports verifiable original rows plus <=60m2 facility subset.
"""
import csv,io,json,urllib.request,urllib.error,zipfile,datetime,pathlib,concurrent.futures,time
CODES=list(range(3000000,3250000,10000))
URL="https://file.localdata.go.kr/file/download/foreigner_city_homestays/info?orgCode={}"
HEAD={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0","Referer":"https://file.localdata.go.kr/file/general_restaurants/info"}
OUT=pathlib.Path("artifacts/seoul-homestay");OUT.mkdir(parents=True,exist_ok=True)
def decode(content):
 for e in ("utf-8-sig","cp949","euc-kr","utf-8"):
  try:return content.decode(e)
  except UnicodeError:continue
 return content.decode("cp949",errors="replace")
def download(code):
 url=URL.format(code); last=""
 for attempt in range(2):
  try:
   req=urllib.request.Request(url,headers=HEAD)
   with urllib.request.urlopen(req,timeout=55) as resp:
    raw=resp.read(6*1024*1024)
    ct=resp.headers.get("Content-Type","")
    if "csv" not in ct.lower():raise RuntimeError("Unexpected content type: "+ct)
   text=decode(raw)
   reader=csv.DictReader(io.StringIO(text))
   data=list(reader)
   if not data or "관리번호" not in reader.fieldnames:raise RuntimeError("Missing header/rows")
   for r in data:r["_수집자치구코드"]=str(code)
   return {"code":code,"url":url,"records":len(data),"bytes":len(raw),"rows":data,"columns":reader.fieldnames}
  except Exception as ex:
   last=type(ex).__name__+": "+str(ex)
   if attempt==0:time.sleep(2)
 return {"code":code,"url":url,"error":last,"records":0,"rows":[]}
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
 answers=sorted(ex.map(download,CODES),key=lambda x:x["code"])
allrows=[];seen=set();dup=0;headers=None
for x in answers:
 for row in x["rows"]:
  key=(row.get("개방자치단체코드",""),row.get("관리번호",""))
  if key in seen:dup+=1;continue
  seen.add(key);allrows.append(row)
 if x.get("columns") and headers is None:headers=x["columns"]
headers=(headers or [])+["_수집자치구코드"]
def num(v):
 try:return float(str(v).strip().replace(",",""))
 except:return None
def is_active(r):return "영업" in r.get("영업상태명","") and "폐" not in r.get("영업상태명","")
candidates=[r for r in allrows if (a:=num(r.get("시설면적"))) is not None and 0<a<=60]
active60=[r for r in candidates if is_active(r)]
for name,items in [("seoul_original_all.csv",allrows),("seoul_facility_le60.csv",candidates),("seoul_active_facility_le60.csv",active60)]:
 with open(OUT/name,"w",encoding="utf-8-sig",newline="") as f:
  w=csv.DictWriter(f,fieldnames=headers,extrasaction="ignore");w.writeheader();w.writerows(items)
manifest={
 "collected_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "source":"LOCALDATA open CSV", "count":len(allrows),
 "fetched_districts":sum("error" not in x for x in answers),
 "failed_districts":[{"code":x["code"],"error":x.get("error")} for x in answers if "error" in x],
 "duplicates":dup,
 "nonempty_facility_area":sum(num(r.get("시설면적")) is not None for r in allrows),
 "facility_le60":len(candidates),
 "active_facility_le60":len(active60),
 "nonempty_public_business_phones":sum(bool((r.get("전화번호") or "").strip()) for r in allrows),
 "nonempty_closed_dates":sum(bool((r.get("폐업일자") or "").strip()) for r in allrows),
 "districts":[{k:v for k,v in x.items() if k!="rows" and k!="columns"} for x in answers],
 "notes":"시설면적 != 주택 전용면적. 영업/정상 != Airbnb current status. 사업자등록번호 not provided."
}
(OUT/"all_districts_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(manifest,ensure_ascii=False,indent=2))
