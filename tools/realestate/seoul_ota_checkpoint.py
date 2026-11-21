#!/usr/bin/env python3
"""Durable, non-force GitHub checkpoint for Seoul OTA worker.
Commits every small batch while the worker is still running. Strictly no force push.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import time

TARGET="research/seoul-homestay-public-20261121"
BASE=pathlib.Path("data/seoul-ota")
def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
def git(*args,check=True):
    p=subprocess.run(["git",*args],capture_output=True,text=True,check=False,timeout=60)
    if check and p.returncode:
        raise RuntimeError(f"GIT {args}: {p.stdout[-1000:]} {p.stderr[-1000:]}")
    return p
def checkpoint(phase:str):
    if not (BASE/"state.json").exists():
        raise RuntimeError("Missing state.json; refusing to write misleading heartbeat")
    state=json.loads((BASE/"state.json").read_text(encoding="utf-8"))
    count=int(state.get("total_stages_completed",0))
    if count<=0:raise RuntimeError("Invalid checkpoint counter")
    mark={
       "run_id":os.environ.get("GITHUB_RUN_ID","local"),
       "phase":phase,
       "updated_at":utc(),
       "total_stages_completed":count,
       "properties_touched":len(state.get("progress",{})),
       "worker_ref":TARGET,
       "new_public_contacts_in_run":state.get("last_run",{}).get("new_public_contacts",0),
    }
    (BASE/"worker_heartbeat.json").write_text(json.dumps(mark,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    git("config","user.name","github-actions[bot]")
    git("config","user.email","41898282+github-actions[bot]@users.noreply.github.com")
    git("add","data/seoul-ota/")
    changed=git("diff","--cached","--quiet",check=False)
    if changed.returncode not in (0,1):raise RuntimeError("git diff failure")
    if changed.returncode==1:
        git("commit","-m",f"data(realestate): OTA checkpoint {count} stages [{phase}] [skip ci]")
    for attempt in range(1,4):
        git("fetch","origin",TARGET)
        base=git("rev-parse",f"origin/{TARGET}").stdout.strip()
        local=git("rev-parse","HEAD").stdout.strip()
        if local!=base:
            rebase=git("rebase",f"origin/{TARGET}",check=False)
            if rebase.returncode:
                git("rebase","--abort",check=False)
                raise RuntimeError(f"Conflict: preserving local state and source artifacts; rebase rejected: {rebase.stderr[-500:]}")
        push=git("push","origin",f"HEAD:{TARGET}",check=False)
        if push.returncode==0:
            print("CHECKPOINT_PUSH_OK",json.dumps(mark,ensure_ascii=False),flush=True)
            return
        if attempt<3:time.sleep(attempt)
    raise RuntimeError(f"Checkpoint push failed after 3 non-force retries: {push.stderr[-700:]}")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--phase",choices=["running","complete","recovered"],default="running")
    a=p.parse_args()
    checkpoint(a.phase)
if __name__=="__main__":main()
