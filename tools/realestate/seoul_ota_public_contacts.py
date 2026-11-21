#!/usr/bin/env python3
"""Seoul <=60m2 city-homestay public OTA and short-let listing discovery.
No login, CAPTCHA evasion, personal directory lookups, messaging, or private APIs.
Search results are leads; a contact is only promoted when a public listing page
supports both the business name and its street address.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import html
import json
import os
import pathlib
import random
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import Counter
from functools import lru_cache

import requests
from bs4 import BeautifulSoup

ROOT = pathlib.Path("data/seoul-ota")
SOURCE = pathlib.Path("artifacts/seoul-homestay/seoul_facility_le60.csv")
STAMP = lambda: dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
HEADERS = {"User-Agent": "SeoulHomestayPublicResearch/1.0 (source-link verification; no personal-data scraping)",
           "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7"}
TIMEOUT = (7, 15)
# Registrations are categories, NOT proof that any licensed property is listed.
PLATFORMS = [
 ("airbnb","Airbnb","global_ota",["airbnb.com","airbnb.co.kr"]),
 ("booking","Booking.com","global_ota",["booking.com"]),
 ("agoda","Agoda","global_ota",["agoda.com"]),
 ("hotels","Hotels.com","global_ota",["hotels.com"]),
 ("expedia","Expedia","global_ota",["expedia.com"]),
 ("trip","Trip.com / Ctrip","global_ota",["trip.com","ctrip.com"]),
 ("hostelworld","Hostelworld","global_ota",["hostelworld.com"]),
 ("vrbo","Vrbo","global_ota",["vrbo.com"]),
 ("traveloka","Traveloka","global_ota",["traveloka.com"]),
 ("priceline","Priceline","global_ota",["priceline.com"]),
 ("rakuten","Rakuten Travel","global_ota",["travel.rakuten.com"]),
 ("jalan","Jalan","global_ota",["jalan.net"]),
 ("klook","Klook","global_ota",["klook.com"]),
 ("tripadvisor","Tripadvisor","metasearch",["tripadvisor.com","tripadvisor.co.kr"]),
 ("kayak","KAYAK","metasearch",["kayak.com","kayak.co.kr"]),
 ("hotelscombined","HotelsCombined","metasearch",["hotelscombined.com","hotelscombined.co.kr"]),
 ("trivago","Trivago","metasearch",["trivago.com","trivago.co.kr"]),
 ("skyscanner","Skyscanner","metasearch",["skyscanner.net","skyscanner.co.kr"]),
 ("google_hotels","Google Hotels / Travel","map_directory",["google.com","google.co.kr"]),
 ("naver","Naver Place / Booking","map_directory",["naver.com","naver.me"]),
 ("kakao","Kakao Map","map_directory",["kakao.com"]),
 ("seoulstay","SeoulStay","official_directory",["stay.visitseoul.net"]),
 ("wehome","Wehome 위홈","korean_ota",["wehome.me"]),
 ("nol","NOL / Yanolja 야놀자","korean_ota",["yanolja.com","nol.yanolja.com"]),
 ("yeogi","여기어때","korean_ota",["yeogi.com"]),
 ("stayfolio","스테이폴리오","korean_ota",["stayfolio.com"]),
 ("myrealtrip","마이리얼트립","korean_ota",["myrealtrip.com"]),
 ("tripbtoz","트립비토즈","korean_ota",["tripbtoz.com"]),
 ("hoteljoy","호텔엔조이","korean_ota",["hotelnjoy.com"]),
 ("tourvis","투어비스","korean_ota",["tourvis.com"]),
 ("privia","프리비아","korean_ota",["priviatravel.com"]),
 ("hotels_pass","호텔패스","korean_ota",["hotelpass.com"]),
 ("allmytour","올마이투어","korean_ota",["allmytour.com"]),
 ("stayandmore","스테이앤모어","korean_ota",["stayandmore.com"]),
 ("webtour","웹투어","korean_ota",["webtour.com"]),
 ("ttn","떠나요닷컴","korean_ota",["ddnayo.com"]),
 ("33m2","삼삼엠투","short_let",["33m2.co.kr"]),
 ("liveanywhere","리브애니웨어","short_let",["liveanywhere.me"]),
 ("mrmention","미스터멘션","short_let",["mrmention.co.kr"]),
 ("dandan","단단홈즈","short_let",["dandanhomes.com"]),
 ("homes","HOMES / 홈즈스테이 (운영사)","managed_stay",["homes.global","homes-stay.com"]),
 ("zipbang","직방 단기임대","short_let",["str.zigbang.com","zigbang.com"]),
 ("spacecloud","스페이스클라우드","space_rental",["spacecloud.kr"]),
 ("blueground","블루그라운드","short_let",["theblueground.com"]),
 ("coupangtravel","쿠팡트래블","korean_ota",["coupang.com"]),
 ("plottlife","플라트라이프","short_let",["life.plott.co.kr"]),
 ("actingfarm","액팅팜","local_stay",["actingfarm.com"]),
 ("springhouse","봄집","short_let",["springhouse.co.kr"]),
]
DOMAIN_MAP = [(d.lower(), pid, label, kind) for pid,label,kind,ds in PLATFORMS for d in ds]
# Five stages ensure coverage of the entire registry without an exponential site-by-site scan.
FAMILIES = [
 ("general", []),
 ("global_primary", ["airbnb.com","booking.com","agoda.com","trip.com","hotels.com","expedia.com"]),
 ("global_secondary", ["hostelworld.com","vrbo.com","kayak.com","hotelscombined.com","tripadvisor.com","trivago.com","traveloka.com"]),
 ("korean_ota", ["wehome.me","yanolja.com","yeogi.com","stayfolio.com","myrealtrip.com","tripbtoz.com","tourvis.com","stay.visitseoul.net"]),
 ("short_let_maps", ["33m2.co.kr","liveanywhere.me","mrmention.co.kr","str.zigbang.com","dandanhomes.com","homes.global","life.plott.co.kr","naver.com","kakao.com","google.com","spacecloud.kr"]),
 ("other_channels", ["hotelnjoy.com","hotelpass.com","allmytour.com","ddnayo.com","webtour.com","rakuten.com","jalan.net","priceline.com","klook.com"]),
]
PHONE = re.compile(r"(?<!\d)(?:\+82[\s().-]*|0)(?:2|70|80|1[016789]|[3-6]\d)[\s().-]*\d{3,4}[\s().-]*\d{4}(?!\d)")
EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
BLACKLIST_PHRASES = {"customer service","contact support","고객센터","고객 지원","예약고객센터","고객센터 전화"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
ROBOTS = {}
COUNTS = Counter()

def normalize(x):
    x = unicodedata.normalize("NFKC", str(x or "")).casefold()
    return re.sub(r"[^0-9a-z가-힣]", "", x)

def short_name(name):
    return re.split(r"[\(\（]",name or "")[0].strip() or (name or "").strip()

def address_key(address):
    # Road name + building number, not neighborhood, city or floor.
    m = re.search(r"([가-힣0-9]+(?:로|길)[가-힣0-9-]*\s*\d+(?:-\d+)?)", str(address or ""))
    return normalize(m.group(1)) if m else ""

def domain_info(url):
    p = urllib.parse.urlparse(url)
    netloc = (p.hostname or "").lower().strip(".")
    if netloc in {"blog.naver.com","m.blog.naver.com"}:return None
    if "/Attraction_Review" in p.path:return None
    for domain,pid,label,kind in sorted(DOMAIN_MAP,key=lambda x:-len(x[0])):
        if netloc == domain or netloc.endswith("."+domain):
            return pid,label,kind
    return None

def clean_url(href):
    href=html.unescape(str(href or "")).strip()
    if href.startswith("//"):href="https:"+href
    if href.startswith("/url?"):
        href=urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("q",[""])[0]
    ddg=urllib.parse.urlparse(href)
    if (ddg.hostname or "").endswith("duckduckgo.com") and ddg.path.startswith("/l/"):
        href=urllib.parse.parse_qs(ddg.query).get("uddg",[""])[0]
    p=urllib.parse.urlparse(href)
    if p.scheme not in {"http","https"} or not p.netloc:return ""
    if len(href)>1500:return ""
    return urllib.parse.urlunparse((p.scheme,p.netloc,p.path,"",p.query,""))

def load_records():
    with SOURCE.open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    good={}
    for r in rows:
        status=r.get("영업상태명","")
        if status != "폐업" and "영업" not in status:continue
        code=r.get("개방자치단체코드","")
        num=r.get("관리번호","")
        name=r.get("사업장명","").strip()
        address=r.get("도로명주소","").strip() or r.get("지번주소","").strip()
        if not (code and num and name):continue
        key=code+"__"+num
        good[key]={"license_id":key,"name":name,"address":address,
                   "status":"closed" if status=="폐업" else "active",
                   "closed_date":r.get("폐업일자",""),
                   "area":r.get("시설면적",""),
                   "permit_phone":r.get("전화번호","").strip()}
    if len(rows)<5000 or len(good)<4500:
        raise RuntimeError("Incomplete official input; refusing to advance scan cursor")
    return good

def load_json(path,default):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:return default

def atomic_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+".tmp")
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
    temp.replace(path)

def append_rows(path,rows,cols):
    if not rows:return
    path.parent.mkdir(parents=True,exist_ok=True)
    fresh=not path.exists()
    with path.open("a",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,cols,extrasaction="ignore")
        if fresh:w.writeheader()
        w.writerows(rows)

def search_terms(r,stage):
    name=short_name(r["name"])
    alternate=re.search(r"\(([^()]+)\)",r["name"])
    if stage.startswith("global") and alternate and re.search(r"[A-Za-z]",alternate.group(1)):
        name=alternate.group(1).strip()
    addr=r["address"]
    road=address_key(addr)
    road_human=re.search(r"([가-힣0-9]+(?:로|길)[가-힣0-9-]*\s*\d+(?:-\d+)?)",addr)
    district=(re.search(r"서울특별시\s+([가-힣]+구)",addr) or [None,"서울"])[1]
    if stage=="general":
        return f'"{name}" 서울'
    domains=dict(FAMILIES)[stage]
    # A constrained OR query; search results are not counted as a listing unless a target URL is found.
    sides=" OR ".join("site:"+d for d in domains)
    address_part=(' "'+road_human.group(1)+'"') if road_human else (' "'+district+'"')
    return f'"{name}"{address_part} ({sides})'

def get_search_results(query,max_results):
    # Public Bing RSS endpoint. Do not evade anti-automation challenges.
    providers=[("bing_rss","https://www.bing.com/search?format=rss&q="+urllib.parse.quote(query)),
               ("duckduckgo_lite","https://lite.duckduckgo.com/lite/?q="+urllib.parse.quote(query))]
    errors=[]
    any_success=False
    for provider,url in providers:
        try:
            resp=SESSION.get(url,timeout=TIMEOUT)
            if resp.status_code in (403,429,503):
                raise RuntimeError(f"blocked_{resp.status_code}")
            resp.raise_for_status()
            out=[]
            if provider=="bing_rss":
                root=ET.fromstring(resp.content)
                for item in root.findall(".//item"):
                    link=clean_url(item.findtext("link"))
                    title=item.findtext("title") or ""
                    snippet=BeautifulSoup(item.findtext("description") or "","html.parser").get_text(" ",strip=True)
                    if link:out.append((link,title,snippet))
            else:
                soup=BeautifulSoup(resp.text,"html.parser")
                for a in soup.select("a.result-link, a.result__a"):
                    link=clean_url(a.get("href",""))
                    if link:out.append((link,a.get_text(" ",strip=True),""))
            COUNTS["search_"+provider+"_ok"]+=1
            any_success=True
            if out:return out[:max_results],provider,errors
            COUNTS["search_"+provider+"_empty"]+=1
        except Exception as e:
            errors.append(provider+":"+type(e).__name__+":"+str(e)[:100])
            COUNTS["search_"+provider+"_fail"]+=1
    return [],("no_results" if any_success else "unavailable"),errors

@lru_cache(maxsize=128)
def can_fetch(url):
    # Robots rules differ by PATH on the same host: cache parser, not a host-wide boolean.
    p=urllib.parse.urlparse(url)
    host=p.scheme+"://"+p.netloc
    if host not in ROBOTS:
        try:
            r=SESSION.get(host+"/robots.txt",timeout=(4,7))
            if r.status_code==404:
                ROBOTS[host]=True
            elif r.status_code in (401,403,429) or r.status_code>=500:
                ROBOTS[host]=False
            else:
                rp=urllib.robotparser.RobotFileParser()
                rp.parse(r.text.splitlines())
                ROBOTS[host]=rp
        except Exception:
            ROBOTS[host]=False
    rule=ROBOTS[host]
    return rule if isinstance(rule,bool) else rule.can_fetch(HEADERS["User-Agent"],url)

def page_content(url):
    if not can_fetch(url):return "", "robots_denied_or_unavailable"
    try:
        r=SESSION.get(url,timeout=TIMEOUT)
        if r.status_code in (403,429,503):return "",f"site_blocked_{r.status_code}"
        r.raise_for_status()
        if "html" not in r.headers.get("Content-Type","").lower():return "","not_html"
        if len(r.content)>1_500_000:return "","oversize"
        soup=BeautifulSoup(r.text,"html.parser")
        for el in soup(["script","style","nav","footer"]):el.decompose()
        return soup.get_text(" ",strip=True)[:220_000],""
    except Exception as e:return "", type(e).__name__

def match_grade(record,title,snippet,page_text):
    # Name-only may be a DIFFERENT business. Only exact street + name is a strong match.
    hay=normalize(" ".join([title,snippet,page_text]))
    n=normalize(short_name(record["name"]))
    a=address_key(record["address"])
    name_ok=bool(n and len(n)>=4 and n in hay)
    addr_ok=bool(a and a in hay)
    if name_ok and addr_ok:return "name_and_road"
    if name_ok:return "name_only_unverified"
    if addr_ok:return "road_only_unverified"
    return "unverified"

def published_contacts(page_text,title,snippet,grade):
    # Extract only business-published telephone next to a clear contact label,
    # never from an unverified search snippet or a platform global help page.
    if grade!="name_and_road" or not page_text:return "",""
    texts=[]
    for x in PHONE.finditer(page_text):
        neighborhood=page_text[max(0,x.start()-90):min(len(page_text),x.end()+55)]
        if re.search(r"전화|연락처|문의|전화번호|tel(?:ephone)?|phone|contact",neighborhood,re.I):
            if not any(block in neighborhood.lower() for block in BLACKLIST_PHRASES):
                texts.append(re.sub(r"[^\d+]","",x.group()))
    emails=[]
    for x in EMAIL.finditer(page_text):
        neighborhood=page_text[max(0,x.start()-75):min(len(page_text),x.end()+55)]
        if re.search(r"이메일|문의|email|e-mail|contact",neighborhood,re.I):
            emails.append(x.group().lower())
    return " | ".join(sorted(set(texts))[:5])," | ".join(sorted(set(emails))[:3])

EVIDENCE_COLS=["license_id","business_name","permit_status","closed_date","facility_area","permit_address",
 "platform_id","platform","category","listing_url","title","search_excerpt","match_grade",
 "public_business_phone","public_business_email","contact_status","search_provider","stage",
 "page_fetch_error","observed_at"]
ATTEMPT_COLS=["license_id","business_name","stage","search_provider","result_count",
              "platform_hits","verified_address_matches","error","observed_at"]

def run(args):
    assert len(FAMILIES)==len(set(name for name,_ in FAMILIES))
    assert len(PLATFORMS)==len(set(p[0] for p in PLATFORMS))
    rows=load_records()
    ROOT.mkdir(parents=True,exist_ok=True)
    state=load_json(ROOT/"state.json",{"version":1,"progress":{},"first_started_at":STAMP()})
    progress=state.get("progress",{})
    ids=sorted(rows,key=lambda k:(int(progress.get(k,{}).get("stage_idx",0)),
                                  progress.get(k,{}).get("last_attempt",""),k))
    selected=ids[:args.batch_size]
    seen=set()
    if (ROOT/"listing_evidence.csv").exists():
        with (ROOT/"listing_evidence.csv").open(encoding="utf-8-sig",newline="") as f:
            for r in csv.DictReader(f):
                seen.add((r["license_id"],r["listing_url"]))
    evidence=[];attempts=[]
    for i,key in enumerate(selected,1):
        rec=rows[key]
        old=progress.get(key,{})
        stage_idx=int(old.get("stage_idx",0))
        stage=FAMILIES[stage_idx % len(FAMILIES)][0]
        query=search_terms(rec,stage)
        results,engine,errs=get_search_results(query,args.max_results)
        # Korean registered names may have an English OTA listing title.
        if not results:
            alias=re.search(r"\(([^()]+)\)",rec["name"])
            if alias and re.search(r"[A-Za-z]",alias.group(1)):
                retry,engine2,errs2=get_search_results(f'"{alias.group(1).strip()}" Seoul',args.max_results)
                errs.extend(errs2)
                if retry:
                    results,engine=retry,engine2
        hits=0;good=0
        if engine=="unavailable":
            attempts.append({"license_id":key,"business_name":rec["name"],"stage":stage,
              "search_provider":engine,"result_count":0,"platform_hits":0,
              "verified_address_matches":0,"error":";".join(errs),"observed_at":STAMP()})
            COUNTS["search_unavailable"]+=1
            # Do not advance on complete upstream failure. Stop the run rather than claim empty results.
            break
        for url,title,snippet in results:
            d=domain_info(url)
            if not d or (key,url) in seen:continue
            # Skip obvious homepages and non-accommodation search result URLs.
            if len(urllib.parse.urlparse(url).path.strip("/"))<5:continue
            pid,label,kind=d
            text,err=page_content(url)
            grade=match_grade(rec,title,snippet,text)
            if grade=="unverified":
                COUNTS["irrelevant_result_rejected"]+=1
                continue
            phone,email=published_contacts(text,title,snippet,grade)
            status="public_contact_address_matched" if (phone or email) else "listing_candidate_only"
            evidence.append({"license_id":key,"business_name":rec["name"],
              "permit_status":rec["status"],"closed_date":rec["closed_date"],
              "facility_area":rec["area"],"permit_address":rec["address"],
              "platform_id":pid,"platform":label,"category":kind,"listing_url":url,
              "title":title,"search_excerpt":snippet[:800],"match_grade":grade,
              "public_business_phone":phone,"public_business_email":email,
              "contact_status":status,"search_provider":engine,
              "stage":stage,"page_fetch_error":err,"observed_at":STAMP()})
            seen.add((key,url));hits+=1
            if grade=="name_and_road":good+=1
        attempts.append({"license_id":key,"business_name":rec["name"],"stage":stage,
            "search_provider":engine,"result_count":len(results),"platform_hits":hits,
            "verified_address_matches":good,"error":";".join(errs),"observed_at":STAMP()})
        old["stage_idx"]=stage_idx+1
        old["last_attempt"]=STAMP()
        progress[key]=old
        COUNTS["properties_stages_completed"]+=1
        time.sleep(args.delay)
    append_rows(ROOT/"listing_evidence.csv",evidence,EVIDENCE_COLS)
    append_rows(ROOT/"search_attempts.csv",attempts,ATTEMPT_COLS)
    state["progress"]=progress
    state["latest_run_at"]=STAMP()
    state["platforms"]=len(PLATFORMS)
    state["stages"]=len(FAMILIES)
    state["input_records"]=len(rows)
    state["done_full_pass"]=sum(int(x.get("stage_idx",0))>=len(FAMILIES) for x in progress.values())
    state["total_stages_completed"]=sum(int(x.get("stage_idx",0)) for x in progress.values())
    state["last_run"]={"selected":len(selected),"advanced":COUNTS["properties_stages_completed"],
                       "new_evidence":len(evidence),"new_public_contacts":sum(bool(r["public_business_phone"] or r["public_business_email"]) for r in evidence),
                       "counts":dict(COUNTS)}
    atomic_json(ROOT/"state.json",state)
    manifest={"run_time":STAMP(),"official_rows":len(rows),"active":sum(r["status"]=="active" for r in rows.values()),
      "closed":sum(r["status"]=="closed" for r in rows.values()),
      "missing_public_address":sum(not r["address"] for r in rows.values()),"platform_count":len(PLATFORMS),
      "platforms":[{"id":x[0],"label":x[1],"category":x[2],"domains":x[3]} for x in PLATFORMS],
      "stages":len(FAMILIES),"last_run":state["last_run"],
      "critical":"Search hits are NOT verified accommodation listings. Only 'name_and_road' evidence supports an address match; contacts are NOT call-verified. The permit area is NOT exclusive area.",
      "scraping_policy":"public search/robots permitted pages only; no authentication, messages, CAPTCHAs or bypass."}
    atomic_json(ROOT/"manifest.json",manifest)
    print(json.dumps({k:v for k,v in manifest.items() if k!="platforms"},ensure_ascii=False,indent=2))
    if COUNTS["search_unavailable"]:
        raise RuntimeError("All public search providers unavailable; progress not advanced for failed item")

def selftest():
    assert address_key("서울특별시 종로구 성균관로5가길 3, B1층")=="성균관로5가길3"
    assert domain_info("https://www.booking.com/hotel/kr/abc.html")[0]=="booking"
    assert domain_info("https://notbooking.com/hotel/kr/abc.html") is None
    assert match_grade({"name":"샘154하우스","address":"서울특별시 종로구 필운대로5길 15"},"샘154하우스","서울 종로구 필운대로5길 15","")=="name_and_road"
    assert published_contacts("전화번호 010-3249-0106 문의처", "", "", "name_only_unverified")==("","")
    assert domain_info("https://homes.global/ko/brands/stay")[0]=="homes"
    assert PHONE.search("전화 070-8809-0955")
    assert clean_url("https://duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.booking.com%2Fhotel%2Fkr%2Fsample.html")=="https://www.booking.com/hotel/kr/sample.html"
    assert len(PLATFORMS)>=40
    print("SELFTEST_OK platforms="+str(len(PLATFORMS))+" stages="+str(len(FAMILIES)))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--batch-size",type=int,default=35)
    p.add_argument("--max-results",type=int,default=10)
    p.add_argument("--delay",type=float,default=1.2)
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:selftest()
    else:run(a)
