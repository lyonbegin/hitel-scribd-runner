#!/usr/bin/env python3
"""Validate that every series lists all its child books. Images are URL strings only."""
import json
from pathlib import Path
p=Path("moonzip-results")
series=json.loads((p/"series.json").read_text(encoding="utf-8"))
books=json.loads((p/"books.json").read_text(encoding="utf-8"))
stats=json.loads((p/"summary.json").read_text(encoding="utf-8"))
bad=[]
for item in series.values():
    expected=item.get("site_book_count_label")
    found=item.get("visible_books_after_expand",0)
    print("MOONZIP_SERIES_QA",item["series_name"],"expected",expected,"found",found)
    if expected is not None and found<expected:bad.append(item["series_id"])
images=list(p.rglob("*.png"))+list(p.rglob("*.jpg"))+list(p.rglob("*.jpeg"))+list(p.rglob("*.webp"))
if images:bad.append("unexpected_image_files")
if stats.get("image_files_downloaded")!=0:bad.append("image_download_policy")
if len(series)<3 or len(books)<12:bad.append("insufficient_pilot_rows")
if sum(bool(x.get("cover_image_url")) for x in books.values())<3:bad.append("missing_book_cover_urls")
if bad:
    print("MOONZIP_PILOT_FAILED",json.dumps(bad))
    raise SystemExit(1)
print("MOONZIP_PILOT_PASSED",json.dumps(stats,ensure_ascii=False))
