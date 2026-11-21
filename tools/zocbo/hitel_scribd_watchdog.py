#!/usr/bin/env python3
"""Five-minute external GitHub Actions watchdog for verified Scribd batches.

Never confuse a five-minute inspection cadence with a five-minute model timeout.
Do not cancel healthy Chrome/AI work. When no classifier run exists, restore the
most recent durable checkpoint and dispatch ONE next run with a stable token.
When an in-progress classifier is old, only cancel it if the exact deterministic
remote request is already verified COMPLETED (read-only proof). Next watchdog
will resume from the last durable verified batch without a second AI send.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import urllib.parse
import zipfile
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from hitel_dispatch_next_verified import GithubClient, handoff
from hitel_public_named_rooms_corpus import title_prompt
from hitel_scribd_ws_continue import SOURCE_SHA, load_verified, next_batch

WORKFLOW = "hitel-public-ai-corpus.yml"
ARTIFACT = "hitel-ai-18109-ws-recovery-checkpoint"
TOTAL = 18109
MINIMUM_SAVED = 1300
ACTIVE = {"queued", "in_progress", "pending", "requested", "waiting"}
SAFE_COMPLETED_FLAGS = ("result_ready", "chatgpt_send_confirmed", "assistant_reply_observed")
CLASSIFY_STEP = "Resume preserved AI answer or submit one signed scribd-18109 isolated HTTP batch"
API_PUBLIC = "https://hitel-integration-api-production.up.railway.app/integrations/v1/public"
STALE_COMPLETED_THRESHOLD_SECONDS = 35 * 60


def date_of(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def seconds_since(s: str, now=None) -> float:
    return ((now or dt.datetime.now(dt.timezone.utc)) - date_of(s)).total_seconds()


def github_listing(client: GithubClient, path: str, what: str):
    status, data = client.request("GET", path)
    if status != 200 or not isinstance(data, dict):
        raise RuntimeError(what + "_HTTP_" + str(status))
    return data


def relevant_runs(client: GithubClient):
    data = github_listing(
        client, "actions/workflows/" + WORKFLOW + "/runs?per_page=100",
        "WORKFLOW_RUNS_LISTING")
    return sorted(
        (x for x in data.get("workflow_runs", [])
         if x.get("head_branch") == "main" and x.get("event")
         in ("push", "workflow_dispatch")),
        key=lambda r: r["created_at"], reverse=True)


def latest_artifact(client: GithubClient):
    data = github_listing(
        client, "actions/artifacts?name=" + ARTIFACT + "&per_page=100",
        "VERIFIED_CHECKPOINT_LISTING")
    matching = [x for x in data.get("artifacts", [])
                if x.get("name") == ARTIFACT and not x.get("expired")
                and x.get("workflow_run", {}).get("head_branch") == "main"]
    if not matching:
        raise RuntimeError("VERIFIED_CHECKPOINT_ARTIFACT_MISSING")
    return max(matching, key=lambda x: x["created_at"])


def download_exact_artifact(client: GithubClient, artifact_id:int, root:Path):
    """Restore by immutable artifact ID; never accidentally load a rerun artifact.

    GitHub's 302 redirects to signed Azure blob storage. Never forward its
    GitHub Authorization header to a different hostname.
    """
    if not isinstance(artifact_id,int) or artifact_id<=0:
        raise ValueError("INVALID_WATCHDOG_ARTIFACT_ID")
    url=(f"https://api.github.com/repos/{client.repository}"
         f"/actions/artifacts/{artifact_id}/zip")
    request=urllib.request.Request(url,headers={
        "Authorization":"Bearer "+client.token,
        "Accept":"application/vnd.github+json",
        "X-GitHub-Api-Version":"2022-11-28",
    })
    class StripCrossHostAuth(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            redirected=super().redirect_request(req,fp,code,msg,headers,newurl)
            if redirected and (urllib.parse.urlsplit(newurl).hostname
                               !=urllib.parse.urlsplit(req.full_url).hostname):
                for key in ("Authorization","Accept","X-GitHub-Api-Version"):
                    redirected.remove_header(key)
            return redirected
    with urllib.request.build_opener(StripCrossHostAuth()).open(
            request,timeout=60) as response:
        payload=response.read(40_000_001)
    if len(payload)>40_000_000:
        raise RuntimeError("WATCHDOG_ARTIFACT_TOO_LARGE")
    root=root.resolve()
    root.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        entries=archive.infolist()
        if not entries:
            raise RuntimeError("WATCHDOG_ARTIFACT_EMPTY")
        for ent in entries:
            target=(root/ent.filename).resolve()
            if not target.is_relative_to(root):
                raise ValueError("WATCHDOG_ARTIFACT_ZIP_TRAVERSAL")
            if (ent.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("WATCHDOG_ARTIFACT_SYMLINK_FORBIDDEN")
        archive.extractall(root)
    print("WATCHDOG_RESTORED_EXACT_ARTIFACT",artifact_id,flush=True)


def restore_checkpoint(client: GithubClient, artifact, root: Path):
    source_run = artifact["workflow_run"]["id"]
    download_exact_artifact(client,int(artifact["id"]),root)
    # Integrity and id checks are repeated by the classifier before any send.
    files = sorted((root / "completed").glob("*.json"))
    verified = {}
    for file in files:
        for row in json.loads(file.read_text("utf-8"))["rows"]:
            n = int(row["no"])
            if not 1 <= n <= TOTAL or n in verified:
                raise ValueError("CHECKPOINT_VERIFIED_DUPLICATE_OR_BAD_RANGE")
            verified[n] = row
    if len(verified) < MINIMUM_SAVED:
        raise ValueError("CHECKPOINT_VERIFIED_COUNT_REGRESSED")
    if list((root / "skipped").glob("*.json")):
        raise ValueError("CHECKPOINT_HAS_UNVERIFIED_SKIPPED_ROWS")
    missing = next((i for i in range(1, TOTAL + 1) if i not in verified), None)
    print("WATCHDOG_DURABLE_CHECKPOINT",
          "SOURCE_RUN", source_run,"ARTIFACT_ID",artifact["id"],
          "VERIFIED", len(verified),"NEXT_MISSING", missing,flush=True)
    return verified, missing


def source_rows():
    pieces = sorted(Path("data/raw_18109").glob("part_*.csv"))
    if len(pieces) != 20:
        raise ValueError("SOURCE_18109_PART_COUNT_CHANGED")
    joined = "".join(x.read_text("utf-8") for x in pieces)
    original = b"\xef\xbb\xbf" + joined.replace("\n", "\r\n").encode("utf-8")
    if hashlib.sha256(original).hexdigest() != SOURCE_SHA:
        raise ValueError("SOURCE_18109_DIGEST_CHANGED")
    rows = list(csv.DictReader(io.StringIO(original.decode("utf-8-sig"),
                                            newline="")))
    if len(rows) != TOTAL:
        raise ValueError("SOURCE_18109_SIZE_CHANGED")
    for n, row in enumerate(rows, 1):
        row["번호"] = n
    return rows


def read_remote_for_batch(verified):
    rows = source_rows()
    # Verify each persisted document ID before deciding to cancel any run.
    for number, row in verified.items():
        if str(rows[number - 1]["문서 ID"]) != str(row["id"]):
            raise ValueError("CHECKPOINT_SOURCE_ID_MISMATCH")
    batch = next_batch(rows, verified)
    if not batch:
        return None
    key = "%05d-%05d" % (batch[0]["번호"], batch[-1]["번호"])
    digest = hashlib.sha256(title_prompt(batch).encode("utf-8")).hexdigest()
    request_id = "scribd18109-" + key + "-" + digest[:32]
    url = API_PUBLIC + "/requests/" + request_id
    try:
        with urllib.request.urlopen(url, timeout=20) as res:
            pointer = json.load(res)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    if pointer.get("request_id") != request_id:
        raise ValueError("REMOTE_REQUEST_ID_CHANGED")
    job_id = pointer.get("job_id")
    if not isinstance(job_id, str) or not job_id.startswith("job_"):
        raise ValueError("REMOTE_JOB_ID_INVALID")
    with urllib.request.urlopen(API_PUBLIC + "/jobs/" + job_id,
                                timeout=20) as res:
        remote = json.load(res)
    if remote.get("job_id") != job_id or remote.get("request_id") != request_id:
        raise ValueError("REMOTE_JOB_REFERENCE_CHANGED")
    return remote


def maybe_cancel_definitely_stuck(client: GithubClient, run, artifact,
                                  threshold_seconds=STALE_COMPLETED_THRESHOLD_SECONDS):
    """Never terminate generation just because no new GitHub log has appeared."""
    run_id = int(run["id"])
    status = run["status"]
    if status != "in_progress":
        return "queued_or_waiting"
    jobs = github_listing(client, "actions/runs/%d/jobs?per_page=100" % run_id,
                          "ACTIVE_JOB_STEPS")
    ai = next((j for j in jobs.get("jobs", []) if j.get("name") == "ai"), None)
    if not ai:
        return "worker_waiting"
    classify = next((s for s in ai.get("steps", [])
                     if s.get("name") == CLASSIFY_STEP), None)
    if not classify or classify.get("status") != "in_progress":
        return "not_in_ai_classification"
    started = classify.get("started_at")
    if not started or seconds_since(started) < threshold_seconds:
        return "generating_or_observing_answer"
    # Only look inside durable previous verified checkpoint AFTER a long
    # classification. Nothing is submitted to ChatGPT by the watchdog.
    with tempfile.TemporaryDirectory() as tmp:
        verified, _ = restore_checkpoint(client, artifact, Path(tmp))
        remote = read_remote_for_batch(verified)
    if not remote:
        return "no_matching_remote_job_preserve_run"
    if (remote.get("status") != "completed"
            or any(remote.get(k) is not True for k in SAFE_COMPLETED_FLAGS)):
        return ("remote_not_verified_preserve_run_" +
                str(remote.get("status", "unknown"))[:24])
    # The exact remote job is independently complete; restarting this client
    # can only fetch that same deterministic request_id. Not a new AI prompt.
    status, _ = client.request("POST",
        "actions/runs/%d/cancel" % run_id)
    if status not in (202, 409):
        raise RuntimeError("SAFE_STALE_CANCELLATION_HTTP_" + str(status))
    print("WATCHDOG_SAFE_CANCEL_REMOTE_ALREADY_COMPLETED",
          "RUN", run_id, "HTTP", status, flush=True)
    return "safe_cancelled_verified_remote"


def retire_shadowed_preflight(client: GithubClient, run, artifact):
    """Cancel ONLY a provably superseded wait-only run that never sent AI.

    GitHub can leave an old worker_ready wait alive after newer runs have
    already verified and archived later batches. That zombie would otherwise
    be counted as 'active' forever, blocking recovery after a later failure.
    Require a checkpoint CREATED AFTER this run, age >10 min, the AI job
    never started, and exactly the worker_ready wait still active.
    No cancellation of any job with an AI phase started, no matter how old.
    """
    if run.get("status") != "in_progress":
        return False
    if seconds_since(run["created_at"]) < 10 * 60:
        return False
    if seconds_since(artifact["created_at"]) >= seconds_since(run["created_at"]):
        return False
    if artifact.get("workflow_run", {}).get("id") == run["id"]:
        return False
    jobs = github_listing(client,
                          "actions/runs/%d/jobs?per_page=100" % run["id"],
                          "STALE_WAIT_ONLY_JOB_STEPS")
    all_jobs = jobs.get("jobs", [])
    ai = next((j for j in all_jobs if j.get("name") == "ai"), None)
    if ai is not None:
        # Even 'queued' AI could have begun asynchronously; fail closed.
        return False
    ready = next((j for j in all_jobs if j.get("name") == "worker_ready"), None)
    if not ready or ready.get("status") != "in_progress":
        return False
    stages = ready.get("steps", [])
    active = [step.get("name") for step in stages
              if step.get("status") == "in_progress"]
    if active != ["Verify currently connected corrected Web2API worker, without pinning its run ID"]:
        return False
    code, _ = client.request("POST", "actions/runs/%d/cancel" % run["id"])
    if code not in (202, 409):
        raise RuntimeError("SHADOWED_PREFLIGHT_CANCEL_HTTP_" + str(code))
    print("WATCHDOG_SAFE_CANCEL_SHADOWED_NO_AI_RUN", run["id"],
          "NEWER_CHECKPOINT", artifact["workflow_run"]["id"],
          "HTTP", code, flush=True)
    return True


def monitor(client: GithubClient):
    runs = relevant_runs(client)
    if not runs:
        raise RuntimeError("NO_BASELINE_CLASSIFIER_RUN_FOUND")
    active = [r for r in runs if r.get("status") in ACTIVE]
    print("WATCHDOG_FIVE_MINUTE_CHECK", "TOTAL_RUNS", len(runs),
          "ACTIVE", [r["id"] for r in active],
          "LATEST", runs[0]["id"], runs[0]["status"], flush=True)
    if active:
        # Active jobs are NEVER preempted by normal five-minute monitoring.
        # Only the safe, separately evidenced 35-minute case may cancel.
        newest = active[0]
        print("WATCHDOG_ACTIVE_RUN", newest["id"],
              "AGE_MIN", round(seconds_since(newest["created_at"]) / 60, 1),
              flush=True)
        if newest["status"] == "in_progress":
            artifact = latest_artifact(client)
            if retire_shadowed_preflight(client, newest, artifact):
                return "shadowed_wait_only_run_cancel_requested"
            decision = maybe_cancel_definitely_stuck(client, newest, artifact)
            print("WATCHDOG_ACTIVE_DECISION", decision, flush=True)
        return "active_safe"

    # No active/pending/queued workflow. Recover from last verified checkpoint
    # rather than guessing that the previous action's partial output is valid.
    artifact = latest_artifact(client)
    with tempfile.TemporaryDirectory() as tmp:
        verified, missing = restore_checkpoint(client, artifact, Path(tmp))
    if missing is None:
        print("WATCHDOG_COMPLETE_VERIFIED_ALL", TOTAL, flush=True)
        return "complete"

    newest = runs[0]
    # Give GitHub's delayed queue/index a grace period after a terminal run.
    if seconds_since(newest["updated_at"]) < 120:
        print("WATCHDOG_RECENT_TERMINAL_RUN_QUEUE_GRACE", newest["id"],
              "NEXT", missing, flush=True)
        return "grace"
    # Stable token across watchdog retries of the same terminal predecessor,
    # so uncertain GitHub dispatch 500 cannot create multiple classifier jobs.
    token = "watchdog-" + str(newest["id"])
    status, child = handoff(client, token)
    print("WATCHDOG_RECOVERY_DISPATCH", status,
          "CHILD_RUN", child, "NEXT_MISSING", missing, flush=True)
    return status


def main():
    client = GithubClient(os.environ["GITHUB_REPOSITORY"],
                          os.environ["GH_TOKEN"])
    result = monitor(client)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("Scribd five-minute watchdog: " + result + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
