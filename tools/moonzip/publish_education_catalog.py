#!/usr/bin/env python3
"""Import a verified one-time catalog snapshot into the HITEL-owned public data folder.

Source archive is an earlier public GitHub Actions artifact; the resulting data is
first-party catalog storage for the HITEL UI. Scraped ratings/reviews are excluded.
"""
import io
import json
import os
import re
import subprocess
import urllib.request
import zipfile
from pathlib import Path

OWNER="lyonbegin"
SOURCE_REPO="hitel-scribd-runner"
ARTIFACT_ID="14051743250"
ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/"published"/"education-catalog-v2"
URL=f"https://api.github.com/repos/{OWNER}/{SOURCE_REPO}/actions/artifacts/{ARTIFACT_ID}/zip"
TOKEN=os.getenv("GH_TOKEN","")
headers={
 "Accept":"application/vnd.github+json",
 "X-GitHub-Api-Version":"2022-11-28",
 "User-Agent":"HITEL-education-catalog-import"
}
if TOKEN:
 headers["Authorization"]=f"Bearer {TOKEN}"
print("IMPORT_STEP: fetching existing verified metadata artifact",flush=True)
req=urllib.request.Request(URL,headers=headers)
try:
 with urllib.request.urlopen(req,timeout=60) as res:
  raw=res.read()
except Exception as exc:
 raise SystemExit(f"CATALOG_IMPORT_DOWNLOAD_FAILED: {type(exc).__name__}: {exc}")
if raw[:2]!=b"PK":
 raise SystemExit(f"CATALOG_IMPORT_INVALID_ARCHIVE: bytes={len(raw)}, first={raw[:20]!r}")
with zipfile.ZipFile(io.BytesIO(raw)) as zf:
 series_data=json.loads(zf.read("moonzip-catalog-results/series.json"))
 books_data=json.loads(zf.read("moonzip-catalog-results/books.json"))
 if len(series_data)!=370 or len(books_data)!=1739:
  raise SystemExit(f"CATALOG_IMPORT_COUNT_MISMATCH: series={len(series_data)} books={len(books_data)}")
 series=[]
 for sid,s in series_data.items():
  series.append({
   "id":sid, "name":s.get("series_name") or "",
   "cover":s.get("series_cover_image_url") or "",
   "external_url":s.get("series_url") or "",
   "book_count":len(s.get("book_ids") or []),
   "collection_complete":bool(s.get("complete")),
   "listed_count":s.get("site_book_count_label")
  })
 books=[]
 for bid,b in books_data.items():
  books.append({
   "id":bid,"series_id":b.get("series_id") or "",
   "name":b.get("book_title") or "",
   "cover":b.get("cover_image_url") or "",
   "publisher":b.get("publisher") or "",
   "isbn":b.get("isbn") or "",
   "author":b.get("author") or "",
   "published_at":b.get("date_published") or "",
   "external_url":b.get("book_url") or "",
   "answer_or_explanation":bool(b.get("answer_or_explanation")),
   "verified_metadata":bool(b.get("detail_checked"))
  })
 if len({s["id"] for s in series})!=370 or len({b["id"] for b in books})!=1739:
  raise SystemExit("CATALOG_IMPORT_DUPLICATE_IDS")
 if sum(bool(b["cover"]) for b in books)!=1739:
  raise SystemExit("CATALOG_IMPORT_MISSING_COVERS")
 if any(b["series_id"] not in series_data for b in books):
  raise SystemExit("CATALOG_IMPORT_DANGLING_SERIES")
TARGET.mkdir(parents=True,exist_ok=True)
(TARGET/"series.json").write_text(json.dumps(series,ensure_ascii=False,separators=(",",":")),encoding="utf8")
(TARGET/"books.json").write_text(json.dumps(books,ensure_ascii=False,separators=(",",":")),encoding="utf8")
manifest={
 "schema":"hitel-education-catalog-v2",
 "series":len(series),
 "books":len(books),
 "complete_series":sum(s["collection_complete"] for s in series),
 "empty_series":sum(s["book_count"]==0 for s in series),
 "cover_urls":sum(bool(b["cover"]) for b in books),
 "original_book_files":0,
 "source_record":"existing verified catalog metadata snapshot",
 "import_status":"validated",
 "detail_notice":"Data stores bibliographic metadata and public covers, not the contents of textbooks"
}
(TARGET/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf8")
print("CATALOG_IMPORT_OK "+json.dumps(manifest,ensure_ascii=False),flush=True)
