#!/usr/bin/env python3
"""Read-only Naver Pay real-estate Chrome reconnaissance. No credentials, no bypass."""
import argparse
import asyncio
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# Centres are tourist pedestrian approaches, NOT property addresses.
AREAS = [
    ("jongno5_gwangjang", 37.57035, 127.00088, "광장시장 종로5가역 보행로"),
    ("dongdaemun_dongmyo", 37.57141, 127.01156, "동대문 동묘앞역 보행로"),
    ("hongdae_exit9", 37.55572, 126.92364, "홍대입구역 9번 출구 보행로"),
    ("yeonnam_entrance", 37.56140, 126.92570, "연남동 연트럴파크 진입로"),
    ("seongsu_exit", 37.54458, 127.05572, "성수역 연무장길 초입"),
    ("euljiro3", 37.56623, 126.99103, "을지로3가 인쇄골목 주요 동선"),
    ("anguk_exit", 37.57630, 126.98540, "안국역 북촌 진입로"),
]
FIELDS = ["area", "source_page", "article_no", "article_url", "type_text",
          "price_text", "floor_text", "area_text", "raw_text",
          "status", "verification"]

def compact(s, limit=600):
    return re.sub(r"\s+", " ", str(s or "")).strip()[:limit]

async def main(args):
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    summary = {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
               "purpose": "public listings only, no login", "areas": [], "items": 0}
    rows = []
    async with async_playwright() as p:
        launch_err = None
        try:
            browser = await p.chromium.launch(channel="chrome", headless=True,
                                              args=["--no-sandbox"])
            summary["browser"] = "Google Chrome"
        except Exception as exc:
            launch_err = compact(exc, 350)
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            summary["browser"] = "Playwright Chromium fallback"
        if launch_err: summary["chrome_launch_error"] = launch_err
        context = await browser.new_context(locale="ko-KR", viewport={"width": 1536, "height": 1024},
                                             timezone_id="Asia/Seoul")
        for slug, lat, lng, desc in AREAS[:args.limit]:
            # Legacy map contains explicit property and trade-type filters; rendered site may redirect.
            url = (f"https://new.land.naver.com/houses?ms={lat},{lng},17"
                   "&a=DDDGG:JWJT:SGJT:HOJT:VL&b=B2")
            page = await context.new_page()
            area = {"slug": slug, "description": desc, "source_url": url,
                    "status": "not_started", "listing_cards": 0, "article_links": 0,
                    "network_responses": []}
            captures = []
            def on_response(response):
                u = response.url
                if "land.naver.com" in u and ("/api/" in u or "/front-api/" in u or
                                                 "article" in u or "listing" in u):
                    if len(captures) < 60:
                        captures.append({"url": u[:500], "status": response.status,
                                         "content_type": (response.headers.get("content-type") or "")[:100]})
            page.on("response", on_response)
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=32000)
                await page.wait_for_timeout(3500)
                area["http_status"] = response.status if response else None
                area["final_url"] = page.url
                area["title"] = compact(await page.title(), 180)
                area["status"] = "loaded"
                # Allow the map's scrollable listing panels to reveal already publicly visible cards.
                for selector in [".item_inner", "[class*='item_inner']", "[class*='item_list']",
                                 "[class*='ArticleList']", "[class*='article_list']"]:
                    try:
                        count = await page.locator(selector).count()
                        if count:
                            area["matched_selector"] = selector
                            area["listing_cards"] = count
                            break
                    except Exception:
                        continue
                page_text = await page.locator("body").inner_text(timeout=12000)
                area["body_excerpt"] = compact(page_text, 3800)
                if any(word in page_text.lower() for word in ["captcha", "비정상적인 접근", "접근이 제한",
                                                            "비정상적인 트래픽", "서비스를 이용할 수"]):
                    area["status"] = "access_challenge"
                if len(page_text.strip()) < 60:
                    area["status"] = "page_empty_or_script_failed"
                try:
                    dom_items = await page.locator(".item_inner").all_inner_texts()
                except Exception:
                    dom_items = []
                for item in dom_items[:80]:
                    txt = compact(item, 700)
                    if txt:
                        rows.append({"area": slug, "source_page": page.url,
                                     "article_no": "", "article_url": "", "type_text": "",
                                     "price_text": "", "floor_text": "", "area_text": "",
                                     "raw_text": txt, "status": "visible_card",
                                     "verification": "study_only_not_deed_verified"})
                links = await page.evaluate("""() => [...document.querySelectorAll('a[href]')]
                    .map(a => ({text: (a.innerText || '').trim().slice(0,250), href:a.href}))
                    .filter(x => /articles\\/\\d+/.test(x.href)).slice(0,100)""")
                for l in links:
                    match = re.search(r"/articles/(\d+)", l["href"])
                    no = match.group(1) if match else ""
                    rows.append({"area": slug, "source_page": page.url, "article_no": no,
                                 "article_url": l["href"], "type_text": "",
                                 "price_text": "", "floor_text": "", "area_text": "",
                                 "raw_text": compact(l["text"], 350), "status": "visible_link",
                                 "verification": "study_only_not_deed_verified"})
                area["article_links"] = len(links)
                if not rows and "매물" not in page_text:
                    area["status"] = "ui_unavailable"
                # Diagnostics: visible UI and public network endpoints, not copied session data.
                area["network_responses"] = captures
                (out / f"{slug}.txt").write_text(page_text[:20000], encoding="utf-8")
                await page.screenshot(path=str(out / f"{slug}.png"), full_page=False, timeout=15000)
            except Exception as exc:
                area["status"] = "error"
                area["error"] = compact(f"{type(exc).__name__}: {exc}", 500)
                try:
                    await page.screenshot(path=str(out / f"{slug}.png"), full_page=False, timeout=9000)
                except Exception: pass
            finally:
                summary["areas"].append(area)
                print("AREA_RESULT", json.dumps({k:v for k,v in area.items() if k not in
                       ("body_excerpt", "network_responses")}, ensure_ascii=False), flush=True)
                await page.close()
                await asyncio.sleep(1)
        await browser.close()
    with (out / "cards.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w=csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    summary["items"] = len(rows)
    summary["needs_manual_or_official_verification"] = (
        "Article cards do not establish deed zoning, exact shop frontage or SH rental support eligibility")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    print("NAVER_FINAL", json.dumps({"browser":summary["browser"],"areas":len(summary["areas"]),
                                      "rows":len(rows),"statuses":[a["status"] for a in summary["areas"]]},
                                      ensure_ascii=False), flush=True)
    return 0

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--out", default="naver-land-results")
    parser.add_argument("--limit", type=int, default=6)
    args=parser.parse_args()
    raise SystemExit(asyncio.run(main(args)))
