#!/usr/bin/env python3
"""Inspect interactive public Npay Land map UI in existing Windows PC Chrome."""
import asyncio, json, re
from datetime import datetime, timezone
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
 out=Path("naver-fin-dom-results");out.mkdir(exist_ok=True)
 data={"timestamp_utc":datetime.now(timezone.utc).isoformat(),"events":[],"requests":[]}
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel="chrome",headless=True,args=["--no-sandbox"])
  context=await browser.new_context(viewport={"width":1600,"height":1000}, locale="ko-KR")
  page=await context.new_page()
  def record(resp):
   u=resp.url
   if "land.naver.com" in u and len(data["requests"])<100:
    data["requests"].append({"url":u[:400],"status":resp.status,
      "type":(resp.headers.get("content-type") or "")[:60]})
  page.on("response",record)
  try:
   response=await page.goto("https://fin.land.naver.com/map",
                             wait_until="commit",timeout=18000)
   data["http_status"]=response.status if response else None
   for stage,wait in [("initial",7000),("settled",4500)]:
    await page.wait_for_timeout(wait)
    result=await page.evaluate("""() => ({
      href: location.href, state: document.readyState, title: document.title,
      body: (document.body?.innerText || '').slice(0,7000),
      inputs: [...document.querySelectorAll('input')].slice(0,45).map(e=>({
        placeholder:e.placeholder, id:e.id, type:e.type, value:e.value,
        className:e.className, html:e.outerHTML.slice(0,400)})),
      buttons: [...document.querySelectorAll('button')].slice(0,85).map(e=>({
        label:(e.innerText||e.ariaLabel||'').trim().slice(0,95),
        className:e.className, title:e.title})),
      anchors: [...document.querySelectorAll('a[href]')].slice(0,65).map(e=>({
        text:(e.innerText||'').trim().slice(0,80),href:e.href.slice(0,250)}))
     })""")
    result["stage"]=stage
    data["events"].append(result)
    print("FIN_UI",json.dumps({k:v for k,v in result.items() if k not in
     ("anchors","buttons","inputs")},ensure_ascii=True)[:3600],flush=True)
    print("FIN_CONTROLS",json.dumps({"stage":stage,"inputs":result["inputs"][:10],
       "buttons":result["buttons"][:30]},ensure_ascii=True)[:6000],flush=True)
   search=page.locator("input[placeholder*='단지'],input[placeholder*='주소'],input[placeholder*='지역']").first
   if await search.count():
    await search.fill("홍대입구역",timeout=6000)
    await search.press("Enter",timeout=5000)
    await page.wait_for_timeout(4500)
    data["events"].append({"stage":"search_hongdae","url":page.url,
     "body":await page.evaluate("document.body.innerText.slice(0,7000)")})
    print("FIN_SEARCH",json.dumps(data["events"][-1],ensure_ascii=True)[:4400],flush=True)
   else:
    print("FIN_SEARCH","missing search input",flush=True)
   try: await page.screenshot(path=str(out/"map.png"),timeout=5000,animations="disabled")
   except Exception as e: data["screenshot_error"]=str(e)[:300]
  except Exception as e: data["error"]=f"{type(e).__name__}: {e}"[:700]
  finally:
   print("FIN_NETWORK",json.dumps(data["requests"][-30:],ensure_ascii=True)[:6000],flush=True)
   (out/"ui.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
   await browser.close()
if __name__=="__main__":asyncio.run(main())
