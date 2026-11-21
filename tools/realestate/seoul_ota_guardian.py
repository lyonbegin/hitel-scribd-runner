#!/usr/bin/env python3
"""Guard the Seoul OTA watchdog itself.

The worker watcher is normally renewed via workflow_dispatch when it finishes.
This separate guardian recovers missed handoffs and stuck watcher executions.
GitHub schedule is only a backup; there is no guaranteed off-GitHub clock.
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

REPO=os.getenv("GITHUB_REPOSITORY","lyonbegin/hitel-scribd-runner")
WATCHDOG="seoul-ota-watchdog.yml"
BRANCH="research/seoul-homestay-public-20261121"
REPORT=Path("artifacts/seoul-ota-watchdog/guardian.json")
EVENTS=[]
MAX_AGE_SECONDS=540
RECENT_RUN_SECONDS=150

def now():
    return dt.datetime.now(dt.timezone.utc)

def stamp():
    return now().isoformat(timespec="seconds")

def gh(*args, timeout=60):
    proc=subprocess.run(["gh",*args],text=True,capture_output=True,timeout=timeout)
    if proc.returncode:
        raise RuntimeError(f"gh {args[:3]}: {proc.stderr[-450:]} {proc.stdout[-150:]}")
    return proc.stdout

def api(path):
    return json.loads(gh("api",path))

def age(iso):
    if not iso:return None
    try:
        created=dt.datetime.fromisoformat(iso.replace("Z","+00:00"))
        return max(0,(now()-created).total_seconds())
    except ValueError:
        return None

def report(action, **data):
    e={"at":stamp(),"action":action,**data}
    EVENTS.append(e)
    print("OTA_GUARDIAN",json.dumps(e,ensure_ascii=False),flush=True)

def save():
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    REPORT.write_text(json.dumps({
        "time":stamp(),"events":EVENTS[-25:],
        "recovery_scope":"GitHub Actions watchdog, not an external always-on monitor",
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def watchers():
    return api(f"repos/{REPO}/actions/workflows/{WATCHDOG}/runs?per_page=40")["workflow_runs"]

def fully_completed():
    try:
        item=api(f"repos/{REPO}/contents/data/seoul-ota/state.json?ref={quote(BRANCH,safe='')}")
        state=json.loads(base64.b64decode(item["content"]))
        records=int(state.get("input_records",0))
        done=int(state.get("done_full_pass",0))
        return records>5000 and done>=records,{"records":records,"fully_done":done,
          "total_search_steps":state.get("total_stages_completed",0)}
    except Exception as e:
        report("progress_unreadable",error=str(e)[:250])
        return False,{}

def dispatch(reason, dry_run=False):
    if dry_run:
        report("would_dispatch_watchdog",reason=reason)
        return
    gh("workflow","run",WATCHDOG,"--repo",REPO,"--ref","main")
    report("dispatched_watchdog",reason=reason)

def controller(mode, dry_run=False):
    completed,stats=fully_completed()
    if completed:
        report("fully_scanned_stop",**stats)
        return "done"
    runs=watchers()
    me=os.getenv("GITHUB_RUN_ID","")
    other_active=[r for r in runs if str(r["id"])!=me and
                  r.get("status") in {"in_progress","queued","pending","waiting","requested"}]
    if mode=="chain":
        if other_active:
            report("chain_successor_exists",other_run_ids=[r["id"] for r in other_active[:6]])
            return "waiting"
        dispatch("normal_watchdog_handoff",dry_run)
        return "dispatched"
    # Guardian mode: do not take over a healthy running or queued watchdog.
    if other_active:
        active=sorted(other_active,key=lambda r:r.get("status")!="in_progress")
        w=active[0]
        elapsed=age(w.get("run_started_at") or w.get("created_at"))
        if elapsed is None or elapsed<MAX_AGE_SECONDS:
            report("watchdog_healthy_or_starting",watchdog_run=w["id"],
                   status=w.get("status"),age_seconds=elapsed)
            return "healthy"
        report("watchdog_stale_confirmed",watchdog_run=w["id"],
               status=w.get("status"),age_seconds=elapsed)
        if dry_run:return "would_cancel"
        try:
            gh("run","cancel",str(w["id"]),"--repo",REPO)
            report("watchdog_cancel_requested",watchdog_run=w["id"])
        except Exception as e:
            report("watchdog_cancel_error",error=str(e))
            return "error"
        # Wait for GitHub to acknowledge cancellation. Do NOT overlap old and
        # replacement watchdogs. The next guardian still serves as fallback.
        for attempt in range(1,7):
            time.sleep(5)
            current=watchers()
            replacements=[r for r in current if r["id"]!=w["id"] and
                          str(r["id"])!=me and
                          r.get("status") in {"in_progress","queued","pending","waiting","requested"}]
            if replacements:
                report("watchdog_recovered_by_other",run_id=replacements[0]["id"])
                return "recovered_by_other"
            old_run=next((r for r in current if r["id"]==w["id"]),None)
            if old_run and old_run.get("status")=="completed":
                dispatch("confirmed_stale_watchdog_cancelled",dry_run)
                return "dispatched"
        report("cancellation_unsettled_retry_next_guardian",watchdog_run=w["id"])
        return "cancel_requested"
    most_recent=runs[0] if runs else None
    if most_recent:
        latest_age=age(most_recent.get("created_at"))
        if latest_age is not None and latest_age<RECENT_RUN_SECONDS:
            report("watchdog_handoff_grace",latest_run=most_recent["id"],age_seconds=latest_age)
            return "grace"
    dispatch("watchdog_missing_or_not_restarted",dry_run)
    return "dispatched"

def selftest():
    """Replay missing, healthy, stuck-running, stuck-queued and complete cases."""
    from unittest.mock import patch
    assert age(None) is None
    assert age("bad") is None
    assert MAX_AGE_SECONDS>RECENT_RUN_SECONDS
    assert WATCHDOG=="seoul-ota-watchdog.yml"
    current=now()
    fresh={"id":123,"status":"in_progress",
           "created_at":current.isoformat(),
           "run_started_at":current.isoformat()}
    stale={"id":456,"status":"in_progress",
           "created_at":(current-dt.timedelta(minutes=15)).isoformat(),
           "run_started_at":(current-dt.timedelta(minutes=15)).isoformat()}
    finished={**stale,"status":"completed","conclusion":"cancelled"}
    with patch(__name__+".fully_completed",return_value=(False,{"records":5320})):
        with patch(__name__+".watchers",return_value=[]),patch(__name__+".gh",return_value="") as fake:
            assert controller("rescue")=="dispatched"
            fake.assert_called_once_with("workflow","run",WATCHDOG,"--repo",REPO,"--ref","main")
        with patch(__name__+".watchers",return_value=[fresh]),patch(__name__+".gh",return_value="") as fake:
            assert controller("rescue")=="healthy"
            fake.assert_not_called()
        with patch(__name__+".watchers",side_effect=[[stale],[finished]]),\
             patch(__name__+".gh",return_value="") as fake,\
             patch(__name__+".time.sleep",return_value=None):
            assert controller("rescue")=="dispatched"
            assert fake.call_count==2
            assert fake.call_args_list[0].args==("run","cancel","456","--repo",REPO)
            assert fake.call_args_list[1].args==("workflow","run",WATCHDOG,"--repo",REPO,"--ref","main")
        stale_queued={**stale,"status":"queued"}
        finished_queued={**stale_queued,"status":"completed","conclusion":"cancelled"}
        with patch(__name__+".watchers",side_effect=[[stale_queued],[finished_queued]]),\
             patch(__name__+".gh",return_value="") as fake,\
             patch(__name__+".time.sleep",return_value=None):
            assert controller("rescue")=="dispatched"
            assert fake.call_count==2
        with patch(__name__+".watchers",return_value=[]),patch(__name__+".gh",return_value="") as fake:
            assert controller("chain")=="dispatched"
            fake.assert_called_once()
        with patch(__name__+".watchers",return_value=[fresh]),patch(__name__+".gh",return_value="") as fake:
            assert controller("chain")=="waiting"
            fake.assert_not_called()
    with patch(__name__+".fully_completed",return_value=(True,{"records":5320,"fully_done":5320})),\
         patch(__name__+".gh",return_value="") as fake:
        assert controller("rescue")=="done"
        fake.assert_not_called()
    print("OTA_GUARDIAN_SELFTEST_OK missing healthy stuck_running stuck_queue chain complete",flush=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--mode",choices=["chain","rescue"],required=False,default="rescue")
    parser.add_argument("--dry-run",action="store_true")
    parser.add_argument("--selftest",action="store_true")
    options=parser.parse_args()
    if options.selftest:
        selftest()
        return
    try:
        controller(options.mode,options.dry_run)
    finally:
        save()

if __name__=="__main__":
    main()
