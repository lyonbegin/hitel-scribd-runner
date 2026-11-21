#!/usr/bin/env python3
"""Official SeoulStay directory: public listing URL and booking-link discovery.
No login, cookies, contacts behind authentication, or outbound messages.
Source: https://stay.visitseoul.net/seoul-stay (public pages).
"""
from __future__ import annotations
import csv, concurrent.futures, datetime as dt, json, os, pathlib, random, re, time
from urllib.parse import urljoin, urlparse, parse_qs
import requests
from bs4 import BeautifulSoup

BASE="https://stay.visitseoul.net"
OUT=pathlib.Path("artifacts/seoul-stay-contacts")
OUT.mkdir(parents=True,exist_ok=True)
HEAD={"User-Agent":"Mozilla/5.0 (compatible; SeoulStayPublicDirectoryResearch/1.0; public data audit)"}
ERRORS=[]
def fetch(url):
    for k in range(3):
        try:
            r=requests.get(url,headers=HEAD,timeout=25)
            r.raise_for_status()
            if not r.text or "서울스테이" not in r.text and "Seoul" not in r.text and "view/" not in r.text:
                raise ValueError("unexpected empty/unrelated page")
            return r.text
        except Exception as e:
            err=str(e)
            if k!=2: time.sleep(0.5+k)
    return None

def listing_ids(html):
    s=BeautifulSoup(html,"html.parser")
    found={}
    for a in s.find_all("a",href=True):
        href=a.get("href","")
        if "/seoul-stay/view/" not in href:continue
        abs_url=urljoin(BASE,href).replace(":80/","/")
        p=parse_qs(urlparse(abs_url).query)
        ident=p.get("us",[""])[0]
        if not ident:continue
        found[ident]={"us":ident,"url":abs_url,"text":a.get_text(" ",strip=True)}
    return found
def crawl_index(lang):
    allitems={}
    failed=[]
    def one(page):
        u=f"{BASE}/seoul-stay?lang={lang}&page={page}"
        h=fetch(u)
        return page,h,listing_ids(h) if h else {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        for page,html,items in ex.map(one,range(1,66)):
            if html is None:failed.append(page)
            allitems.update(items)
    return allitems,failed

en,enfail=crawl_index("en")
ko,kofail=crawl_index("ko")
allids=sorted(set(en)|set(ko),reverse=True)
def one_detail(ident):
    en_url=(en.get(ident) or {}).get("url",f"{BASE}/seoul-stay?lang=en")
    en_url=re.sub(r"([?&])lang=[^&]+",r"\1lang=en",en_url)
    html=fetch(en_url)
    result={"us":ident,"seoulstay_en":en_url,"seoulstay_ko":(ko.get(ident) or {}).get("url",""),
      "directory_name_ko":(ko.get(ident) or {}).get("text",""),
      "directory_name_en":(en.get(ident) or {}).get("text",""),
      "details_ok":bool(html),"published_booking_links":"","booking_domains":"",
      "displayed_address":"","booking_link_count":0}
    if not html:return result
    soup=BeautifulSoup(html,"html.parser")
    body=soup.get_text(" ",strip=True)
    match=re.search(r"Address\s*:\s*(.{5,160}?)(?:\s*\(lat:|\s*See map|\s*\bFooter\b|$)",body,re.I)
    if match:result["displayed_address"]=match.group(1).strip()
    all_links=[]
    for a in soup.find_all("a",href=True):
        link=urljoin(BASE,a.get("href","")).strip()
        domain=urlparse(link).netloc.lower()
        if any(x in domain for x in ("airbnb.","wehome.me","booking.com","agoda.com","expedia.","trip.com","yanolja.","nol-universe.","hotels.com","stayfolio.")):
            if link not in all_links:all_links.append(link)
    result["published_booking_links"]=" | ".join(all_links)
    result["booking_domains"]=" | ".join(sorted(set(urlparse(a).netloc for a in all_links)))
    result["booking_link_count"]=len(all_links)
    return result
with concurrent.futures.ThreadPoolExecutor(max_workers=7) as ex:
    rows=list(ex.map(one_detail,allids))
cols=["us","directory_name_ko","directory_name_en","displayed_address","booking_link_count","booking_domains","published_booking_links","seoulstay_ko","seoulstay_en","details_ok"]
with open(OUT/"seoulstay_official_booking_links.csv","w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=cols,extrasaction="ignore");w.writeheader();w.writerows(rows)
manifest={
 "collected_at":dt.datetime.now(dt.timezone.utc).isoformat(),
 "source":BASE+"/seoul-stay?lang=ko",
 "pages_attempted_per_language":65,
 "english_index_failures":enfail,
 "korean_index_failures":kofail,
 "unique_listing_ids":len(allids),
 "details_read":sum(x["details_ok"] for x in rows),
 "rows_with_public_booking_link":sum(bool(x["booking_link_count"]) for x in rows),
 "booking_link_total":sum(x["booking_link_count"] for x in rows),
 "first_rows":rows[:4],
 "important":"Booking links are NOT approved marketing channels; Airbnb/Wehome prohibits unsolicited commercial communications; no messaging was sent."
}
(OUT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(manifest,ensure_ascii=False,indent=2))
