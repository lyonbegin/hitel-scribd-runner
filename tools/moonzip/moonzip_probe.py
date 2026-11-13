#!/usr/bin/env python3
"""Moonzip public catalogue probe: URLs and cover IMAGE LINKS only, never image downloads."""
import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright

OUT=Path("moonzip-results")
OUT.mkdir(parents=True, exist_ok=True)
URLS=[
 "https://moonzip.kr/search",
 "https://moonzip.kr/series/c335a5f7-3f6b-438a-8442-ba535c2e5918",
 "https://moonzip.kr/series/2b6719bf-f758-4497-9b41-81301ce9c85c",
 "https://moonzip.kr/series/43567ca7-2583-49fb-b629-786c360144e1",
 "https://moonzip.kr/books/c66dbaa8-9a88-4394-828c-13a5e71486f5",
]
async def inspect(page, url):
    response=await page.goto(url, wait_until="domcontentloaded", timeout=35000)
    await page.wait_for_timeout(2000)
    try:
        await page.locator("body").press("End", timeout=1600)
        await page.wait_for_timeout(700)
    except Exception:
        pass
    parsed=await page.evaluate("""() => ({
      title: document.title,
      pageTitle: document.querySelector('h1')?.textContent?.trim() || '',
      body: (document.body?.innerText || '').slice(0,12000),
      links: Array.from(document.querySelectorAll('a[href]')).map(a=>({
        text:(a.innerText || a.getAttribute('aria-label') || '').trim().slice(0,170),
        href:a.href
      })).filter(a=>a.href.includes('/series/') || a.href.includes('/books/') || /next|page|more/.test(a.href)).slice(0,1000),
      images: Array.from(document.querySelectorAll('img')).map(i=>({
        alt: i.alt || '',
        src: i.getAttribute('src') || '',
        currentSrc: i.currentSrc || '',
        srcset: (i.getAttribute('srcset')||'').slice(0,900),
        outer: i.outerHTML.slice(0,500)
      })).slice(0,70),
      ogImage:document.querySelector('meta[property="og:image"]')?.content || '',
      jsonld:Array.from(document.querySelectorAll('script[type="application/ld+json"]')).map(i=>i.textContent.slice(0,2000)).slice(0,6)
    })""")
    parsed.update({"source_url":url,"final_url":page.url,"http_status":response.status if response else None})
    print("MOONZIP_PROBE",json.dumps({k:(v if k not in ("body","images","links") else (v[:450] if isinstance(v,str) else v[:5])) for k,v in parsed.items()},ensure_ascii=False),flush=True)
    return parsed

async def main():
    out=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(channel="chrome",headless=False)
        context=await browser.new_context(locale="ko-KR",viewport={"width":1366,"height":850})
        try:
            for index,url in enumerate(URLS):
                page=await context.new_page()
                try:
                    result=await asyncio.wait_for(inspect(page,url),timeout=65)
                    out.append(result)
                except Exception as exc:
                    out.append({"source_url":url,"error":f"{type(exc).__name__}: {str(exc)[:350]}"})
                    print("MOONZIP_PROBE_ERROR",url,type(exc).__name__,str(exc)[:250],flush=True)
                finally:
                    try: await page.close()
                    except Exception: pass
                await asyncio.sleep(1.2)
        finally:
            await context.close()
            await browser.close()
    (OUT/"probe.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    series={x["href"] for r in out for x in r.get("links",[]) if "/series/" in x.get("href","")}
    books={x["href"] for r in out for x in r.get("links",[]) if "/books/" in x.get("href","")}
    covers=sum(len(r.get("images",[])) for r in out)
    print("MOONZIP_PROBE_SUMMARY",json.dumps({"pages":len(out),"series_links":len(series),"book_links":len(books),"image_tags":covers,"downloaded_images":0},ensure_ascii=False),flush=True)

if __name__=="__main__":
    asyncio.run(main())
