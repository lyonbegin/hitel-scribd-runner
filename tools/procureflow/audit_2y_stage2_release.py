#!/usr/bin/env python3
"""Read-only Release manifest auditor for the existing 2-year G2B bidder archive.

Checks the actual downloaded bytes of all shard status JSON manifests, cross-checks
the matching ZIP SHA256/size metadata, and extracts three representative ZIP assets
for independent byte SHA256 and CRC checks. Does NOT re-query G2B notices.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

TAG = "procureflow-stage2-tenworkers-20261115"
COUNT = 187
EXPECTED = 930279
STATUS = re.compile(r"^g2b-status-shard-(\d+)-(.+)\.json$")
ZIP = re.compile(r"^g2b-repair-shard-(\\d+)-(.+)\.zip$")
SAMPLES = (0,93,186)

def checksum(path):
    hasher=hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda:stream.read(1024*1024),b""):
            hasher.update(data)
    return hasher.hexdigest()

def api(token, url):
    req=urllib.request.Request(url,headers={
        "Accept":"application/vnd.github+json",
        "Authorization":"Bearer "+token,
        "User-Agent":"ProcureFlow-2Y-ReadOnly-Audit",
        "X-GitHub-Api-Version":"2022-11-28",
    })
    with urllib.request.urlopen(req,timeout=45) as response:
        return json.load(response)

def download_release(repo, glob, folder):
    folder.mkdir(parents=True,exist_ok=True)
    cmd=["gh","release","download",TAG,"--repo",repo,"--pattern",glob,
         "--dir",str(folder)]
    subprocess.run(cmd,check=True,timeout=900)

def run():
    repo=os.environ.get("GITHUB_REPOSITORY","lyonbegin/hitel-scribd-runner")
    token=os.environ.get("GH_TOKEN") or ""
    if not token:raise RuntimeError("GH_TOKEN_REQUIRED")
    root=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"pf2-release-audit"
    root.mkdir(parents=True,exist_ok=True)
    report={"at":dt.datetime.now(dt.timezone.utc).isoformat(),
            "repo":repo,"tag":TAG,"expected_shards":COUNT,
            "expected_stage2_input_count":EXPECTED,
            "status_count":0,"zip_count":0,
            "status_sha256_verified":0,"paired_sha256_metadata_verified":0,
            "complete_shards":0,"incomplete_shards":[],
            "sum_expected":0,"sum_processed":0,
            "sum_bidder_rows":0,"sum_verified_complete":0,
            "sum_no_opening_data":0,"sum_unknown":0,
            "zip_samples":[],"errors":[]}
    try:
        release=api(token,"https://api.github.com/repos/"+repo+"/releases/tags/"+TAG)
        assets=[]
        page=1
        while True:
            chunk=api(token,"https://api.github.com/repos/"+repo+"/releases/"+str(release["id"])+"/assets?per_page=100&page="+str(page))
            assets.extend(chunk)
            if len(chunk)<100:break
            page+=1
        statuses={}
        zips={}
        for item in assets:
            sm=STATUS.fullmatch(item["name"])
            zm=ZIP.fullmatch(item["name"])
            if sm:
                shard=int(sm.group(1))
                if shard not in statuses or item["created_at"]>statuses[shard]["created_at"]:
                    statuses[shard]=item
            if zm:
                shard=int(zm.group(1))
                if shard not in zips or item["created_at"]>zips[shard]["created_at"]:
                    zips[shard]=item
        report["status_count"]=len(statuses)
        report["zip_count"]=len(zips)
        missing_status=sorted(set(range(COUNT))-set(statuses))
        missing_zip=sorted(set(range(COUNT))-set(zips))
        report["missing_status_shards"]=missing_status
        report["missing_zip_shards"]=missing_zip
        if missing_status or missing_zip:report["errors"].append("missing-shard-assets")
        stored=root/"statuses"
        download_release(repo,"g2b-status-shard-*.json",stored)
        manifests={}
        for shard,item in sorted(statuses.items()):
            path=stored/item["name"]
            if not path.is_file():
                report["errors"].append("missing-downloaded-status:"+str(shard))
                continue
            actualsha=checksum(path)
            if item.get("digest")!="sha256:"+actualsha or path.stat().st_size!=item["size"]:
                report["errors"].append("status-asset-digest-mismatch:"+str(shard))
                continue
            report["status_sha256_verified"]+=1
            try:
                info=json.loads(path.read_text(encoding="utf-8"))
            except (OSError,ValueError):
                report["errors"].append("status-json-invalid:"+str(shard))
                continue
            manifests[shard]=info
            zipasset=zips.get(shard)
            if zipasset is None:
                continue
            related_stamp=STATUS.fullmatch(item["name"]).group(2)
            expected_zip="g2b-repair-shard-"+str(shard)+"-"+related_stamp+".zip"
            if (zipasset["name"] != expected_zip or
                zipasset.get("digest") != "sha256:"+str(info.get("archive_sha256")) or
                zipasset["size"] != info.get("archive_size")):
                report["errors"].append("archive-metadata-manifest-mismatch:"+str(shard))
            else:
                report["paired_sha256_metadata_verified"]+=1
            for field,key in (("expected","sum_expected"),("processed","sum_processed"),
                              ("verified_bidder_rows","sum_bidder_rows"),
                              ("verified_complete","sum_verified_complete"),
                              ("no_opening_data","sum_no_opening_data"),
                              ("unknown","sum_unknown")):
                report[key]+=int(info.get(field) or 0)
            iscomplete=(info.get("complete") is True and
                        int(info.get("processed") or 0)==int(info.get("expected") or -1) and
                        int(info.get("unknown") or 0)==0)
            if iscomplete:report["complete_shards"]+=1
            else:report["incomplete_shards"].append({"shard":shard,
                "processed":info.get("processed"),"expected":info.get("expected"),
                "unknown":info.get("unknown"),"complete":info.get("complete")})

        if report["sum_expected"]!=EXPECTED:
            report["errors"].append("unexpected-total-selected:"+str(report["sum_expected"]))
        if report["status_sha256_verified"]!=COUNT or report["paired_sha256_metadata_verified"]!=COUNT:
            report["errors"].append("status-or-pair-audit-incomplete")

        # Actual ZIP downloads are bounded to 3 samples rather than 9GB by default.
        sample_root=root/"sample_zips"
        for i in SAMPLES:
            asset=zips.get(i)
            if not asset:continue
            target=sample_root/asset["name"]
            sample_root.mkdir(parents=True,exist_ok=True)
            download_release(repo,asset["name"],sample_root)
            entry={"shard":i,"name":asset["name"],"bytes":target.stat().st_size}
            entry["actual_sha256"]=checksum(target)
            entry["expected_digest"]=asset.get("digest")
            entry["sha_match"]=entry["expected_digest"]=="sha256:"+entry["actual_sha256"]
            entry["byte_match"]=entry["bytes"]==asset["size"]
            with zipfile.ZipFile(target) as z:
                bad=z.testzip()
                entry["zip_crc_ok"]=(bad is None)
                members=z.namelist()
                entry["files"]=len(members)
                entry["status_files"]=sum(x.endswith("/status.json") for x in members)
                entry["bidder_csv_files"]=sum(x.endswith("/bidders.csv") for x in members)
            report["zip_samples"].append(entry)
            if not all(entry[k] for k in ("sha_match","byte_match","zip_crc_ok")):
                report["errors"].append("bad-zip-sample:"+str(i))
            target.unlink()
    except Exception as e:
        report["errors"].append(type(e).__name__+":"+str(e)[:220])
    report["audit_complete"]=len(report["errors"])==0 and report["complete_shards"]==COUNT and len(report["zip_samples"])==3
    out=root/"release-2y-audit.json"
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    brief={k:report[k] for k in (
        "status_count","zip_count","status_sha256_verified","paired_sha256_metadata_verified",
        "complete_shards","sum_expected","sum_processed","sum_bidder_rows",
        "sum_no_opening_data","sum_unknown","incomplete_shards","zip_samples","errors","audit_complete"
    )}
    print("PROCUREFLOW_STAGE2_RELEASE_AUDIT",json.dumps(brief,ensure_ascii=False),flush=True)
    return 0 if report["audit_complete"] else 1

if __name__=="__main__":
    sys.exit(run())
