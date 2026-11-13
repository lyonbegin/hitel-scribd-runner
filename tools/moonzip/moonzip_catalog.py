#!/usr/bin/env python3
"""Moonzip public book metadata crawler. Preserve cover image URLs, never fetch image bodies or write image files.
Supports pilot and resumable full scans. No authentication/access-challenge circumvention.
"""
import argparse
import asyncio
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright

ROOT="https://moonzip.kr"
OUT=Path("moonzip-results")
SEED_SERIES=[
 "c335a5f7-3f6b-438a-8442-ba535c2e5918",
 "2b6719bf-f758-4497-9b41-81301ce9c85c",
 "43567ca7-2583-49fb-b629-786c360144e1",
]
UUID=r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
BOOK_RE=re.compile(r"/books/("+UUID+r")(?=$|[/?#])")
SERIES_RE=re.compile(r"/series/("+UUID+r")(?=$|[/?#])")
FATAL_RE=re.compile(r"verify you are human|CAPTCHA|Client Challenge|access denied|unusual traffic",re.I)
ANS_RE=re.compile(r"(정답\s*및\s*해설|정답\s*해설|정답과\s*해설|해설지|해답지|답지|정답지|정답편|해설편|솔루션)",re.I)
NOW=lambda:datetime.now(timezone.utc).isoformat()

def save(path,data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_name(path.name+".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(path)

def url_id(url,pattern):
    m=pattern.search(url or "")
    return m.group(1).lower() if m else ""

def checked_http(url):
    p=urlparse(url)
    return p.scheme in ("http","https") and bool(p.netloc)

def strip(s):
    return " ".join((s or "").split()).strip()

async def scan_page(page,url):
    response=await page.goto(url,wait_until="domcontentloaded",timeout=30000)
    await page.wait_for_timeout(600)
    js="""() => ({
      title:document.title || '',
      h1:document.querySelector('h1')?.innerText?.trim()||'',
      body:(document.body?.innerText || '').slice(0,14000),
      links:Array.from(document.querySelectorAll('a[href]')).map(a=>({
        href:a.href,text:(a.innerText||a.getAttribute('aria-label')||'').trim().slice(0,250),
        cover:(a.querySelector('img')?.getAttribute('src')||''),
        coverAlt:(a.querySelector('img')?.getAttribute('alt')||'')
      })).filter(a=>a.href.includes('moonzip.kr/')).slice(0,1500),
      covers:Array.from(document.querySelectorAll('img[alt*="표지"]')).map(i=>({
        alt:i.getAttribute('alt')||'',url:i.getAttribute('src')||'',
        displayUrl:i.currentSrc||''
      })).slice(0,250)
    })"""
    data=await page.evaluate(js)
    data["http_status"]=response.status if response else 0
    data["final_url"]=page.url
    if FATAL_RE.search(data.get("body","")[:2500]):
        raise RuntimeError("ACCESS_CHALLENGE")
    if data["http_status"]>=400:
        raise RuntimeError("HTTP_"+str(data["http_status"]))
    return data

async def open_page(browser,url):
    page=await browser.new_page()
    try:
        data=await asyncio.wait_for(scan_page(page,url),timeout=43)
        return page,data
    except Exception:
        await page.close()
        raise

async def collect_one(context,url):
    for attempt in range(2):
        page=None
        try:
            page,data=await open_page(context,url)
            return page,data
        except Exception as e:
            if "ACCESS_CHALLENGE" in str(e):
                raise
            if attempt:
                raise
            await asyncio.sleep(1.3)
    raise RuntimeError("Unexpected retry flow")

def cover_from(data, title="",series=False):
    covers=data.get("covers",[])
    title=strip(title)
    # Main cover typically first on Moonzip book/series pages; prefer matching alt.
    for x in covers:
        if title and title in strip(x.get("alt","")) and checked_http(x.get("url","")):
            return x["url"]
    for x in covers:
        if checked_http(x.get("url","")):
            return x["url"]
    return ""

async def catalogue(context,mode,series_limit,book_limit,delay):
    OUT.mkdir(exist_ok=True)
    sfile=OUT/"series.json"
    bfile=OUT/"books.json"
    listing=OUT/"search_pages.json"
    series=json.loads(sfile.read_text(encoding="utf-8")) if sfile.exists() else {}
    books=json.loads(bfile.read_text(encoding="utf-8")) if bfile.exists() else {}
    search_pages=json.loads(listing.read_text(encoding="utf-8")) if listing.exists() else {}
    seeds={}
    if mode=="probe":
        seeds={i:ROOT+"/series/"+i for i in SEED_SERIES}
        search_pages_count=1
    else:
        search_pages_count=31
    for page_num in range(1,search_pages_count+1):
        key=str(page_num)
        if key in search_pages:
            entry=search_pages[key]
        else:
            url=ROOT+"/search"+(f"?page={page_num}" if page_num>1 else "")
            page,data=await collect_one(context,url)
            try:
                ids={url_id(x["href"],SERIES_RE):x["href"] for x in data["links"] if url_id(x["href"],SERIES_RE)}
                entry={"url":url,"series":ids,"body_count":re.search(r"전체\s*([0-9,]+)\s*개\s*시리즈",data["body"]).group(1) if re.search(r"전체\s*([0-9,]+)\s*개\s*시리즈",data["body"]) else "",
                       "title":data["title"],"checked_at":NOW()}
            finally:
                await page.close()
            search_pages[key]=entry
            save(listing,search_pages)
            print("MOONZIP_SEARCH_PAGE",json.dumps({"page":page_num,"series":len(entry["series"]),"total_label":entry["body_count"]},ensure_ascii=False),flush=True)
            await asyncio.sleep(delay)
        seeds.update(entry["series"])
    if mode=="full" and search_pages_count==31 and len(seeds)<350:
        raise RuntimeError(f"Search series enumeration incomplete: {len(seeds)}/370")
    if mode=="probe":
        seeds={i:ROOT+"/series/"+i for i in SEED_SERIES}
    print("MOONZIP_DISCOVERY",json.dumps({"mode":mode,"unique_series":len(seeds),"search_pages":len(search_pages)},ensure_ascii=False),flush=True)
    selected=list(seeds.items())[:series_limit or len(seeds)]
    for ix,(sid,url) in enumerate(selected,1):
        if sid in series and series[sid].get("complete"):
            continue
        page,data=await collect_one(context,url)
        try:
            initial={url_id(x["href"],BOOK_RE):x for x in data["links"] if url_id(x["href"],BOOK_RE)}
            before=len(initial)
            # On the series page "전체 보기" expands the full list in place or in modal.
            actions=page.get_by_text("전체 보기",exact=False)
            if await actions.count():
                try:
                    await actions.last.click(timeout=3500)
                    await page.wait_for_timeout(1500)
                    more=await page.evaluate("""() => Array.from(document.querySelectorAll('a[href*="/books/"]')).map(a=>({
                      href:a.href,text:(a.innerText||a.getAttribute('aria-label')||'').trim(),
                      cover:(a.querySelector('img')?.getAttribute('src')||'')
                    }))""")
                    for x in more:
                        bid=url_id(x["href"],BOOK_RE)
                        if bid: initial[bid]=x
                except Exception as e:
                    print("MOONZIP_EXPAND_WARNING",json.dumps({"series_id":sid,"error":f"{type(e).__name__}:{str(e)[:100]}"},ensure_ascii=False),flush=True)
            label=re.search(r"(?:같은 시리즈의 다른 책|시리즈 내 다른 책)\s*\((\d+)\s*권\)",data["body"])
            count=int(label.group(1)) if label else None
            if count is not None and len(initial)<count:
                debug=await page.evaluate("""() => ({
                  current_url:location.href,
                  footer:(document.body?.innerText||'').slice(-3000),
                  controls:Array.from(document.querySelectorAll('button')).map(b=>({
                    text:(b.innerText||b.getAttribute('aria-label')||'').trim().slice(0,60),
                    disabled:b.disabled
                  })).filter(x=>x.text).slice(-40),
                  book_links_count:document.querySelectorAll('a[href*="/books/"]').length,
                  overlays:Array.from(document.querySelectorAll('[role="dialog"],[aria-modal="true"]')).map(x=>x.innerText.slice(0,1000))
                })""")
                print("MOONZIP_EXPANSION_DIAG",json.dumps({"series_id":sid,"expected":count,"found":len(initial),"debug":debug},ensure_ascii=False),flush=True)
            series[sid]={"series_id":sid,"series_url":url,"series_name":strip(data["h1"]),
                         "series_cover_image_url":cover_from(data,data["h1"],series=True),
                         "series_page_title":data["title"],
                         "visible_books_before_expand":before,"visible_books_after_expand":len(initial),
                         "site_book_count_label":count,"book_ids":list(initial),
                         "checked_at":NOW(),"complete":True}
            for bid,link in initial.items():
                if bid not in books:
                    books[bid]={"book_id":bid,"book_url":link["href"],"book_title":strip(link["text"]),"series_id":sid,
                                "series_name":strip(data["h1"]),"cover_image_url":link.get("cover",""),
                                "answer_or_explanation":bool(ANS_RE.search(link["text"])),"detail_checked":False}
                elif not books[bid].get("series_id"):
                    books[bid]["series_id"]=sid
            save(sfile,series)
            save(bfile,books)
            print("MOONZIP_SERIES",json.dumps({"done":ix,"series_id":sid,"name":data["h1"],"cover_url":series[sid]["series_cover_image_url"],
                                               "initial_books":before,"expanded_books":len(initial),"site_book_count":count},ensure_ascii=False),flush=True)
        finally:
            await page.close()
        await asyncio.sleep(delay)
    todo=[b for b in books.values() if not b.get("detail_checked")]
    if book_limit:
        todo=todo[:book_limit]
    for ix,book in enumerate(todo,1):
        page=None
        try:
            page,data=await collect_one(context,book["book_url"])
            book["book_title"]=strip(data["h1"]) or book["book_title"]
            book["cover_image_url"]=cover_from(data,book["book_title"]) or book.get("cover_image_url","")
            book["detail_title"]=data["title"]
            book["body_summary"]=data["body"][:750]
            book["answer_or_explanation"]=bool(ANS_RE.search(book["book_title"]))
            book["detail_checked"]=True
            book["checked_at"]=NOW()
            print("MOONZIP_BOOK",json.dumps({"done":ix,"id":book["book_id"],"title":book["book_title"],
                      "series_id":book["series_id"],"cover_image_url":book["cover_image_url"]},ensure_ascii=False),flush=True)
        except Exception as exc:
            book["detail_error"]=f"{type(exc).__name__}: {str(exc)[:250]}"
            print("MOONZIP_BOOK_ERROR",json.dumps({"id":book["book_id"],"error":book["detail_error"]},ensure_ascii=False),flush=True)
            if "ACCESS_CHALLENGE" in str(exc):
                raise
        finally:
            if page:
                await page.close()
        if ix%5==0:
            save(bfile,books)
        await asyncio.sleep(delay)
    save(bfile,books)
    # All outputs contain URLs/metadata only; no PNG/JPG files or image payloads.
    with (OUT/"books.csv").open("w",encoding="utf-8-sig",newline="") as f:
        fields=["book_id","book_title","book_url","series_id","series_name","cover_image_url",
                "answer_or_explanation","detail_checked","checked_at","detail_error"]
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader()
        for x in books.values():w.writerow(x)
    with (OUT/"series.csv").open("w",encoding="utf-8-sig",newline="") as f:
        fields=["series_id","series_name","series_url","series_cover_image_url","visible_books_after_expand",
                "site_book_count_label","checked_at"]
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader()
        for x in series.values():w.writerow(x)
    stats={"series_discovered":len(seeds),"series_crawled":sum(bool(x.get("complete")) for x in series.values()),
           "books_discovered":len(books),"book_details_checked":sum(bool(x.get("detail_checked")) for x in books.values()),
           "book_cover_urls":sum(bool(x.get("cover_image_url")) for x in books.values()),
           "series_cover_urls":sum(bool(x.get("series_cover_image_url")) for x in series.values()),
           "excluded_answer_or_explanation":sum(bool(x.get("answer_or_explanation")) for x in books.values()),
           "image_files_downloaded":0,"mode":mode,"updated_at":NOW()}
    save(OUT/"summary.json",stats)
    print("MOONZIP_CATALOG_SUMMARY",json.dumps(stats,ensure_ascii=False),flush=True)

async def main(args):
    async with async_playwright() as p:
        browser=await p.chromium.launch(channel="chrome",headless=False)
        context=await browser.new_context(locale="ko-KR",viewport={"width":1366,"height":900})
        async def abort_images(route):
            if route.request.resource_type in ("image","media","font"):
                await route.abort()
            else:
                await route.continue_()
        await context.route("**/*",abort_images)
        try:
            await catalogue(context,args.mode,args.series_limit,args.book_limit,args.delay)
        finally:
            await context.close()
            await browser.close()

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=["probe","full"],default="probe")
    p.add_argument("--series-limit",type=int,default=0)
    p.add_argument("--book-limit",type=int,default=0)
    p.add_argument("--delay",type=float,default=1.2)
    args=p.parse_args()
    asyncio.run(main(args))
