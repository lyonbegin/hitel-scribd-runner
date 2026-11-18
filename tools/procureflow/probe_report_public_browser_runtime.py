#!/usr/bin/env python3
"""Check whether normal anonymous datahub browser can invoke public report UI.

This intentionally never reads or exposes cookies, guest user keys, tokens,
credentials or authorization headers. It does not log in or fetch MSTR tokens.
"""
import asyncio,hashlib,json,os
from pathlib import Path
from playwright.async_api import async_playwright
HOST="https://data.g2b.go.kr/"
URL=HOST+"link/AISC001_01/?reptNm=UI-ADOXAA-038R"
OUT=Path(os.getenv("RUNNER_TEMP","."))/"pf2-public-report-browser"
OUT.mkdir(parents=True,exist_ok=True)
async def main():
 result={"url":URL,"public_only":True,"report_rows":0}
 async with async_playwright() as p:
  br=await p.chromium.launch(channel="chrome",headless=False)
  ctx=await br.new_context(locale="ko-KR",timezone_id="Asia/Seoul")
  try:
   pg=await ctx.new_page()
   req_paths=[]
   def resp_callback(resp):
    if len(req_paths)>=400:return
    # Ignore authentication/cookie URL paths and query strings.
    if "/auth" in resp.url.lower() or "/sso" in resp.url.lower() or "key" in resp.url.lower():return
    from urllib.parse import urlsplit
    u=urlsplit(resp.url)
    req_paths.append({"host":u.hostname,"path":u.path,
                      "method":resp.request.method,"http":resp.status,
                      "mime":resp.headers.get("content-type","").split(";")[0]})
   pg.on("response",resp_callback)
   h=await pg.goto(URL,wait_until="domcontentloaded",timeout=36000)
   await pg.wait_for_timeout(6500)
   result["home_http"]=h.status if h else None
   result["runtime"]=await pg.evaluate("""() => ({
     bodyChildren:document.body?.childElementCount||0,
     window_mstr:typeof window.mstr,
     window_com:typeof window.com,
     window_prcm:typeof window.prcm,
     window_websquare:typeof window.WebSquare,
     window_MicroStrategy:typeof window.microstrategy,
     scripts:[...document.scripts].map(s=>s.getAttribute('src')).filter(Boolean).slice(0,60)
   })""")
   result["observed_request_paths"]=[x for x in req_paths if
       not x["path"].endswith((".js",".css",".png",".jpg",".svg",".ico",".woff",".woff2"))][:75]
  finally:await ctx.close();await br.close()
 (OUT/"report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
 print("PF2_REPORT_PUBLIC_BROWSER_READY",json.dumps(result,ensure_ascii=False),flush=True)
if __name__=="__main__":asyncio.run(main())
