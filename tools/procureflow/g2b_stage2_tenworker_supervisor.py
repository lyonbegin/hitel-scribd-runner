#!/usr/bin/env python3
"""Safely resume Stage 2 from immutable original evidence with ten asynchronous workers.

Never performs Stage 1 discovery. Every shard is preserved to a GitHub Release,
with byte hashes, before the supervisor advances to the next shard.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# Windows Python may lack the enterprise/root CA certificates exposed to
# Windows SChannel, even when PowerShell HTTPS succeeds. Inject the system
# trust store; never disable TLS certificate verification.
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    raise RuntimeError("Install truststore to use the Windows OS certificate store")

import g2b_bidder_detail_stage2_recovery as detail

ORIGINAL_RELEASE = "procureflow-stage2-evidence-43553991301"
TOTAL_NOTICES = 930379
FIRST_OFFSET = 100
SHARD_SIZE = 5000
SHARD_COUNT = 187


def log(event, **values):
    print(event, json.dumps(values, sort_keys=True, ensure_ascii=False), flush=True)


def digest_file(path):
    hash_ = hashlib.sha256()
    with open(path, "rb") as file:
        for piece in iter(lambda: file.read(1024 * 1024), b""):
            hash_.update(piece)
    return hash_.hexdigest()


class Github:
    def __init__(self, repo, token):
        if not token:
            raise ValueError("GITHUB_TOKEN must be set; no anonymous changes")
        self.repo = repo
        self.token = token

    def request(self, url, method="GET", payload=None, headers=None, timeout=180):
        data = None
        h = {
            "Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "HITEL-ProcureFlow-Stage2",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            h["Content-Type"] = "application/json"
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read()

    def api(self, path, method="GET", payload=None):
        data = self.request("https://api.github.com/repos/" + self.repo + path,
                            method, payload)
        return json.loads(data) if data else {}

    def release(self, tag, create=False):
        try:
            return self.api("/releases/tags/" + urllib.parse.quote(tag))
        except urllib.error.HTTPError as e:
            if e.code != 404 or not create:
                raise
        return self.api("/releases", method="POST", payload={
            "tag_name": tag, "target_commitish": os.environ["GITHUB_SHA"],
            "name": "G2B bidder detail resumable checkpoints",
            "body": "Verified original queue only. Individual shards may still be incomplete.",
            "draft": False, "prerelease": False
        })

    def assets(self, release):
        # The REST release response can truncate large asset lists.
        url = "/releases/%s/assets?per_page=100" % release["id"]
        items = []
        page = 1
        while True:
            chunk = self.api(url + "&page=" + str(page))
            items.extend(chunk)
            if len(chunk) < 100:
                return items
            page += 1

    def download(self, asset, destination):
        url = asset["browser_download_url"]
        for attempt in range(4):
            try:
                request = urllib.request.Request(
                    url, headers={"User-Agent": "HITEL-ProcureFlow-Stage2",
                                  "Authorization": "Bearer " + self.token})
                with urllib.request.urlopen(request, timeout=180) as response:
                    with destination.open("wb") as stream:
                        shutil.copyfileobj(response, stream, 1024 * 1024)
                expected = asset.get("digest") or ""
                found = digest_file(destination)
                if expected and expected != "sha256:" + found:
                    raise RuntimeError("Release asset digest mismatch: " + asset["name"])
                if destination.stat().st_size != asset["size"]:
                    raise RuntimeError("Release asset size mismatch: " + asset["name"])
                log("ARCHIVE_RESTORED", name=asset["name"],
                    bytes=destination.stat().st_size, sha256=found)
                return
            except (OSError, RuntimeError):
                if attempt == 3:
                    raise
                time.sleep(min(2 ** attempt, 8))

    def upload(self, release, path, name):
        url = ("https://uploads.github.com/repos/" + self.repo +
               "/releases/%s/assets?name=" % release["id"] +
               urllib.parse.quote(name))
        sha = digest_file(path)
        with open(path, "rb") as stream:
            body = stream.read()
        # Individual compressed shard files stay much smaller than the 2GB release limit.
        request = urllib.request.Request(
            url, data=body, method="POST",
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/zip" if name.endswith(".zip")
                                 else "application/json",
                "Content-Length": str(len(body)),
                "User-Agent": "HITEL-ProcureFlow-Stage2",
            })
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=900) as response:
                    result = json.loads(response.read())
                if result.get("size") != len(body):
                    raise RuntimeError("Uploaded byte length mismatch: " + name)
                if result.get("digest") and result["digest"] != "sha256:" + sha:
                    raise RuntimeError("Uploaded SHA256 mismatch: " + name)
                log("CHECKPOINT_STORED", name=name, sha256=sha, bytes=len(body))
                return result
            except (urllib.error.HTTPError, OSError) as e:
                if attempt == 2 or isinstance(e, urllib.error.HTTPError) and e.code in (409, 422):
                    raise
                time.sleep(2 ** attempt)


def safe_extract(zip_path, target):
    target.mkdir(parents=True, exist_ok=True)
    target_root = target.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError("Corrupt ZIP member: " + bad)
        for member in archive.infolist():
            if member.is_dir():
                continue
            candidate = (target / member.filename).resolve()
            if target_root not in candidate.parents:
                raise RuntimeError("Archive attempted unsafe extraction")
            candidate.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as reader, candidate.open("wb") as writer:
                shutil.copyfileobj(reader, writer, 1024 * 1024)


def archive_dir(folder, destination):
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=6,
                         allowZip64=True) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(folder).as_posix())
    if zipfile.ZipFile(destination).testzip() is not None:
        raise RuntimeError("New archive ZIP verification failed")


def select_asset(assets, exact_name):
    return next((x for x in assets if x["name"] == exact_name), None)


def read_original_queue(github, release, folder):
    assets = github.assets(release)
    a = select_asset(assets, "g2b-two-year-notice-index-merged.zip")
    if not a:
        raise RuntimeError("Immutable verified 721-day queue backup not found")
    z = folder / "saved-original-index.zip"
    github.download(a, z)
    index = folder / "historical-index"
    safe_extract(z, index)
    z.unlink()
    candidates = list(index.rglob("notice_queue.csv"))
    covers = list(index.rglob("coverage.json"))
    if len(candidates) != 1 or len(covers) != 1:
        raise RuntimeError("Original index missing/ambiguous")
    coverage = json.loads(covers[0].read_text(encoding="utf-8-sig"))
    if coverage.get("detail_eligible_keys") != TOTAL_NOTICES:
        raise RuntimeError("Source index has different number of eligible keys")
    if coverage.get("days_complete") != 721:
        raise RuntimeError("Only 721 verified dates are allowed")
    queue, _ = detail.load_queue(candidates[0], 0, 0)
    if len(queue) != TOTAL_NOTICES:
        raise RuntimeError("Original queue keys or ordering changed")
    log("EXISTING_INDEX_VERIFIED", eligible=len(queue), verified_days=721,
        unverified_dates_not_queried=10)
    return queue


def choose_segments(github, checkpoint_assets, root, only_unprocessed=False):
    manifests = {}
    counts = {}
    for item in checkpoint_assets:
        name = item["name"]
        if name.startswith("g2b-status-shard-") and name.endswith(".json"):
            # Every run has a unique suffix. Use the latest completed attempt.
            parts = name.removesuffix(".json").split("-")
            try:
                index = int(parts[3])
            except (IndexError, ValueError):
                continue
            counts[index] = counts.get(index, 0) + 1
            previous = manifests.get(index)
            if previous is None or item["created_at"] > previous["created_at"]:
                manifests[index] = item
    # Cover each previously unseen shard before retries. Never re-query
    # a verified complete shard; the release keeps its original evidence.
    absent = [i for i in range(SHARD_COUNT) if i not in manifests]
    if absent:
        return absent, "first_pass", counts
    unresolved = []
    temp = root / "inspect-status.json"
    for index, item in sorted(manifests.items()):
        if counts.get(index, 0) >= 3:
            continue
        github.download(item, temp)
        try:
            summary = json.loads(temp.read_text(encoding="utf-8"))
        finally:
            temp.unlink(missing_ok=True)
        if not summary.get("complete"):
            # Recovery step 1: complete interrupted/never-started shards first.
            # All other partial shards are preserved for error-classified recovery.
            if not only_unprocessed or int(summary.get("processed") or 0) == 0:
                unresolved.append(index)
    return unresolved, "recheck", counts


def write_chunk_csv(queue, index, filepath):
    start = FIRST_OFFSET + SHARD_SIZE * index
    selected = queue[start:start + SHARD_SIZE]
    if not selected:
        raise RuntimeError("Empty shard despite expected index")
    # Preserve the same original column strings and ordering.
    keys = list(queue[0].keys())
    with filepath.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(selected)
    return len(selected)


def shard_status(output, segment, count, command_code):
    summary_path = output / "detail_summary.json"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        summary = {}
    statuses = summary.get("detail_status_counts", {})
    bad = sum(int(statuses.get(x, 0)) for x in
              ("error", "partial_page_limit", "no_bidder_rows_unverified"))
    complete = bool(
        command_code == 0 and summary.get("processed") == count and
        summary.get("selected") == count and bad == 0 and
        not summary.get("interrupted"))
    return {
        "segment": segment,
        "expected": count,
        "processed": summary.get("processed", 0),
        "verified_complete": statuses.get("verified_complete", 0),
        "no_opening_data": statuses.get("no_opening_data", 0),
        "unknown": bad,
        "verified_bidder_rows": summary.get("verified_bidder_rows", 0),
        "complete": complete,
        "exit_code": command_code,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "award_linkage_verified": False,
        "excel_integration_verified": False
    }


def process_shard(github, original_assets, checkpoint_assets, release,
                  queue, segment, script, root, runid):
    shard_root = root / ("detail-shard-" + str(segment))
    shard_root.mkdir(parents=True, exist_ok=True)
    old_name = "g2b-real-bidder-details-shard-" + str(segment) + ".zip"
    recover_prefix = "g2b-repair-shard-%d-" % segment
    saved = sorted((a for a in checkpoint_assets
                    if a["name"].startswith(recover_prefix) and a["name"].endswith(".zip")),
                   key=lambda a: a["created_at"], reverse=True)
    source = saved[0] if saved else select_asset(original_assets, old_name)
    if source:
        old_zip = root / "restored.zip"
        github.download(source, old_zip)
        safe_extract(old_zip, shard_root)
        old_zip.unlink()
        log("CHECKPOINT_REUSED", shard=segment, source=source["name"])
    else:
        log("SHARD_WITHOUT_PRIOR_ZIP", shard=segment)

    chunk_path = root / "chunk.csv"
    selected = write_chunk_csv(queue, segment, chunk_path)
    args = [sys.executable, str(script), "--input", str(chunk_path),
            "--start-index", "0", "--limit", str(selected), "--tabs", "10",
            "--max-pages", "20", "--timeout", "9000", "--output", str(shard_root)]
    log("SHARD_START", segment=segment, selected=selected, workers=10)
    try:
        code = subprocess.run(args, check=False, timeout=10000).returncode
    except subprocess.TimeoutExpired:
        code = 124
    status = shard_status(shard_root, segment, selected, code)

    # Safeguard: a result is not declared complete merely because a return
    # code is zero; the status.json and original page files are also checked.
    if status["complete"]:
        for row in queue[FIRST_OFFSET + segment * SHARD_SIZE:
                         FIRST_OFFSET + segment * SHARD_SIZE + selected]:
            try:
                d = detail.folder_for(shard_root, row)
                metadata = json.loads((d / "status.json").read_text(encoding="utf-8"))
                if not detail.cached_complete(d, metadata):
                    status["complete"] = False
                    status["validation_error"] = "source_raw_or_csv_verification_failed"
                    break
            except (OSError, KeyError, ValueError):
                status["complete"] = False
                status["validation_error"] = "missing_original_evidence"
                break

    stamp = runid + "-" + str(int(time.time()))
    outzip = root / ("g2b-repair-shard-%d-%s.zip" % (segment, stamp))
    archive_dir(shard_root, outzip)
    uploaded = github.upload(release, outzip, outzip.name)
    status["archive_sha256"] = digest_file(outzip)
    status["archive_size"] = outzip.stat().st_size
    status["archive_asset_id"] = uploaded["id"]
    manifest = root / ("g2b-status-shard-%d-%s.json" % (segment, stamp))
    manifest.write_text(json.dumps(status, indent=2, sort_keys=True), encoding="utf-8")
    github.upload(release, manifest, manifest.name)
    log("SHARD_CHECKPOINT_VERIFIED", **status)
    outzip.unlink()
    manifest.unlink()
    chunk_path.unlink()
    shutil.rmtree(shard_root)
    return status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--archive-tag", default=ORIGINAL_RELEASE)
    parser.add_argument("--checkpoint-tag", default="procureflow-stage2-tenworkers-20261115")
    parser.add_argument("--max-shards", type=int, default=12)
    parser.add_argument("--threads", type=int, default=10)
    parser.add_argument("--repair-only-unprocessed", action="store_true",
                        help="Process ONLY shards whose latest status has zero processed records")
    args = parser.parse_args()
    if args.threads != 10:
        raise ValueError("Supervisor configured for exactly ten request workers")
    if not (1 <= args.max_shards <= 187):
        raise ValueError("Invalid shard maximum")
    root = Path(args.workdir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    github = Github(args.repo, os.environ.get("GH_TOKEN", ""))
    original_release = github.release(args.archive_tag)
    checkpoint_release = github.release(args.checkpoint_tag, create=True)
    original_assets = github.assets(original_release)
    checkpoint_assets = github.assets(checkpoint_release)
    queue = read_original_queue(github, original_release, root)
    pending, phase, prior_attempts = choose_segments(github, checkpoint_assets, root, args.repair_only_unprocessed)
    chosen = pending[:args.max_shards]
    runid = os.environ.get("GITHUB_RUN_ID", "manual")
    script = Path(__file__).with_name("g2b_bidder_detail_stage2_recovery.py")
    errors = []
    done = []
    for segment in chosen:
        try:
            result = process_shard(github, original_assets, checkpoint_assets,
                                   checkpoint_release, queue, segment, script, root,
                                   runid)
            done.append(result)
        except Exception as exc:
            log("SHARD_FATAL", segment=segment, error=type(exc).__name__ + ":" + str(exc))
            errors.append({"segment": segment, "error": str(exc)})
            # Never skip past an unpreserved shard: its state must be retried.
            break

    # Stop if no positive progress; do not spin on an unusable offline PC
    # or repeated server errors. Release assets are the durable cursor.
    manifest = {
        "phase": phase,
        "segments_checked_this_run": [x["segment"] for x in done],
        "complete_shards_this_run": sum(x["complete"] for x in done),
        "errors": errors,
        "new_shards_remaining": max(0, len(pending) - len(done)),
        "need_continue": bool(done and not errors and (
            len(pending) > len(done) or
            any(not x["complete"] and prior_attempts.get(x["segment"], 0) < 2
                for x in done))),
        "all_stage2_verified": False,
        "source_index_unchanged": True,
        "award_linkage_verified": False,
        "excel_integration_verified": False
    }
    statefile = root / "runner-state.json"
    statefile.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log("SUPERVISOR_RESULT", **manifest)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
