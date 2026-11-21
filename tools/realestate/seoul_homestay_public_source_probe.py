#!/usr/bin/env python3
"""Collect public foreign-tourist urban-homestay licensing CSV including areas and public business telephones.
Standalone public-source probe, no credentials. Output in artifacts/seoul-homestay.
"""
import csv,io,json,os,urllib.request,urllib.error,zipfile,datetime,pathlib,time
OUT=pathlib.Path("artifacts/seoul-homestay");OUT.mkdir(parents=True,exist_ok=True)
HEAD={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0","Referer":"https://file.localdata.go.kr/file/general_restaurants/info"}
sources=[
 ("localdata_national","https://www.localdata.go.kr/datafile/each/03_11_04_P_CSV.zip"),
 ("localdata_mirror","https://file.localdata.go.kr/file/download/foreigner_city_homestays/info?orgCode=3130000"),
 ("localdata_mirror_jongno","https://file.localdata.go.kr/file/download/foreigner_city_homestays/info?orgCode=3000000"),
]
log=[];rows=[];winner=None;headers=[]
def dec(b):
 for enc in ("utf-8-sig","cp949","euc-kr","utf-8"):
  try:return b.decode(enc)
  except UnicodeError:continue
 return b.decode("cp949",errors="replace")
for source,url in sources:
 try:
  req=urllib.request.Request(url,headers=HEAD)
  with urllib.request.urlopen(req,timeout=70) as resp:
   content=resp.read(35*1024*1024+1);meta={"source":source,"url":url,"status":resp.status,"type":resp.headers.get("Content-Type"),"bytes":len(content)}
  if len(content)>35*1024*1024:raise ValueError("too_large")
  candidates=[]
  if content[:2]==b"PK":
   with zipfile.ZipFile(io.BytesIO(content)) as z:
    for file in z.namelist():
     if file.lower().endswith((".csv",".txt")):
      candidates.append((file,z.read(file)))
  else:candidates=[("response.csv",content)]
  for filename,content in candidates:
   text=dec(content)
   rd=csv.DictReader(io.StringIO(text))
   arr=list(rd)
   if not arr:continue
   columns=rd.fieldnames or []
   if not any("사업장명" in c or "BPLCNM" in c for c in columns):continue
   seo=[r for r in arr if any("서울특별시" in (v or "") for k,v in r.items() if "주소" in k or k.upper() in ("SITEWHLADDR","RDNWHLADDR")) or (r.get("개방자치단체코드","")[:2]=="31")]
   meta.update({"file":filename,"total_records":len(arr),"seoul_records":len(seo),"columns":columns})
   if len(seo)>len(rows):rows=seo;headers=columns;winner=source
   break
  log.append(meta)
 except Exception as e:log.append({"source":source,"url":url,"error":type(e).__name__+": "+str(e)})
if rows:
 with open(OUT/"seoul_original_enriched.csv","w",encoding="utf-8-sig",newline="") as f:
  w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows(rows)
met={"generated_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"best_source":winner,"best_count":len(rows),"attempts":log}
(OUT/"source_manifest.json").write_text(json.dumps(met,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(met,ensure_ascii=False,indent=2))
