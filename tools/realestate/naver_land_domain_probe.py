#!/usr/bin/env python3
"""Probe supported public Naver Pay Land entrypoints using actual Chrome."""
import asyncio, json, re
from datetime import datetime, timezone
from pathlib import Path
from playwright.async_api import async_playwright

URLS = [
 ("land_home", "https://land.naver.com/"),
 ("fin_map", "https://fin.land.naver.com/map"),
 ("fin_home", "https://fin.land.naver.com/"),
 ("mobile", "https://m.land.naver.com/"),
 ("legacy", "https://new.land.naver.com/houses?ms=37.57035,127.00088,16&a=DDDGG:JWJT:SGJT:HOJT:VL&b=B2"),
]
async def main():
 out=Path("naver-domain-results");out.mkdir(exist_ok=True)
 results=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
  context=await browser.new_context(locale="ko-KR", viewport={"width":1440,"height":900})
  for key,url in URLS:
   page=await context.new_page()
   r={"key":key,"url":url,"timestamp_utc":datetime.now(timezone.utc).isoformat()}
   errors=[]
   page.on("requestfailed",lambda req: errors.append({"url":req.url[:200],"failure":req.failure}) if len(errors)<10 else None)
   try:
    resp=await page.goto(url,wait_until="commit",timeout=12000)
    r["http_status"]=resp.status if resp else None
    r["final_url"]=page.url
    await page.wait_for_timeout(3000)
    r["title"]=await page.title()
    txt=await page.locator("body").inner_text(timeout=5000)
    r["body_chars"]=len(txt)
    r["excerpt"]=re.sub(r"\s+"," ",txt)[:900]
    await page.screenshot(path=str(out/(key+".png")),timeout=9000)
    r["status"]="loaded" if len(txt)>60 else "empty_body"
   except Exception as exc:
    r["status"]="error"
    r["error"]=f"{type(exc).__name__}: {str(exc)}"[:500]
    try: await page.screenshot(path=str(out/(key+".png")),timeout=3000)
    except Exception: pass
   r["failed_requests"]=errors
   results.append(r)
   print("NAVER_DOMAIN",json.dumps(r,ensure_ascii=False),flush=True)
   await page.close()
   await asyncio.sleep(0.6)
  await browser.close()
 (out/"summary.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__": asyncio.run(main())
