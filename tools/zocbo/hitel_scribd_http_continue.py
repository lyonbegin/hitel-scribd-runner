#!/usr/bin/env python3
"""Resume Scribd classification with the proven HITEL /public/chat HTTP path.

One public POST per exact batch and immutable request_id; subsequent runs
only GET /requests or /jobs. Never replay an uncertain ChatGPT submission.
All previously verified corpus rows and WebSocket audit files are retained.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import os
import urllib.parse
import urllib.request
import time
import urllib.error
from pathlib import Path

from hitel_public_named_rooms_corpus import (
    BASE, HTTP, call, output_file, read_completed_result, save, title_prompt, validated_rows)
from hitel_scribd_ws_continue import SOURCE_SHA, load_verified, next_batch

API="/integrations/v1/public"
OLD_1101_JOB="job_0beb067740a64d488431c274a5d0a69a"
OLD_1101_ROOM="HITEL-SCRIBD-18109-REPAIRED-VENDOR-20261121-01101-01120"
OLD_1101_KEY="01101-01120"


def validate_old_1101(out: Path, key: str, digest: str, ids: list[dict]) -> None:
    """Explicitly audit the prior stalled/unknown job, not a verified result.

    The user authorized retiring the previous GitHub runs and restarting
    using the now-proven HTTP test endpoint. This may repeat a request whose
    previous delivery could not be determined, so retain that fact in audit.
    """
    if key!=OLD_1101_KEY:
        return
    audit=out/"http"/"old_ws_1101_audit.json"
    if audit.exists():
        saved=json.loads(audit.read_text("utf-8"))
        if saved.get("key")!=key or saved.get("digest")!=digest or saved.get("source_ids")!=ids:
            raise ValueError("LEGACY_AUDIT_SCOPE_CHANGED")
        return
    oldfile=out/"ws"/(key+".json")
    active=out/"ws"/"active_batch.json"
    if not oldfile.exists() or not active.exists():
        raise ValueError("ORIGINAL_1101_WS_CHECKPOINT_MISSING")
    state=json.loads(oldfile.read_text("utf-8"))
    pointer=json.loads(active.read_text("utf-8"))
    if (state.get("job_id")!=OLD_1101_JOB or state.get("room_name")!=OLD_1101_ROOM
        or state.get("text_sha256")!=digest
        or pointer.get("key")!=key or pointer.get("prompt_sha256")!=digest
        or pointer.get("source_ids")!=ids):
        raise ValueError("ORIGINAL_1101_WS_SCOPE_MISMATCH")
    code,remote=call(API+"/jobs/"+OLD_1101_JOB)
    if (code!=200 or remote.get("job_id")!=state.get("job_id")
        or remote.get("request_id")!=state.get("request_id")
        or remote.get("room_id")!=state.get("room_id")
        or remote.get("result_ready") is not False
        or remote.get("status") not in ("stalled","unknown")
        or remote.get("chatgpt_send_confirmed") is True
        or remote.get("assistant_reply_observed") is True):
        raise ValueError("LEGACY_1101_MAY_HAVE_VERIFIED_RESPONSE")
    save(audit,{"key":key,"digest":digest,"source_ids":ids,
                "old_client":state,"old_active":pointer,
                "old_remote":{k:remote.get(k) for k in (
                    "job_id","request_id","room_id","status","stage","error_code",
                    "result_ready","chatgpt_send_confirmed","assistant_reply_observed")},
                "prior_delivery_unknown":True,"user_authorized_http_recovery":True,
                "prior_job_not_counted_completed":True})
    print("OLD_1101_REMOTE_AUDITED_NO_VERIFIED_REPLY",OLD_1101_JOB,flush=True)


def fetch_existing(request_id: str):
    try:
        code,obj=call(API+"/requests/"+request_id)
    except urllib.error.HTTPError as exc:
        if exc.code==404:
            return None
        raise
    if code!=200 or obj.get("request_id")!=request_id:
        raise ValueError("REQUEST_LOOKUP_IDENTITY_MISMATCH")
    return obj


def isolated_chat_once(state: dict, text: str):
    """Task-bound POST via exact GitHub Actions producer OIDC, never shared /chat.

    Tokens are short-lived and never persisted, printed or sent to GitHub
    artifact files. No signed producer token means no submission.
    """
    if state.get("task_id")!="scribd-18109":
        raise ValueError("INVALID_ISOLATED_TASK_SCOPE")
    token_url=os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL")
    token_secret=os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not token_url or not token_secret:
        raise RuntimeError("GITHUB_OIDC_PRODUCER_NOT_AVAILABLE")
    audience="urn:lyonbegin:procureflow:hitel-isolated-task-submit"
    separator="&" if "?" in token_url else "?"
    url=token_url+separator+"audience="+urllib.parse.quote(audience,safe="")
    signed=urllib.request.Request(url,headers={
        "Authorization":"Bearer "+token_secret,"Accept":"application/json"})
    with HTTP.open(signed,timeout=30) as response:
        oidc=json.load(response).get("value")
    if not isinstance(oidc,str) or len(oidc)<50:
        raise RuntimeError("GITHUB_OIDC_PRODUCER_TOKEN_MISSING")
    raw=json.dumps({"request_id":state["request_id"],
                    "room_name":state["room_name"],"text":text},
                   ensure_ascii=False).encode("utf-8")
    endpoint=BASE+API+"/isolated/tasks/scribd-18109/chat"
    req=urllib.request.Request(endpoint,data=raw,method="POST",
           headers={"Content-Type":"application/json",
                    "Accept":"application/json",
                    "X-HITEL-PRODUCER-OIDC":oidc})
    with HTTP.open(req,timeout=60) as response:
        return response.status,json.load(response)


def expected_server_room_name(state:dict):
    task=state.get("task_id")
    if task=="scribd-18109":
        return "HITEL-ISOLATED-SCRIBD-18109-"+state["room_name"]
    if task is None:
        return state["room_name"]
    raise ValueError("INVALID_TASK_IN_CHECKPOINT")


def allow_exact_prior_http_403_rejected_attempt(statefile:Path,state:dict):
    """One audited recovery of a proven PRE-DB-write producer OIDC 403 only.

    GitHub run 44887496031 was a push event. Railway rejects such producer
    OIDC before allocating jobs. The exact attempted 2181-2200 request
    received HTTP 403, and public /requests returned 404. Reuse the SAME
    immutable request_id and task-specific room once on workflow_dispatch.
    Never relax this for a 5xx, transport timeout or delivery uncertainty.
    """
    digest="c58ef9aed39a78d6ed52838df6a2d4b5a1974f6441939df40ac8175790f18fb1"
    if not (
        state.get("key")=="02181-02200"
        and state.get("digest")==digest
        and state.get("task_id")=="scribd-18109"
        and state.get("request_id")=="scribd18109-02181-02200-"+digest[:32]
        and state.get("room_name")=="HITEL-SCRIBD-18109-PROVEN-HTTP-20261121-02181-02200"
        and [int(x["no"]) for x in state.get("source_ids",[])]==list(range(2181,2201))
        and state.get("submit_attempted") is True
        and not state.get("job_id")
        and os.environ.get("GITHUB_EVENT_NAME")=="workflow_dispatch"
    ):
        raise RuntimeError("POST_DELIVERY_UNCERTAIN_LOOKUP_404_REFUSE_DUPLICATE_SEND")
    auditfile=statefile.parent/"producer_rejections"/"02181-02200.json"
    if auditfile.exists():
        raise RuntimeError("ALREADY_RECOVERED_PRIOR_403_DO_NOT_RESEND")
    save(auditfile,{
        "key":state["key"],"digest":state["digest"],
        "request_id":state["request_id"],"room_name":state["room_name"],
        "source_ids":state["source_ids"],
        "task_id":"scribd-18109",
        "previous_workflow_run":44887496031,
        "previous_server_rejection":"HTTP_403_BEFORE_DB_INSERT",
        "remote_request_lookup_http":404,
        "user_authorized_new_isolated_task_recovery":True,
        "single_recovery_only":True,
    })
    state["submit_attempted"]=False
    state["prior_rejected_403_audit"]=str(auditfile.relative_to(statefile.parent.parent))
    save(statefile,state)
    print("AUDITED_PRE_SEND_403_SAME_REQUEST_ID_RECOVERY_ONE_TIME",
          state["key"],flush=True)


def ensure_one_http_job(statefile: Path, state: dict, text: str) -> dict:
    """Persist attempt before network I/O. A lost POST reply is never resent."""
    if state.get("job_id"):
        return state
    request_id=state["request_id"]
    previous=fetch_existing(request_id)
    if previous is not None:
        job=previous
        print("RECOVER_EXISTING_HTTP_JOB_NO_RESEND",job["job_id"],flush=True)
    else:
        if state.get("submit_attempted") is True:
            allow_exact_prior_http_403_rejected_attempt(statefile,state)
        # This atomic write happens BEFORE any request can reach the API.
        state["submit_attempted"]=True
        save(statefile,state)
        if state.get("task_id")=="scribd-18109":
            code,job=isolated_chat_once(state,text)
        else:
            code,job=call(API+"/chat",{"request_id":request_id,
                                     "room_name":state["room_name"],"text":text})
        if code!=202 or job.get("accepted") is not True:
            raise ValueError("HTTP_CHAT_NOT_ACCEPTED")
        print("PUBLIC_HTTP_CHAT_ACCEPTED_ONCE",job.get("job_id"),flush=True)
    if (job.get("request_id")!=request_id or
        (job.get("room_name") is not None and
         job.get("room_name")!=expected_server_room_name(state)) or
        not str(job.get("job_id","")).startswith("job_") or
        not str(job.get("room_id","")).startswith("room_")):
        raise ValueError("HTTP_ACCEPTED_JOB_IDENTITY_MISMATCH")
    # GET /requests returns no room name. Match the job's persisted room name
    # on GET /jobs before accepting an existing request for a future poll.
    if previous is not None:
        status_code,status=call(API+"/jobs/"+job["job_id"])
        if (status_code!=200 or status.get("room_name")!=expected_server_room_name(state)
            or status.get("room_id")!=job["room_id"]):
            raise ValueError("HTTP_EXISTING_REQUEST_ROOM_MISMATCH")
    state.update({"job_id":job["job_id"],"room_id":job["room_id"],
                  "status":"accepted"})
    save(statefile,state)
    return state


def await_http_reply(statefile:Path,state:dict):
    """GET only: worker can rotate, and a lost reply never causes a new POST."""
    while True:
        code,remote=call(API+"/jobs/"+state["job_id"])
        if (code!=200 or any(remote.get(k)!=state.get(k) for k in
           ("job_id","request_id","room_id"))):
            raise ValueError("HTTP_RESULT_JOB_IDENTITY_MISMATCH")
        status=remote.get("status")
        if status=="completed":
            if (remote.get("result_ready") is not True or
                remote.get("chatgpt_send_confirmed") is not True or
                remote.get("assistant_reply_observed") is not True):
                raise ValueError("HTTP_COMPLETION_EVIDENCE_MISSING")
            answer=read_completed_result(state["job_id"],remote)
            state.update({"status":"completed",
                          "answer_sha256":hashlib.sha256(answer.encode("utf-8")).hexdigest()})
            save(statefile,state)
            return answer,remote
        if (state.get("task_id")=="scribd-18109"
                and status=="stalled"
                and remote.get("error_code")=="WORKER_NOT_ACTIVE_FOR_JOB"):
            # The legacy read-only /public/jobs view checks the SHARED
            # web2api_active_jobs set, which does not hold task-isolated
            # Chrome jobs. This is NOT an upstream model failure when
            # the signed dedicated Scribd worker is actively processing.
            # Poll the original job only; never POST a second request.
            task_code,task=call(API+"/isolated/tasks/scribd-18109/status")
            if (task_code==200 and task.get("task_id")=="scribd-18109"
                    and task.get("worker_connected") is True
                    and task.get("worker_heartbeat_recent") is True
                    and task.get("worker_active_jobs_count",0)>0):
                print("ISOLATED_TASK_ACTIVE_LEGACY_STATUS_FALSE_STALL_GET_ONLY",
                      state["job_id"],flush=True)
                time.sleep(10)
                continue
        if status in ("queued","running"):
            print("HTTP_JOB_PROGRESS",state["job_id"],status,
                  str(remote.get("stage",""))[:90],flush=True)
            time.sleep(10)
            continue
        state.update({"status":"unverified","remote_status":status,
                      "remote_error_code":remote.get("error_code")})
        save(statefile,state)
        print("HTTP_REPLY_UNVERIFIED_NO_AUTOMATIC_RESEND",
              state["job_id"],status,remote.get("error_code"),flush=True)
        raise RuntimeError("HTTP_JOB_NOT_VERIFIED_KEEP_CHECKPOINT")



def recovery_after_verified_worker_disconnect(
        out: Path, key: str, digest: str, ids: list[dict],
        original_file: Path, original: dict, request_id: str,
        room_name: str):
    """Explicit operator-requested restart of an interrupted AI batch, ONCE.

    Preserve the exact old request as immutable evidence. No reply from a
    stalled job may count as verified. A fresh, uniquely scoped request can
    be created only for the literal WORKER_CONNECTION_LOST terminal state.
    Earlier ChatGPT delivery remains unknown and is audited explicitly.
    If any prior send/reply was observed, refuse automatic duplication.
    """
    recoveryfile = out / "http" / "worker_recoveries" / (key + ".json")
    if recoveryfile.exists():
        state = json.loads(recoveryfile.read_text("utf-8"))
        if (state.get("key") != key or state.get("digest") != digest
                or state.get("source_ids") != ids
                or state.get("request_id") != request_id + "-recovery1"
                or state.get("room_name") != room_name + "-RECOVERY1"
                or state.get("recovery_from_job") != original.get("job_id")
                or state.get("prior_delivery_unknown") is not True):
            raise ValueError("WORKER_RECOVERY_CHECKPOINT_SCOPE_MISMATCH")
        return recoveryfile, state

    # Existing uncertain jobs are never automatically replayed unless an
    # exact terminal worker-disconnect failure has been confirmed by Railway.
    if (original.get("status") != "unverified"
            or original.get("remote_status") != "stalled"
            or original.get("remote_error_code") != "WORKER_CONNECTION_LOST"
            or not original.get("job_id")):
        return original_file, original
    code, remote = call(API + "/jobs/" + original["job_id"])
    if (code != 200 or remote.get("job_id") != original["job_id"]
            or remote.get("request_id") != request_id
            or remote.get("room_name") != room_name):
        raise ValueError("ORIGINAL_DISCONNECTED_REQUEST_IDENTITY_MISMATCH")
    # Another process might have completed the original; in that case
    # preserve it and allow the ordinary same-ID read-only path to verify.
    if remote.get("status") == "completed":
        return original_file, original
    if (remote.get("status") not in ("stalled", "unknown")
            or remote.get("error_code") != "WORKER_CONNECTION_LOST"
            or remote.get("result_ready") is not False
            or remote.get("chatgpt_send_confirmed") is True
            or remote.get("assistant_reply_observed") is True):
        raise RuntimeError("WORKER_LOSS_RECOVERY_NOT_SAFE_NO_REPOST")
    # One fresh idempotent request in a different room. It may repeat an
    # unobserved earlier send. Keep the fact available for audit.
    state = {
        "key": key, "digest": digest, "source_ids": ids,
        "request_id": request_id + "-recovery1",
        "room_name": room_name + "-RECOVERY1",
        "status": "prepared", "submit_attempted": False,
        "recovery_from_job": original["job_id"],
        "prior_delivery_unknown": True,
        "prior_error_code": "WORKER_CONNECTION_LOST",
    }
    save(recoveryfile, state)
    print("AUDITED_WORKER_LOSS_RECOVERY_PREPARED_ONCE", key,
          "PRIOR_JOB", original["job_id"],
          "PRIOR_SEND_UNCONFIRMED", flush=True)
    return recoveryfile, state


MAX_SIGNED_TASK_RESTARTS=8
MIN_TERMINAL_IDLE_SECONDS=300

def recover_signed_task_only_after_terminal_disconnect(
        out:Path,key:str,digest:str,ids:list[dict],
        original_file:Path, original:dict,
        current_file:Path,current:dict,
        request_id:str,room_name:str):
    """User-authorized Scribd-only audited recovery; never hide unknown delivery.

    Every attempt has a separate immutable room/request ID and an audit link
    to the previous job. No attempt is made while ChatGPT may still be active,
    while an answer is observed, or before a quiet five-minute interval.
    """
    if current.get("task_id")!="scribd-18109":
        return current_file,current
    if current.get("status")!="unverified" or current.get("remote_status") not in ("stalled","unknown"):
        return current_file,current
    if current.get("remote_error_code") not in ("UPSTREAM_DELIVERY_UNKNOWN","WORKER_CONNECTION_LOST"):
        return current_file,current
    if not current.get("job_id"):
        return current_file,current
    code,remote=call(API+"/jobs/"+current["job_id"])
    if code!=200 or any(remote.get(k)!=current.get(k) for k in ("job_id","request_id","room_id")):
        raise ValueError("SIGNED_RECOVERY_PREVIOUS_REMOTE_IDENTITY_MISMATCH")
    if remote.get("status")=="completed":
        print("SIGNED_RECOVERY_PREVIOUS_COMPLETED_REUSE_SAME_REQUEST",current["job_id"],flush=True)
        return current_file,current
    if (remote.get("status") not in ("stalled","unknown")
            or remote.get("error_code") not in ("UPSTREAM_DELIVERY_UNKNOWN","WORKER_CONNECTION_LOST")
            or remote.get("result_ready") is not False
            or remote.get("chatgpt_send_confirmed") is True
            or remote.get("assistant_reply_observed") is True):
        raise RuntimeError("SIGNED_RECOVERY_SEND_OR_REPLY_POSSIBLY_OBSERVED_NO_REPOST")
    observed_at=remote.get("updated_at")
    if not isinstance(observed_at,(int,float)):
        raise RuntimeError("SIGNED_RECOVERY_MISSING_REMOTE_TIMESTAMP")
    # Some versions expose milliseconds, others seconds.
    observed_seconds=observed_at/1000 if observed_at>10**11 else observed_at
    if time.time()-observed_seconds<MIN_TERMINAL_IDLE_SECONDS:
        raise RuntimeError("SIGNED_RECOVERY_TERMINAL_NOT_IDLE_FIVE_MINUTES")
    status_code,task=call(API+"/isolated/tasks/scribd-18109/status")
    if (status_code!=200 or task.get("task_id")!="scribd-18109"
            or task.get("worker_connected") is not False
            or task.get("worker_heartbeat_recent") is not False):
        raise RuntimeError("SIGNED_RECOVERY_WORKER_STILL_PRESENT_NO_REPOST")
    # Even if the prior worker disappeared before acknowledging send, delivery
    # is not provably absent. Audit this explicit user-approved one-time
    # handoff instead of claiming no duplication risk.
    previous_sequence=int(current.get("recovery_sequence",0))
    if previous_sequence<0 or previous_sequence>=MAX_SIGNED_TASK_RESTARTS:
        raise RuntimeError("SIGNED_RECOVERY_RETRY_BUDGET_EXHAUSTED")
    next_sequence=previous_sequence+1
    next_key=(key+".json" if next_sequence==1
              else key+f"-recovery{next_sequence}.json")
    target=out/"http"/"worker_recoveries"/next_key
    next_id=request_id+f"-recovery{next_sequence}"
    next_room=room_name+f"-RECOVERY{next_sequence}"
    if target.exists():
        existing=json.loads(target.read_text("utf-8"))
        if (existing.get("key")!=key or existing.get("digest")!=digest
                or existing.get("source_ids")!=ids
                or existing.get("request_id")!=next_id
                or existing.get("room_name")!=next_room
                or existing.get("recovery_from_job")!=current["job_id"]
                or existing.get("task_id")!="scribd-18109"
                or existing.get("recovery_sequence")!=next_sequence):
            raise ValueError("SIGNED_RECOVERY_CHECKPOINT_REPLAY_SCOPE_MISMATCH")
        return target,existing
    state={
        "key":key,"digest":digest,"source_ids":ids,
        "request_id":next_id,"room_name":next_room,
        "task_id":"scribd-18109",
        "status":"prepared","submit_attempted":False,
        "recovery_from_job":current["job_id"],
        "recovery_sequence":next_sequence,
        "prior_delivery_unknown":True,
        "prior_error_code":remote["error_code"],
        "prior_result_ready":False,
        "prior_send_confirmed":remote.get("chatgpt_send_confirmed"),
        "prior_reply_observed":remote.get("assistant_reply_observed"),
        "prior_updated_at":observed_at,
        "recovered_under_user_approved_disconnect_policy":True,
    }
    save(target,state)
    print("SIGNED_SCRIBD_DISCONNECT_RECOVERY_AUDITED",
          "BATCH",key,"ATTEMPT",next_sequence,
          "OLD_JOB",current["job_id"],
          "OLD_SEND_UNKNOWN_POSSIBLE_DUPLICATE",flush=True)
    return target,state


def run_one(rows:list[dict],out:Path) -> int:
    verified=load_verified(rows,out)
    batch=next_batch(rows,verified)
    if not batch:
        output_file(rows,out)
        print("COMPLETE_VERIFIED_ALL",len(verified),flush=True)
        return 0
    key=f'{batch[0]["번호"]:05d}-{batch[-1]["번호"]:05d}'
    ids=[{"no":a["번호"],"id":str(a["문서 ID"])} for a in batch]
    question=title_prompt(batch)
    digest=hashlib.sha256(question.encode("utf-8")).hexdigest()
    if len(question)>24000:
        raise ValueError("PROMPT_EXCEEDS_API_LIMIT")
    validate_old_1101(out,key,digest,ids)
    statefile=out/"http"/(key+".json")
    request_id="scribd18109-"+key+"-"+digest[:32]
    room_name="HITEL-SCRIBD-18109-PROVEN-HTTP-20261121-"+key
    if statefile.exists():
        state=json.loads(statefile.read_text("utf-8"))
        if (state.get("key")!=key or state.get("digest")!=digest
            or state.get("source_ids")!=ids
            or state.get("request_id")!=request_id
            or state.get("room_name")!=room_name
            or state.get("task_id") not in (None,"scribd-18109")):
            raise ValueError("HTTP_CHECKPOINT_SCOPE_CHANGED")
    else:
        state={"key":key,"digest":digest,"source_ids":ids,
               "request_id":request_id,"room_name":room_name,
               "task_id":os.environ.get("HITEL_ISOLATED_TASK_ID") or None,
               "status":"prepared","submit_attempted":False}
        save(statefile,state)
    original_file,original=statefile,state
    statefile,state=recovery_after_verified_worker_disconnect(
        out,key,digest,ids,statefile,state,request_id,room_name)
    for _ in range(MAX_SIGNED_TASK_RESTARTS+1):
        nextfile,nextstate=recover_signed_task_only_after_terminal_disconnect(
            out,key,digest,ids,original_file,original,statefile,state,
            request_id,room_name)
        if nextfile==statefile or nextstate.get("status")!="unverified":
            statefile,state=nextfile,nextstate
            break
        statefile,state=nextfile,nextstate
    else:
        raise RuntimeError("SIGNED_RECOVERY_CHAIN_FAILED_CLOSED")
    state=ensure_one_http_job(statefile,state,question)
    answer,remote=await_http_reply(statefile,state)
    identity_repair_audit=[]
    parsed=validated_rows(answer,batch,identity_repair_audit)
    dest=out/"completed"/(key+".json")
    if dest.exists():
        raise ValueError("REFUSE_OVERWRITE_VERIFIED_RESULTS")
    save(dest,{"rows":parsed,"job_id":state["job_id"],"room_id":state["room_id"],
               "request_id":request_id,
               "transport":("HITEL_TASK_ISOLATED_HTTP_OIDC"
                            if state.get("task_id")=="scribd-18109"
                            else "HITEL_PUBLIC_HTTP_PROVEN_E2E"),
               "verified_reply_sha256":remote["result_sha256"],
               "source_id_repairs":identity_repair_audit,
               "source_id_repair_count":len(identity_repair_audit)})
    summary=output_file(rows,out)
    if summary["verified_ai_completed"]!=len(verified)+len(parsed):
        raise ValueError("VERIFIED_TOTAL_MISMATCH")
    print("HTTP_VERIFIED_BATCH",key,"NEW",len(parsed),
          "TOTAL_VERIFIED",summary["verified_ai_completed"],
          "REMAINING",len(rows)-summary["verified_ai_completed"],flush=True)
    return 0


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--out",required=True)
    o=p.parse_args()
    data=Path(o.input).read_bytes()
    if hashlib.sha256(data).hexdigest()!=SOURCE_SHA:
        raise ValueError("ORIGINAL_18109_CORPUS_SHA256_CHANGED")
    rows=list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"),newline="")))
    if len(rows)!=18109 or len(set(x["문서 ID"] for x in rows))!=18109:
        raise ValueError("ORIGINAL_18109_CORPUS_IDS_CHANGED")
    for no,r in enumerate(rows,1):
        r["번호"]=no
    return run_one(rows,Path(o.out))


if __name__=="__main__":
    raise SystemExit(main())
