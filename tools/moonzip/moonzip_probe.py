#!/usr/bin/env python3
"""Moonzip 10-tab simultaneous Chrome probe. Save cover image URLs, never download files."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from playwright.async_api import async_playwright

OUT = Path("moonzip-results")
OUT.mkdir(parents=True, exist_ok=True)
URLS = [
    "https://moonzip.kr/search",
    "https://moonzip.kr/series/c335a5f7-3f6b-438a-8442-ba535c2e5918",
    "https://moonzip.kr/series/2b6719bf-f758-4497-9b41-81301ce9c85c",
    "https://moonzip.kr/series/43567ca7-2583-49fb-b629-786c360144e1",
    "https://moonzip.kr/books/c66dbaa8-9a88-4394-828c-13a5e71486f5",
    "https://moonzip.kr/series/8b136e40-06b0-4b83-924e-358819df5ada",
    "https://moonzip.kr/series/49ca91bd-5b1f-4c05-8e07-9dee557c26c7",
    "https://moonzip.kr/series/98e35e49-24bf-42ca-b130-d123a59468ca",
    "https://moonzip.kr/series/5cd36ec7-42fe-47d5-a4eb-13d931ad67bf",
    "https://moonzip.kr/series/1de26881-a7a4-49a4-ae01-92166f90be9c",
]
assert len(URLS) == 10 and len(set(URLS)) == 10

async def inspect(tab, page, url):
    started = datetime.now(timezone.utc).isoformat()
    print("MOONZIP_TAB_START", json.dumps({"tab":tab,"url":url,"utc":started}), flush=True)
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=35000)
        await page.wait_for_timeout(1400)
        extracted = await page.evaluate("""() => ({
           title: document.title,
           heading: document.querySelector('h1')?.textContent?.trim() || '',
           body_excerpt: (document.body?.innerText || '').slice(0,3500),
           links: Array.from(document.querySelectorAll('a[href]')).map(a=>({
             text: (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0,180),
             href: a.href
           })).filter(a=>a.href.includes('/series/') || a.href.includes('/books/')).slice(0,1000),
           images: Array.from(document.querySelectorAll('img')).map(i=>({
             alt: i.alt || '',
             src: i.getAttribute('src') || '',
             currentSrc: i.currentSrc || '',
             srcset: (i.getAttribute('srcset')||'').slice(0,1400)
           })).slice(0,200),
           jsonld: Array.from(document.querySelectorAll('script[type="application/ld+json"]'))
                    .map(s=>s.textContent.slice(0,5000)).slice(0,8)
        })""")
        result = dict(extracted,
             source_url=url, final_url=page.url,
             http_status=response.status if response else None,
             tab=tab, started_at=started,
             finished_at=datetime.now(timezone.utc).isoformat())
        print("MOONZIP_TAB_RESULT", json.dumps({
            "tab":tab,"status":result["http_status"],"url":url,
            "series_urls":sum('/series/' in x['href'] for x in result["links"]),
            "book_urls":sum('/books/' in x['href'] for x in result["links"]),
            "cover_image_links":len(result["images"]),
            "heading":result["heading"]
        },ensure_ascii=True),flush=True)
        return result
    except Exception as exc:
        result={"source_url":url,"tab":tab,"started_at":started,
                "finished_at":datetime.now(timezone.utc).isoformat(),
                "error":f"{type(exc).__name__}: {str(exc)[:400]}"}
        print("MOONZIP_TAB_FAILURE",json.dumps(result,ensure_ascii=True),flush=True)
        return result

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=False)
        context = await browser.new_context(locale="ko-KR", viewport={"width":1366,"height":850})
        try:
            # All TEN tabs are opened BEFORE any page is navigated.
            pages = await asyncio.gather(*(context.new_page() for _ in range(10)))
            print("MOONZIP_10_TABS_OPEN",json.dumps({
                "count":len(pages),"at":datetime.now(timezone.utc).isoformat()
            }),flush=True)
            # Start all ten navigations simultaneously. No sequential await inside this loop.
            results = await asyncio.gather(
                *(inspect(i+1,pages[i],URLS[i]) for i in range(10)))
            try:
                await asyncio.wait_for(asyncio.gather(
                    *(page.close(run_before_unload=False) for page in pages)),timeout=25)
            except Exception:
                pass
        finally:
            await context.close()
            await browser.close()
    (OUT/"probe.json").write_text(
         json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    series={x["href"] for r in results for x in r.get("links",[]) if "/series/" in x.get("href","")}
    books={x["href"] for r in results for x in r.get("links",[]) if "/books/" in x.get("href","")}
    status=sum(r.get("http_status")==200 for r in results)
    print("MOONZIP_PROBE_SUMMARY", json.dumps({
        "pages":len(results),"successful_pages":status,"tabs_opened_simultaneously":10,
        "series_links":len(series),"book_links":len(books),
        "cover_image_urls":sum(len(r.get("images",[])) for r in results),
        "downloaded_images":0
    },ensure_ascii=True),flush=True)
    if status<8:
        raise SystemExit("Under eight of ten Moonzip pages succeeded")

if __name__ == "__main__":
    asyncio.run(main())
