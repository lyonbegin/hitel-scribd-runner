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
import time
import urllib.error
from pathlib import Path

from hitel_public_named_rooms_corpus import (
    call, output_file, read_completed_result, save, title_prompt, validated_rows)
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
            raise RuntimeError("POST_DELIVERY_UNCERTAIN_LOOKUP_404_REFUSE_DUPLICATE_SEND")
        # This atomic write happens BEFORE any request can reach the API.
        state["submit_attempted"]=True
        save(statefile,state)
        code,job=call(API+"/chat",{"request_id":request_id,
                                 "room_name":state["room_name"],"text":text})
        if code!=202 or job.get("accepted") is not True:
            raise ValueError("HTTP_CHAT_NOT_ACCEPTED")
        print("PUBLIC_HTTP_CHAT_ACCEPTED_ONCE",job.get("job_id"),flush=True)
    if (job.get("request_id")!=request_id or
        (job.get("room_name") is not None and
         job.get("room_name")!=state["room_name"]) or
        not str(job.get("job_id","")).startswith("job_") or
        not str(job.get("room_id","")).startswith("room_")):
        raise ValueError("HTTP_ACCEPTED_JOB_IDENTITY_MISMATCH")
    # GET /requests returns no room name. Match the job's persisted room name
    # on GET /jobs before accepting an existing request for a future poll.
    if previous is not None:
        status_code,status=call(API+"/jobs/"+job["job_id"])
        if (status_code!=200 or status.get("room_name")!=state["room_name"]
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
            or state.get("room_name")!=room_name):
            raise ValueError("HTTP_CHECKPOINT_SCOPE_CHANGED")
    else:
        state={"key":key,"digest":digest,"source_ids":ids,
               "request_id":request_id,"room_name":room_name,
               "status":"prepared","submit_attempted":False}
        save(statefile,state)
    statefile,state=recovery_after_verified_worker_disconnect(
        out,key,digest,ids,statefile,state,request_id,room_name)
    state=ensure_one_http_job(statefile,state,question)
    answer,remote=await_http_reply(statefile,state)
    parsed=validated_rows(answer,batch)
    dest=out/"completed"/(key+".json")
    if dest.exists():
        raise ValueError("REFUSE_OVERWRITE_VERIFIED_RESULTS")
    save(dest,{"rows":parsed,"job_id":state["job_id"],"room_id":state["room_id"],
               "request_id":request_id,"transport":"HITEL_PUBLIC_HTTP_PROVEN_E2E",
               "verified_reply_sha256":remote["result_sha256"]})
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
