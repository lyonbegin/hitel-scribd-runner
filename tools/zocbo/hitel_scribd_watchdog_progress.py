#!/usr/bin/env python3
"""Durable 5-minute Scribd health sampler and *evidence-gated* recovery.

GitHub Actions starts with a blank filesystem on every run. Store a tiny
content-free observation as a GitHub Actions artifact. At the next check,
recover the prior observation and compare checkpoint progress, the active job,
and Railway's exact job status. Do not mistake a live model's slow response for
a terminated request, and NEVER send an AI prompt from this watchdog.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import hitel_scribd_watchdog as base
from hitel_dispatch_next_verified import GithubClient

SAMPLE_ARTIFACT = "hitel-scribd-watchdog-five-minute-observation"
SAMPLE_FILE = "five-minute-health.json"
MIN_INTERVAL_SECONDS = 240
STAGNATION_SECONDS = 600
REMOTE_COMPLETED_FLAGS = ("result_ready", "chatgpt_send_confirmed",
                          "assistant_reply_observed")


def epoch(s: str) -> float:
    return base.date_of(s).timestamp()


def prior_observation(client: GithubClient):
    data = base.github_listing(
        client, "actions/artifacts?name="+SAMPLE_ARTIFACT+"&per_page=100",
        "WATCHDOG_OBSERVATION_ARTIFACTS")
    items = [a for a in data.get("artifacts", [])
             if a.get("name") == SAMPLE_ARTIFACT and not a.get("expired")
             and a.get("workflow_run", {}).get("head_branch") == "main"
             and int(a.get("workflow_run", {}).get("id", 0))
                 != int(os.environ.get("GITHUB_RUN_ID", "0"))]
    if not items:
        return None
    latest = max(items, key=lambda a: a["created_at"])
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            ["gh", "run", "download",
             str(latest["workflow_run"]["id"]),
             "--repo", client.repository, "-n", SAMPLE_ARTIFACT,
             "-D", tmp],
            env=dict(os.environ, GH_TOKEN=client.token),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=120, check=False)
        if result.returncode:
            raise RuntimeError("PREVIOUS_WATCHDOG_OBSERVATION_DOWNLOAD_FAILED")
        path = Path(tmp) / SAMPLE_FILE
        if not path.is_file():
            raise RuntimeError("PREVIOUS_WATCHDOG_OBSERVATION_MISSING")
        observation = json.loads(path.read_text("utf-8"))
    if (observation.get("version") != 1
            or not isinstance(observation.get("verified"), int)
            or not isinstance(observation.get("observed_at"), (int, float))):
        raise ValueError("PREVIOUS_WATCHDOG_OBSERVATION_CORRUPTED")
    return observation


def worker_status():
    with urllib.request.urlopen(base.API_PUBLIC+"/status",timeout=20) as res:
        status = json.load(res)
    if not isinstance(status, dict):
        raise ValueError("WORKER_STATUS_BAD_RESPONSE")
    return status


def active_phase(client: GithubClient, run):
    if not run:
        return ("no_running_classifier", None, None)
    jobs = base.github_listing(
        client, "actions/runs/%d/jobs?per_page=100" % run["id"],
        "ACTIVE_CLASSIFIER_JOB_STEPS")
    phases = []
    for job in jobs.get("jobs", []):
        if job.get("status") != "in_progress":
            continue
        active = next((s for s in job.get("steps", [])
                       if s.get("status") == "in_progress"), {})
        phases.append((job.get("name"), active.get("name")))
    if not phases:
        return ("running_with_no_active_step", None, None)
    job, step = phases[-1]
    return (job+" / "+str(step), job, step)


def exact_remote_from_checkpoint(root: Path, verified):
    """Read the batch request from immutable checkpoint, not account history.

    After a deliberate worker-loss recovery, use its recorded *recovery1*
    request rather than mistaking the old terminal job for the live job.
    A missing checkpoint is resolved by exact deterministic request ID.
    """
    batch=base.next_batch(base.source_rows(), verified)
    if not batch:
        return None
    key=f'{batch[0]["번호"]:05d}-{batch[-1]["번호"]:05d}'
    for filename in (root/"http"/"worker_recoveries"/(key+".json"),
                     root/"http"/(key+".json")):
        if not filename.is_file():
            continue
        state=json.loads(filename.read_text("utf-8"))
        jid=state.get("job_id")
        if jid:
            if not str(jid).startswith("job_"):
                raise ValueError("CHECKPOINT_REMOTE_JOB_ID_INVALID")
            with urllib.request.urlopen(
                base.API_PUBLIC+"/jobs/"+jid,timeout=20) as res:
                remote=json.load(res)
            for k in ("job_id","request_id","room_id"):
                if state.get(k) is not None and remote.get(k)!=state.get(k):
                    raise ValueError("CHECKPOINT_REMOTE_"+k.upper()+"_MISMATCH")
            return remote
        if state.get("submit_attempted") is True:
            # The old POST may have landed; the classifier owns lookup via
            # the same request ID. Do not invent a new request.
            return None
    return base.read_remote_for_batch(verified)


def safe_remote_view(remote):
    if remote is None:
        return {"status":"not_visible"}
    fields=("job_id","request_id","status","stage","result_ready",
            "result_sha256","chatgpt_send_confirmed",
            "assistant_reply_observed","error_code",
            "job_last_progress_at")
    return {k:remote.get(k) for k in fields}


def comparison(previous, current):
    """Two separate checks AND ten minutes without verified progress."""
    if not previous:
        return 1, False, "first_observation"
    if previous["verified"] != current["verified"] or (
            previous.get("first_missing") != current["first_missing"]):
        return 1, False, "verified_progress_changed"
    delta = current["observed_at"]-previous["observed_at"]
    if delta < MIN_INTERVAL_SECONDS:
        return previous.get("unchanged_checks",1), False, "same_window_too_soon"
    checks = previous.get("unchanged_checks",1)+1
    last_checkpoint_age = current["observed_at"]-current["checkpoint_at"]
    suspect = checks >= 2 and last_checkpoint_age >= STAGNATION_SECONDS
    return checks,suspect,("two_checks_and_ten_minutes_no_verified_growth"
                          if suspect else "observation_repeated_not_yet_stale")


def take_snapshot(client, previous, now=None):
    now = time.time() if now is None else now
    runs=base.relevant_runs(client)
    artifact=base.latest_artifact(client)
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        verified, missing=base.restore_checkpoint(client,artifact,root)
        original=base.source_rows()
        for number,row in verified.items():
            if (not 1 <= number <= len(original)
                    or str(row["id"])!=str(original[number-1]["문서 ID"])):
                raise ValueError("WATCHDOG_CHECKPOINT_SOURCE_ID_MISMATCH")
        try:
            remote=exact_remote_from_checkpoint(root,verified)
            remote_status=safe_remote_view(remote)
        except (OSError,ValueError,TimeoutError) as exc:
            # Network trouble is a detection signal, never permission to
            # replay a question or cancel in-progress work.
            remote_status={"status":"observation_error",
                           "type":type(exc).__name__}
    active=[r for r in runs if r.get("status") in base.ACTIVE]
    current=active[0] if active else None
    phase,job,step=active_phase(client,current)
    try:
        worker=worker_status()
        worker_view={
            "connected":worker.get("worker_connected") is True,
            "heartbeat":worker.get("worker_heartbeat_recent") is True,
            "bootstrap":worker.get("worker_bootstrap_ready") is True,
            "jobs":worker.get("worker_active_jobs_count"),
        }
    except (OSError,TimeoutError,ValueError) as exc:
        worker_view={"connected":None,"error":type(exc).__name__}
    sample={
        "version":1,
        "observed_at":now,
        "verified":len(verified),
        "first_missing":missing,
        "checkpoint_run":artifact["workflow_run"]["id"],
        "checkpoint_at":epoch(artifact["created_at"]),
        "classifier_run":current["id"] if current else None,
        "classifier_phase":phase,
        "classifier_job":job,
        "classifier_step":step,
        "worker":worker_view,
        "remote":remote_status,
    }
    checks,stale,reason=comparison(previous,sample)
    sample.update({"unchanged_checks":checks,
                   "suspected_stagnation":stale,
                   "decision_reason":reason})
    return sample,current,runs,artifact


def respond_safely(client,sample,active,artifact):
    """No fresh AI sends. Never cancel an uncertain in-flight response."""
    if sample["first_missing"] is None:
        return "verified_corpus_complete"
    if not sample["suspected_stagnation"]:
        return "healthy_or_not_proven_stale"
    print("WATCHDOG_TEN_MINUTE_NO_VERIFIED_PROGRESS",
          "VERIFIED",sample["verified"],
          "NEXT",sample["first_missing"],
          "RUN",sample["classifier_run"],
          "PHASE",sample["classifier_phase"],
          "REMOTE",sample["remote"].get("status"),
          flush=True)
    if not active:
        # The existing watchdog.monitor handles the no-active checkpoint
        # dispatch and repeated 500 with stable tokens. Do not double POST.
        return "restart_from_checkpoint_by_existing_monitor"
    if active["status"]!="in_progress":
        return "queued_worker_preserved"
    if sample["classifier_job"]=="worker_ready":
        if base.retire_shadowed_preflight(client,active,artifact):
            return "shadowed_preflight_cancelled_no_ai_was_sent"
        return "waiting_for_chrome_without_ai_send"
    if sample["classifier_job"]!="ai" or (
            sample["classifier_step"]!=base.CLASSIFY_STEP):
        return "active_nonclassification_step_preserved"
    remote=sample["remote"]
    if (remote.get("status")=="completed"
            and all(remote.get(k) is True for k in REMOTE_COMPLETED_FLAGS)):
        # The original 35-minute guard is lowered to 10 minutes ONLY after
        # two spaced check records and immutable source identity validation.
        return base.maybe_cancel_definitely_stuck(client,active,artifact)
    if remote.get("status") in ("running","queued"):
        return "remote_model_or_worker_active_do_not_duplicate"
    if remote.get("status") in ("stalled","unknown","failed") and (
            remote.get("chatgpt_send_confirmed") is True
            or remote.get("assistant_reply_observed") is True):
        return "delivery_uncertain_or_seen_do_not_duplicate"
    # For terminal delivery-unknown statuses leave the original job and its
    # evidence for the classifier's explicit audited recovery handler.
    return "remote_not_verifiably_complete_preserve_old_job"


def main():
    client=GithubClient(os.environ["GITHUB_REPOSITORY"],
                        os.environ["GH_TOKEN"])
    output=Path(os.environ.get("HITEL_WATCHDOG_STATE_FILE",
                             "/tmp/"+SAMPLE_FILE))
    output.parent.mkdir(parents=True,exist_ok=True)
    prior=prior_observation(client)
    sample,active,runs,artifact=take_snapshot(client,prior)
    # Write first, so any failure in an action retains the observation.
    output.write_text(json.dumps(sample,ensure_ascii=False,indent=2),
                      encoding="utf-8")
    print("WATCHDOG_DURABLE_FIVE_MINUTE_SAMPLE",
          "VERIFIED",sample["verified"],"NEXT",sample["first_missing"],
          "UNCHANGED_CHECKS",sample["unchanged_checks"],
          "STAGNANT",sample["suspected_stagnation"],
          "WHY",sample["decision_reason"],flush=True)
    response=respond_safely(client,sample,active,artifact)
    print("WATCHDOG_EVIDENCE_GATED_RECOVERY",response,flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",
                  encoding="utf-8") as f:
            f.write("Scribd checkpoint: "+str(sample["verified"])+
                    "; next: "+str(sample["first_missing"])+
                    "; stagnant checks: "+str(sample["unchanged_checks"])+
                    "; decision: "+response+"\n")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
