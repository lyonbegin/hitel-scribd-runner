#!/usr/bin/env python3
"""Independent Seoul OTA GitHub Actions watchdog.
Public-repo GitHub API only. No always-on server.
Checks worker status and durable checkpoint; cancels only *confirmed* stale runs.
Re-dispatches safe resume after a completed/failed/cancelled worker.
"""
from __future__ import annotations
import argparse
import base64
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.parse import quote

REPO=os.environ.get("GITHUB_REPOSITORY","lyonbegin/hitel-scribd-runner")
WORKFLOW="seoul-ota-public-contacts.yml"
WORKER_PATH=".github/workflows/"+WORKFLOW
REF="research/seoul-homestay-public-20261121"
NOW=lambda:dt.datetime.now(dt.timezone.utc)
REPORT=Path("artifacts/seoul-ota-watchdog/report.json")
STALE_SECONDS=int(os.getenv("OTA_STALE_SECONDS","480"))
QUEUE_STALE_SECONDS=900
NO_HEARTBEAT_GRACE_SECONDS=540
EVENTS=[]
SEEN_STALE={}
LAST_DISPATCH_AT=None

def stamp(t=None):
    return (t or NOW()).isoformat(timespec="seconds")

def gh(*args,timeout=50):
    p=subprocess.run(["gh",*args],capture_output=True,text=True,timeout=timeout)
    if p.returncode:
        raise RuntimeError(f"gh {args[:3]} failed: {p.stderr[-400:]} {p.stdout[-150:]}")
    return p.stdout

def api(path):
    return json.loads(gh("api",path))

def tparse(x):
    try:
        return dt.datetime.fromisoformat(x.replace("Z","+00:00"))
    except (AttributeError,ValueError):return None

def age_seconds(iso,now):
    t=tparse(iso)
    return (now-t).total_seconds() if t else None

def branch_json(path):
    try:
        d=api(f"repos/{REPO}/contents/{quote(path,safe='/')}?ref={quote(REF,safe='')}")
        raw=base64.b64decode(d["content"])
        return json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:
        EVENTS.append({"event":"branch_file_unavailable","path":path,"error":str(exc)[:180]})
        return {}

def recent_worker_runs():
    try:
        obj=api(f"repos/{REPO}/actions/workflows/{WORKFLOW}/runs?per_page=60")
    except Exception:
        obj=api(f"repos/{REPO}/actions/runs?per_page=100")
    runs=[r for r in obj.get("workflow_runs",[]) if r.get("path")==WORKER_PATH]
    return sorted(runs,key=lambda x:x.get("created_at",""),reverse=True)

def decide_worker(active,heartbeat,now):
    """Pure health state decision; no cancellations without two stale observations."""
    start_age=age_seconds(active.get("run_started_at") or active.get("created_at"),now)
    if active["status"] in {"queued","waiting","pending","requested"}:
        if start_age is not None and start_age>QUEUE_STALE_SECONDS:
            return "stale_queue"
        return "queued"
    if start_age is None:return "unknown_start"
    if start_age<=NO_HEARTBEAT_GRACE_SECONDS:return "startup_grace"
    if str(heartbeat.get("run_id"))!=str(active["id"]):
        return "stale_missing_heartbeat"
    silence=age_seconds(heartbeat.get("updated_at"),now)
    if silence is None:return "stale_invalid_heartbeat"
    if silence>STALE_SECONDS:return "stale_no_progress"
    return "healthy"

def slowdown_seconds(completed):
    """Throttle repeated no-progress failures to avoid runaway expensive loops."""
    bad=[]
    for r in completed[:6]:
        if r.get("conclusion") in {"failure","cancelled","timed_out"}:bad.append(r)
        else:break
    if len(bad)>=6:return 1800
    if len(bad)>=3:return 900
    return 40

def record(**kwargs):
    item={"checked_at":stamp(),**kwargs}
    EVENTS.append(item)
    print("WATCHDOG",json.dumps(item,ensure_ascii=False),flush=True)

def save_report():
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    REPORT.write_text(json.dumps({
        "updated_at":stamp(),
        "recovered_from_checkpoint":True,
        "monitoring_source":"GitHub Actions worker + GitHub branch heartbeat",
        "github_schedule_minimum_minutes":5,
        "within_run_poll_seconds":120,
        "stale_after_seconds":STALE_SECONDS,
        "events":EVENTS[-100:],
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def check_once(dry_run=False):
    global LAST_DISPATCH_AT
    now=NOW()
    runs=recent_worker_runs()
    heartbeat=branch_json("data/seoul-ota/worker_heartbeat.json")
    state=branch_json("data/seoul-ota/state.json")
    progress=int(state.get("total_stages_completed",0))
    records=int(state.get("input_records",5317))
    stages=int(state.get("stages",7))
    done=int(state.get("done_full_pass",0))
    active=[r for r in runs if r.get("status") in {"in_progress","queued","waiting","pending","requested"}]
    active.sort(key=lambda x:x.get("status")!="in_progress")
    if active:
        run=active[0]
        reason=decide_worker(run,heartbeat,now)
        rid=run["id"]
        if reason.startswith("stale"):
            SEEN_STALE[rid]=SEEN_STALE.get(rid,0)+1
        else:
            SEEN_STALE.pop(rid,None)
        record(action="monitor",run_id=rid,run_status=run["status"],reason=reason,
               stale_observations=SEEN_STALE.get(rid,0),
               progress_stages=progress,checkpoint_run_id=heartbeat.get("run_id"),
               heartbeat_at=heartbeat.get("updated_at"))
        if reason.startswith("stale") and SEEN_STALE[rid]>=2:
            if not dry_run:
                try:
                    gh("run","cancel",str(rid),"--repo",REPO)
                    record(action="requested_cancel",run_id=rid,reason=reason)
                except Exception as e:
                    record(action="cancel_failed",run_id=rid,error=str(e))
            else:record(action="would_cancel",run_id=rid,reason=reason)
            SEEN_STALE[rid]=0
        return "active"
    if not runs:
        record(action="no_worker_history",detail="Dispatch initial worker")
    if records>0 and done>=records:
        record(action="finished_all",done=done,records=records,stages=stages)
        return "done"
    completed=[r for r in runs if r.get("status")=="completed"]
    last=completed[0] if completed else None
    if not last and runs:
        record(action="wait_for_runs",detail="Latest run not yet settled")
        return "waiting"
    cooldown=slowdown_seconds(completed)
    if last:
        age=age_seconds(last.get("updated_at") or last.get("created_at"),now)
        if age is not None and age<cooldown:
            record(action="cooldown",last_run=last["id"],
                  conclusion=last.get("conclusion"),remaining_seconds=round(cooldown-age))
            return "cooldown"
    if LAST_DISPATCH_AT and (now-LAST_DISPATCH_AT).total_seconds()<180:
        record(action="dispatch_cooldown",seconds=int((now-LAST_DISPATCH_AT).total_seconds()))
        return "cooldown"
    if not dry_run:
        # Workflow exists on default main; research branch is checked out in worker YAML.
        gh("workflow","run",WORKFLOW,"--repo",REPO,"--ref","main")
    LAST_DISPATCH_AT=now
    record(action="dispatched" if not dry_run else "would_dispatch",
           from_completed_run=last.get("id") if last else None,
           latest_run_conclusion=last.get("conclusion") if last else None,
           saved_stages=progress,done_full_pass=done,records=records)
    return "dispatched"

def selftest():
    now=dt.datetime(2026,11,21,8,0,tzinfo=dt.timezone.utc)
    active={"id":123,"status":"in_progress","run_started_at":(now-dt.timedelta(minutes=20)).isoformat()}
    hb={"run_id":"123","updated_at":(now-dt.timedelta(minutes=2)).isoformat()}
    assert decide_worker(active,hb,now)=="healthy"
    hb["updated_at"]=(now-dt.timedelta(minutes=10)).isoformat()
    assert decide_worker(active,hb,now)=="stale_no_progress"
    assert decide_worker(active,{"run_id":"999"},now)=="stale_missing_heartbeat"
    active["status"]="queued"
    assert decide_worker(active,{},now)=="stale_queue"
    active["status"]="in_progress"
    active["run_started_at"]=(now-dt.timedelta(minutes=2)).isoformat()
    assert decide_worker(active,{},now)=="startup_grace"
    assert slowdown_seconds([{"conclusion":"failure"}]*6)==1800
    print("WATCHDOG_SELFTEST_OK",flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--checks",type=int,default=3)
    p.add_argument("--interval",type=int,default=120)
    p.add_argument("--dry-run",action="store_true")
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:return selftest()
    try:
        for i in range(args.checks):
            try:
                outcome=check_once(args.dry_run)
            except Exception as e:
                record(action="watchdog_check_error",error=repr(e))
                outcome="error"
            save_report()
            if outcome in {"done","dispatched"}:break
            if i<args.checks-1:time.sleep(args.interval)
    finally:save_report()
if __name__=="__main__":main()
