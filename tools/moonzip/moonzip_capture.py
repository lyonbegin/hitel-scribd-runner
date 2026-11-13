#!/usr/bin/env python3
"""Moonzip site adapter / proof of preservation. Uses the installed local Chrome.

Public, allowed series/book pages only. Do not bypass login, paywalls or challenges.
Never deletes prior page screenshots, image assets, metadata, or checkpoints.
"""
import argparse
import asyncio
import csv
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote
from urllib.robotparser import RobotFileParser

BASE = "https://moonzip.kr"
SEEDS = [
    "https://moonzip.kr/series/c335a5f7-3f6b-438a-8442-ba535c2e5918",  # 쎈
    "https://moonzip.kr/series/46c7c368-0823-4f2f-96d3-c387fe30a539",  # N기출 3점 집중
    "https://moonzip.kr/series/43567ca7-2583-49fb-b629-786c360144e1",  # 블랙라벨
]
AGENT = "HITEL-Public-Catalog-Review/1.0"
IMAGE_EXT = {"image/png":".png","image/jpeg":".jpg","image/webp":".webp",
             "image/gif":".gif","image/avif":".avif","image/svg+xml":".svg"}
TYPE_RX = re.compile(r"^/(series|books)/([0-9a-f]{8}-[0-9a-f-]{27,36})/?$", re.I)


def iso():
    return datetime.now(timezone.utc).isoformat()


def classify(url):
    p = urlparse(url)
    if p.scheme != "https" or p.netloc not in ("moonzip.kr", "www.moonzip.kr"):
        return None
    m = TYPE_RX.match(p.path)
    return (m.group(1).lower(), m.group(2)) if m else None


def normalize(url):
    p = urlparse(urljoin(BASE, url))
    if p.netloc.lower() not in ("moonzip.kr","www.moonzip.kr") or p.scheme != "https":
        return ""
    return p._replace(query="",fragment="").geturl().rstrip("/")


def hashfile(data):
    return hashlib.sha256(data).hexdigest()


def atomic_json(path, item):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def append_jsonl(path, item):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


async def robot_policy(context):
    rp = RobotFileParser()
    url=BASE+"/robots.txt"
    try:
        response=await context.request.get(url, timeout=10000)
        if response.status == 200:
            text=await response.text()
            rp.parse(text.splitlines())
            print("MOONZIP_ROBOTS", json.dumps({"status":200,"bytes":len(text)}),flush=True)
            return rp
        print("MOONZIP_ROBOTS",json.dumps({"status":response.status}),flush=True)
    except Exception as exc:
        print("MOONZIP_ROBOTS_ERROR",str(exc)[:200],flush=True)
    return None


def allowed(robots, url):
    return robots is None or robots.can_fetch(AGENT,url)


async def save_image(context, output, url, robots):
    if not url.startswith(("https://","http://")):
        return {"url":url,"status":"non_http"}
    if not allowed(robots,url):
        return {"url":url,"status":"robots_disallowed"}
    try:
        response=await context.request.get(url,timeout=20000)
        ct=response.headers.get("content-type","").split(";")[0].lower()
        if not response.ok or not ct.startswith("image/"):
            return {"url":url,"status":f"http_{response.status}","content_type":ct}
        data=await response.body()
        sha=hashfile(data)
        ext=IMAGE_EXT.get(ct,Path(urlparse(url).path).suffix.lower() or ".bin")
        if len(ext)>8 or "/" in ext: ext=".bin"
        dest=output/"assets"/(sha+ext)
        if not dest.exists():
            dest.write_bytes(data)
        return {"url":url,"status":"saved","sha256":sha,"file":str(dest),
                "bytes":len(data),"content_type":ct}
    except Exception as exc:
        return {"url":url,"status":"error","error":type(exc).__name__+":"+str(exc)[:220]}


async def fetch_page(context, url, output, robots, pause):
    kind_id=classify(url)
    if not kind_id:
        return {"url":url,"status":"unsupported_url"}
    kind,item_id=kind_id
    path=output/"pages"/kind/item_id
    path.mkdir(parents=True,exist_ok=True)
    metadata=path/"metadata.json"
    if metadata.exists():
        prev=json.loads(metadata.read_text(encoding="utf-8"))
        if prev.get("status")=="saved" and prev.get("images_saved",0)>=0:
            print("MOONZIP_ALREADY_SAVED",json.dumps({"url":url}),flush=True)
            return prev
    if not allowed(robots,url):
        return {"url":url,"status":"robots_disallowed"}
    page=await context.new_page()
    info={"kind":kind,"item_id":item_id,"url":url,"status":"error","utc":iso()}
    try:
        response=await page.goto(url,wait_until="domcontentloaded",timeout=30000)
        info["http_status"]=response.status if response else None
        await page.wait_for_timeout(1400)
        info["final_url"]=page.url
        info["title"]=await page.title()
        info["h1"]=await page.locator("h1").all_inner_texts()
        # Scroll to resolve lazy-loaded cover photographs, then return to top.
        height=await page.evaluate("Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
        info["scroll_height"]=height
        for y in range(0,min(height,30000),900):
            await page.evaluate("(y) => window.scrollTo(0,y)",y)
            await page.wait_for_timeout(80)
        info["scroll_coverage_complete"]=height<=30000
        await page.evaluate("window.scrollTo(0,0)")
        await page.wait_for_timeout(250)
        info["body_excerpt"]=(await page.locator("body").inner_text(timeout=7000))[:10000]
        info["links"]=await page.locator("a[href]").evaluate_all(
            """nodes => [...new Set(nodes.map(n => n.href).filter(Boolean))]""")
        # Preserve all HTTP image URLs exposed by page IMG, CSS background and picture/source.
        raw_imgs=await page.evaluate("""() => {
          const rows=[];
          for (const n of document.querySelectorAll('img')) {
            if(n.currentSrc) rows.push({url:n.currentSrc,alt:n.alt||'',source:'img'});
            else if(n.src) rows.push({url:n.src,alt:n.alt||'',source:'img'});
            if(n.srcset) for(const part of n.srcset.split(',')){
              const u=part.trim().split(/\\s+/)[0]; if(u) rows.push({url:u,alt:n.alt||'',source:'srcset'});
            }
          }
          for (const n of document.querySelectorAll('source[srcset]')) {
             for(const part of n.srcset.split(',')){
               const u=part.trim().split(/\\s+/)[0];if(u)rows.push({url:u,alt:'',source:'source'});
             }
          }
          for(const n of document.querySelectorAll('*')) {
            const bg=getComputedStyle(n).backgroundImage;
            if(bg&&bg!=='none') for(const m of bg.matchAll(/url\\(["']?([^)"']+)["']?\\)/g))
              rows.push({url:m[1],alt:'',source:'background'});
          }
          return rows;
        }""")
        found={}
        for candidate in raw_imgs:
            u=urljoin(url,candidate["url"])
            if u not in found: found[u]=candidate
        image_rows=[]
        for u,v in found.items():
            item=await save_image(context,output,u,robots)
            item["source"]=v.get("source","")
            item["alt"]=v.get("alt","")
            image_rows.append(item)
            await asyncio.sleep(pause)
        info["images"]=image_rows
        info["images_saved"]=sum(x.get("status")=="saved" for x in image_rows)
        info["images_failed"]=sum(x.get("status") in ("error","robots_disallowed") or x.get("status","").startswith("http_") for x in image_rows)
        # Required preservation: full-page PNG and tile fallback if oversized.
        try:
            shot=path/"full_page.png"
            await page.screenshot(path=str(shot),full_page=True,timeout=30000,animations="disabled")
            info["page_images"]=[str(shot)]
            info["screenshot_complete"]=True
        except Exception as exc:
            info["page_images"]=[]
            info["screenshot_complete"]=False
            info["screenshot_error"]=f"{type(exc).__name__}:{exc}"[:250]
            viewport=await page.evaluate("window.innerHeight")
            for idx,y in enumerate(range(0,min(height,30000),max(300,viewport-60))):
                await page.evaluate("(y) => window.scrollTo(0,y)",y)
                await page.wait_for_timeout(120)
                shot=path/f"tile_{idx:03d}.png"
                try:
                    await page.screenshot(path=str(shot),full_page=False,timeout=14000)
                    info["page_images"].append(str(shot))
                except Exception as e:
                    info.setdefault("failed_tiles",[]).append({"y":y,"error":str(e)[:200]})
        info["status"]="saved" if (info["page_images"] and info["http_status"] and info["http_status"]<400) else "partial"
    except Exception as exc:
        info["error"]=f"{type(exc).__name__}:{exc}"[:600]
    finally:
        try: await page.close()
        except Exception: pass
    atomic_json(metadata,info)
    append_jsonl(output/"page_manifest.jsonl",{
        k:info.get(k) for k in ("kind","item_id","url","status","http_status","h1",
                                 "images_saved","images_failed","page_images","utc")})
    print("MOONZIP_PAGE_RESULT",json.dumps({k:info.get(k) for k in
          ("kind","item_id","status","images_saved","images_failed","screenshot_complete")},ensure_ascii=False),flush=True)
    return info


async def main(args):
    from playwright.async_api import async_playwright
    output=Path(args.out).expanduser().resolve()
    output.mkdir(parents=True,exist_ok=True)
    (output/"assets").mkdir(exist_ok=True)
    if args.phase=="smoke":
        seeds=SEEDS[:args.series_limit]
    else:
        raise ValueError("Bulk discovery not yet validated. Run smoke and inspect real link inventory.")
    async with async_playwright() as p:
        browser=await p.chromium.launch(channel="chrome",headless=args.headless)
        context=await browser.new_context(locale="ko-KR",viewport={"width":1366,"height":900})
        robots=await robot_policy(context)
        summary={"phase":args.phase,"started":iso(),"output":str(output),
                 "series_requested":len(seeds),"books_requested_limit":args.book_limit,"pages":[]}
        booklinks=[]
        for url in seeds:
            item=await fetch_page(context,url,output,robots,args.pause)
            summary["pages"].append({"url":url,"status":item.get("status")})
            for href in item.get("links",[]):
                normalized=normalize(href)
                kind_id=classify(normalized)
                if kind_id and kind_id[0]=="books" and normalized not in booklinks:
                    booklinks.append(normalized)
        # If the series presents the rest of the books through a UI route not normal anchors,
        # the probe records zero discovered links; never invent book pages.
        summary["book_links_discovered"]=len(booklinks)
        summary["sampled_books"]=booklinks[:args.book_limit]
        for url in booklinks[:args.book_limit]:
            item=await fetch_page(context,url,output,robots,args.pause)
            summary["pages"].append({"url":url,"status":item.get("status")})
        summary["completed"]=iso()
        summary["pages_saved"]=sum(r["status"]=="saved" for r in summary["pages"])
        summary["pages_requested"]=len(summary["pages"])
        summary["status"]="success" if summary["pages_saved"]>=len(seeds) and summary["pages_saved"]==summary["pages_requested"] else "needs_review"
        atomic_json(output/"smoke_summary.json",summary)
        print("MOONZIP_SMOKE_SUMMARY",json.dumps(summary,ensure_ascii=False),flush=True)
        await context.close()
        await browser.close()
        if summary["status"]!="success" or summary["book_links_discovered"]==0:
            raise SystemExit("MOONZIP_SMOKE_INCOMPLETE: inspect local pages and DOM link inventory")
    return 0


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--phase",choices=["smoke"],default="smoke")
    parser.add_argument("--out",required=True)
    parser.add_argument("--series-limit",type=int,default=3)
    parser.add_argument("--book-limit",type=int,default=10)
    parser.add_argument("--pause",type=float,default=0.10)
    parser.add_argument("--headless",action="store_true")
    args=parser.parse_args()
    if not 1<=args.series_limit<=3 or not 0<=args.book_limit<=25 or args.pause<0:
        parser.error("Out of range")
    raise SystemExit(asyncio.run(main(args)))
