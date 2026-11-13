#!/usr/bin/env python3
"""Moonzip public catalogue: TEN simultaneous Chrome tabs, cover URLs only.
Existing Moonzip scan_page helpers are reused. No image file download.
"""
import argparse
import asyncio
import csv
import json
import re
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from moonzip_catalog import (
    ROOT, UUID, NOW, BOOK_RE, SERIES_RE, ANS_RE, save,
    url_id, strip, checked_http, scan_page, cover_from
)

PAGE_SIZE=10
SITE_COUNT=370
LIMIT_PAGE=31
COUNTER=re.compile(r"(?:같은 시리즈의 다른 책|시리즈 내 다른 책)\s*\((\d+)\s*권\)")
TOTAL_RE=re.compile(r"전체\s*([0-9,]+)\s*개\s*시리즈")

def copy_cover_url(image):
    if isinstance(image,str):
        return image if checked_http(image) else ""
    return next((v for v in (image.get("url"),image.get("displayUrl"),image.get("src"))
                 if checked_http(v)), "")

def extract_book_jsonld(raw):
    for block in raw:
        try:
            item=json.loads(block)
            items=item if isinstance(item,list) else [item]
            for obj in items:
                if not isinstance(obj,dict):continue
                if obj.get("@type")=="Book" or "Book" in (obj.get("@type") or []):
                    publisher=obj.get("publisher") or {}
                    author=obj.get("author") or {}
                    return {
                        "isbn":str(obj.get("isbn") or ""),
                        "publisher":publisher.get("name","") if isinstance(publisher,dict) else "",
                        "author":author.get("name","") if isinstance(author,dict) else "",
                        "date_published":str(obj.get("datePublished") or ""),
                        "cover_image_url":copy_cover_url(obj.get("image") or "")
                    }
        except (ValueError,TypeError):
            pass
    return {}

async def visit(page,url):
    err=None
    for attempt in range(2):
        try:
            return await asyncio.wait_for(scan_page(page,url),timeout=44)
        except Exception as exc:
            err=exc
            if "ACCESS_CHALLENGE" in str(exc):raise
            if attempt==0:await asyncio.sleep(0.5)
    raise err

async def concurrently(context, items, action, phase, delay=0.7):
    """Exactly ten tabs open before ten simultaneous page tasks per full batch."""
    output=[]
    for offset in range(0,len(items),PAGE_SIZE):
        chunk=items[offset:offset+PAGE_SIZE]
        pages=await asyncio.gather(*(context.new_page() for _ in chunk))
        print("MOONZIP_TABS_OPEN",json.dumps({
            "phase":phase,"count":len(pages),"batch_start":offset+1,
            "total":len(items),"utc":NOW()
        }),flush=True)
        try:
            results=await asyncio.gather(
                *(action(page,item) for page,item in zip(pages,chunk)),
                return_exceptions=True)
        finally:
            await asyncio.gather(*(page.close(run_before_unload=False) for page in pages),
                                 return_exceptions=True)
        for item,result in zip(chunk,results):
            if isinstance(result,BaseException):
                detail=f"{type(result).__name__}: {str(result)[:240]}"
                print("MOONZIP_ITEM_ERROR",json.dumps({"phase":phase,"item":str(item),
                                                       "error":detail},ensure_ascii=True),flush=True)
                if "ACCESS_CHALLENGE" in detail:raise RuntimeError(detail)
                output.append({"error":detail})
            else:
                output.append(result)
        if delay:await asyncio.sleep(delay)
    return output

async def discover(context,mode,out):
    path=out/"search_pages.json"
    data=json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    pages=list(range(1,2 if mode=="probe" else LIMIT_PAGE+1))
    todo=[n for n in pages if str(n) not in data or not data[str(n)].get("series")]
    async def scan(page,n):
        url=ROOT+"/search"+(f"?page={n}" if n>1 else "")
        response=await visit(page,url)
        entries={}
        for link in response.get("links",[]):
            sid=url_id(link.get("href",""),SERIES_RE)
            if sid: entries[sid]=link["href"]
        m=TOTAL_RE.search(response.get("body",""))
        print("MOONZIP_DISCOVERY_PAGE",json.dumps({
            "page":n,"unique_series_on_page":len(entries),"site_total":m.group(1) if m else ""
        },ensure_ascii=True),flush=True)
        return {"url":url,"series":entries,"total":m.group(1) if m else "",
                "checked_at":NOW()}
    # Per-batch checkpoint: a crashed PC only repeats the current ten URLs.
    for start in range(0,len(todo),10):
        batch=todo[start:start+10]
        rows=await concurrently(context,batch,scan,"search",0.5)
        for n,row in zip(batch,rows):
            if not row.get("error"):data[str(n)]=row
        save(path,data)
    series={}
    for record in data.values():
        series.update(record.get("series",{}))
    if mode=="full" and len(series)<350:
        raise RuntimeError(f"Incomplete discovery: only {len(series)} of {SITE_COUNT} series")
    print("MOONZIP_DISCOVERY_RESULT",json.dumps({"pages":len(data),"series":len(series)}),flush=True)
    return series

async def expand_books(page,data):
    found={}
    def absorb(links):
        for link in links:
            bid=url_id(link.get("href",""),BOOK_RE)
            if bid:found[bid]=link
    absorb(data["links"])
    expected_match=COUNTER.search(data.get("body",""))
    expected=int(expected_match.group(1)) if expected_match else None
    if expected is not None and len(found)>=expected:return found,expected
    # Some series have more than 6 books. Expand every visible '전체 보기' control.
    for pass_no in range(4):
        controls=page.get_by_text("전체 보기",exact=False)
        try:count=min(await controls.count(),5)
        except Exception:count=0
        if count<1:break
        changed=False
        for index in range(count-1,-1,-1):
            try:
                await controls.nth(index).click(timeout=1800)
                await page.wait_for_timeout(450)
                more=await page.evaluate("""() => Array.from(document.querySelectorAll('a[href*="/books/"]'))
                    .map(a=>({href:a.href, text:(a.innerText||'').trim(),
                              cover:a.querySelector('img')?.getAttribute('src')||''}))""")
                old=len(found)
                absorb(more)
                changed=changed or len(found)>old
                if expected and len(found)>=expected:break
            except Exception:
                continue
        if expected and len(found)>=expected:break
        if not changed:break
    return found,expected

async def collect_series(context,seeds,out,limit):
    sfile=out/"series.json"
    bfile=out/"books.json"
    series=json.loads(sfile.read_text(encoding="utf-8")) if sfile.exists() else {}
    books=json.loads(bfile.read_text(encoding="utf-8")) if bfile.exists() else {}
    selected=list(seeds.items())[:limit or len(seeds)]
    todo=[(sid,url) for sid,url in selected
          if sid not in series or not series[sid].get("complete")]
    async def scan(page,pair):
        sid,url=pair
        data=await visit(page,url)
        link_map,expected=await expand_books(page,data)
        image=cover_from(data,data.get("h1",""),series=True)
        complete=bool(link_map) and (expected is None or len(link_map)>=expected)
        row={"series_id":sid,"series_url":url,"series_name":strip(data["h1"]),
             "series_cover_image_url":image,"site_book_count_label":expected,
             "visible_books_after_expand":len(link_map),"book_ids":list(link_map),
             "complete":complete,"checked_at":NOW()}
        print("MOONZIP_SERIES_RESULT",json.dumps({
            "series_id":sid,"name":row["series_name"],"found":len(link_map),
            "site_count":expected,"complete":complete
        },ensure_ascii=True),flush=True)
        return {"series":row,"linked_books":link_map}
    for start in range(0,len(todo),10):
        batch=todo[start:start+10]
        results=await concurrently(context,batch,scan,"series",1)
        for (sid,url),result in zip(batch,results):
            if result.get("error"):
                series[sid]={"series_id":sid,"series_url":url,"complete":False,
                             "error":result["error"],"checked_at":NOW()}
                continue
            row=result["series"]
            series[sid]=row
            for bid,link in result["linked_books"].items():
                old=books.get(bid,{})
                books[bid]={**old,"book_id":bid,"book_url":link["href"],
                            "book_title":strip(link.get("text","")) or old.get("book_title",""),
                            "series_id":sid,"series_name":row["series_name"],
                            "cover_image_url":copy_cover_url(link.get("cover")) or old.get("cover_image_url",""),
                            "answer_or_explanation":bool(ANS_RE.search(link.get("text",""))),
                            "detail_checked":old.get("detail_checked",False)}
        save(sfile,series)
        save(bfile,books)
    return series,books

async def collect_books(context,books,out,limit):
    bfile=out/"books.json"
    todo=[(bid,b) for bid,b in books.items() if not b.get("detail_checked")]
    if limit:todo=todo[:limit]
    async def scan(page,pair):
        bid,book=pair
        data=await visit(page,book["book_url"])
        jsonld_raw=await page.evaluate("""() => Array.from(
            document.querySelectorAll('script[type="application/ld+json"]')
            ).map(x=>x.textContent).slice(0,15)""")
        details=extract_book_jsonld(jsonld_raw)
        title=strip(data["h1"]) or book.get("book_title","")
        cover=details.get("cover_image_url") or cover_from(data,title) or book.get("cover_image_url","")
        print("MOONZIP_BOOK_RESULT",json.dumps({"book_id":bid,"title":title,
            "cover_link":bool(cover)},ensure_ascii=True),flush=True)
        return {"book_title":title,"cover_image_url":cover,
                "isbn":details.get("isbn",""),"publisher":details.get("publisher",""),
                "author":details.get("author",""),"date_published":details.get("date_published",""),
                "answer_or_explanation":bool(ANS_RE.search(title)),
                "detail_checked":True,"checked_at":NOW()}
    for start in range(0,len(todo),10):
        batch=todo[start:start+10]
        rows=await concurrently(context,batch,scan,"books",1)
        for (bid,_),row in zip(batch,rows):
            if row.get("error"):books[bid]["detail_error"]=row["error"]
            else:books[bid].update(row)
        save(bfile,books)
    return books

def export(series,books,out,seeds,mode):
    with (out/"series.csv").open("w",newline="",encoding="utf-8-sig") as f:
        fields=["series_id","series_name","series_url","series_cover_image_url",
                "site_book_count_label","visible_books_after_expand","complete","error"]
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader();w.writerows(series.values())
    with (out/"books.csv").open("w",newline="",encoding="utf-8-sig") as f:
        fields=["book_id","book_title","book_url","series_id","series_name",
                "cover_image_url","isbn","publisher","date_published","author",
                "answer_or_explanation","detail_checked","detail_error"]
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader();w.writerows(books.values())
    summary={"mode":mode,"series_discovered":len(seeds),
             "series_crawled":sum(bool(x.get("complete")) for x in series.values()),
             "series_incomplete":sum(not bool(x.get("complete")) for x in series.values()),
             "books_discovered":len(books),
             "book_details_checked":sum(bool(x.get("detail_checked")) for x in books.values()),
             "series_cover_urls":sum(bool(x.get("series_cover_image_url")) for x in series.values()),
             "book_cover_urls":sum(bool(x.get("cover_image_url")) for x in books.values()),
             "excluded_answer_or_explanation":sum(bool(x.get("answer_or_explanation")) for x in books.values()),
             "image_files_downloaded":0,"simultaneous_chrome_tabs":10,"updated_at":NOW()}
    save(out/"summary.json",summary)
    print("MOONZIP_CATALOG_SUMMARY",json.dumps(summary,ensure_ascii=True),flush=True)
    return summary

async def main(args):
    out=Path(args.out)
    out.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch(channel="chrome",headless=False)
        context=await browser.new_context(locale="ko-KR",viewport={"width":1366,"height":900})
        async def abort_images(route):
            if route.request.resource_type in ("image","media","font"):
                await route.abort()
            else:await route.continue_()
        await context.route("**/*",abort_images)
        try:
            seeds=await discover(context,args.mode,out)
            series,books=await collect_series(context,seeds,out,args.series_limit)
            books=await collect_books(context,books,out,args.book_limit)
            summary=export(series,books,out,seeds,args.mode)
            if args.mode=="probe" and (summary["series_crawled"]<5 or
                summary["book_details_checked"]<8 or summary["book_cover_urls"]<8):
                raise RuntimeError("Ten-tab pilot quality gate failed")
        finally:
            await context.close()
            await browser.close()

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--mode",choices=["probe","full"],default="probe")
    parser.add_argument("--out",default="moonzip-results-parallel")
    parser.add_argument("--series-limit",type=int,default=0)
    parser.add_argument("--book-limit",type=int,default=0)
    args=parser.parse_args()
    asyncio.run(main(args))
