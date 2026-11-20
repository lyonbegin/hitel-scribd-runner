#!/usr/bin/env python3
"""Classify the original 18,109 Scribd titles against the current HITEL API.

Use the checked-out proc ureflow main tools/hitel_chat.py protocol:
room.open/bind, chat.send, job.accepted, job.progress, reply.chunk,
reply.done (SHA-256 verified), job.resume (read-only), reply.unverified.

Do not impose a classification timeout: the API owns terminal job status.
A verified batch is recorded only after reply.done and source ID validation.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,os,subprocess,sys
from pathlib import Path
from urllib.request import urlopen
from hitel_public_named_rooms_corpus import title_prompt,validated_rows,output_file,save

SOURCE_SHA="c9ac45f833dd30a002cffac64cb3ced763ed4eb18b0e121c4ab00b935a9b82e3"
REQUIRED_INITIAL=340
FRESH_ROOM_PREFIX="HITEL-SCRIBD-18109-CLEAN-20261121-"
PUBLIC_API="https://hitel-integration-api-production.up.railway.app/integrations/v1/public"

# A single operator-authorized recovery of the interrupted 1001-1020 window.
# The previous remote job is stalled, but ChatGPT delivery is not proven absent.
# Preserve its audit without classifying it completed or hiding duplicate risk.
FAILED_KEY="01001-01020"
FAILED_JOB="job_5f672c582a9d4610be76fb281580dc92"
FAILED_ERROR="WEB2API_ADAPTER_HTTP_500_UPSTREAM_RATE_LIMITED"
FAILED_ROOM=FRESH_ROOM_PREFIX+FAILED_KEY
RECOVERY_ROOM="HITEL-SCRIBD-18109-EXPLICIT-RESTART-20261121-"+FAILED_KEY
CAPACITY_JOB="job_3e186fbd148c44c7b13bb9e6f88d3550"
CAPACITY_ROOM="HITEL-SCRIBD-18109-POST-CAPACITY-FIX-20261121-"+FAILED_KEY
CAPACITY_ERROR="ROOM_TAB_CAPACITY_EXCEEDED"

def fresh_room_name(key):
    """Route the one authorized capacity repair to its new public room."""
    return CAPACITY_ROOM if key==FAILED_KEY else FRESH_ROOM_PREFIX+key

def archive_confirmed_capacity_failure(out,key,digest,expected_ids,state,active):
    """Capacity rejection occurred before a ChatGPT send. Verify remote first.

    Unlike the original HTTP 500, a room-slot capacity rejection can be
    classified by the server as failed. We still audit the exact job and
    refuse to mark any of its source IDs as completed.
    """
    ws=out/"ws"
    old_audit=ws/"restart_audit"/(key+"-"+FAILED_JOB+".json")
    audit=ws/"restart_audit"/(key+"-"+CAPACITY_JOB+".json")
    if not old_audit.exists():
        raise ValueError("ORIGINAL_STALLED_AUDIT_MISSING")
    if not active.exists():
        raise ValueError("CAPACITY_FAILURE_ACTIVE_MARKER_MISSING")
    target=json.loads(active.read_text(encoding="utf-8"))
    if (target.get("key")!=key or target.get("prompt_sha256")!=digest
        or target.get("source_ids")!=expected_ids
        or state.get("room_name")!=RECOVERY_ROOM
        or state.get("job_id")!=CAPACITY_JOB
        or state.get("status")!="unverified"
        or state.get("error_code")!="web2api_failed"
        or state.get("text_sha256")!=digest):
        raise ValueError("CAPACITY_FAILURE_CHECKPOINT_MISMATCH")
    with urlopen(PUBLIC_API+"/jobs/"+CAPACITY_JOB,timeout=15) as response:
        remote=json.load(response)
    if any(remote.get(k)!=state.get(k) for k in ("job_id","request_id","room_id")):
        raise ValueError("CAPACITY_FAILURE_REMOTE_SCOPE_MISMATCH")
    if (remote.get("status")!="failed"
        or remote.get("stage")!="web2api_failed"
        or remote.get("error")!=CAPACITY_ERROR
        or remote.get("result_ready") is not False
        or remote.get("assistant_reply_observed") is True
        or remote.get("chatgpt_send_confirmed") is True):
        raise ValueError("CAPACITY_FAILURE_NOT_CONFIRMED_SAFE")
    record={"key":key,"prompt_sha256":digest,"source_ids":expected_ids,
            "old_active":target,"old_client_state":state,
            "old_remote_snapshot":{k:remote.get(k) for k in
                ("job_id","request_id","room_id","status","stage","error",
                 "error_code","result_ready","assistant_reply_observed",
                 "chatgpt_send_confirmed")},
            "authorized_explicit_restart":True,"capacity_rejected_before_send":True,
            "counted_as_completed":False}
    if audit.exists():
        if json.loads(audit.read_text(encoding="utf-8"))!=record:
            raise ValueError("CAPACITY_RESTART_AUDIT_CONFLICT")
    else:
        save(audit,record)
    (ws/(key+".json")).unlink()
    active.unlink()
    print("CAPACITY_FAILED_WINDOW_AUDITED_NEW_ROOM",key,
          "OLD_JOB",CAPACITY_JOB,"VERIFIED_RESULTS_PRESERVED",flush=True)


def archive_failed_window_before_restart(out,key,digest,expected_ids):
    """One authorized new send after confirming exact old job is stalled.

    A 500 upstream response means delivery is *uncertain*, not absent.
    Audit the original job and retain all verified rows. Never automatically
    retry another uncertain job or a currently active/answered job.
    """
    if os.environ.get("HITEL_EXPLICIT_RESTART_FAILED_KEY","").strip()!=FAILED_KEY:
        return
    if key!=FAILED_KEY:
        return
    ws=out/"ws"
    statefile=ws/(key+".json")
    active=ws/"active_batch.json"
    if not statefile.exists():
        # Already restarted or checkpoint was externally tampered with:
        # do not silently invent a request to cover missing evidence.
        if (ws/"restart_audit"/(key+"-"+FAILED_JOB+".json")).exists():
            return
        raise ValueError("ORIGINAL_FAILED_JOB_STATE_MISSING_REFUSE_RESTART")
    state=json.loads(statefile.read_text(encoding="utf-8"))
    audit=ws/"restart_audit"/(key+"-"+FAILED_JOB+".json")
    if state.get("room_name")==CAPACITY_ROOM:
        if not audit.exists() or not (ws/"restart_audit"/(key+"-"+CAPACITY_JOB+".json")).exists():
            raise ValueError("POST_CAPACITY_STATE_WITHOUT_BOTH_AUDITS")
        return
    if state.get("room_name")==RECOVERY_ROOM:
        archive_confirmed_capacity_failure(out,key,digest,expected_ids,state,active)
        return
    if not active.exists():
        raise ValueError("FAILED_ACTIVE_BATCH_CHECKPOINT_MISSING")
    target=json.loads(active.read_text(encoding="utf-8"))
    if (target.get("key")!=key or target.get("prompt_sha256")!=digest
        or target.get("source_ids")!=expected_ids
        or state.get("room_name")!=FAILED_ROOM
        or state.get("job_id")!=FAILED_JOB
        or state.get("status")!="unverified"
        or state.get("error_code")!=FAILED_ERROR
        or state.get("text_sha256")!=digest):
        raise ValueError("FAILED_WINDOW_CHECKPOINT_MISMATCH_REFUSE_RESTART")
    with urlopen(PUBLIC_API+"/jobs/"+FAILED_JOB,timeout=15) as response:
        remote=json.load(response)
    if any(remote.get(k)!=state.get(k) for k in
           ("job_id","request_id","room_id")):
        raise ValueError("FAILED_WINDOW_REMOTE_SCOPE_MISMATCH")
    if (remote.get("status")!="stalled"
        or remote.get("error_code")!=FAILED_ERROR
        or remote.get("result_ready") is not False
        or remote.get("assistant_reply_observed") is True
        or remote.get("chatgpt_send_confirmed") is True):
        raise ValueError("FAILED_WINDOW_NOT_STALLED_OR_MAY_HAVE_REPLY")
    record={"key":key,"prompt_sha256":digest,"source_ids":expected_ids,
            "old_active":target,"old_client_state":state,
            "old_remote_snapshot":{k:remote.get(k) for k in
                ("job_id","request_id","room_id","status","stage","error_code",
                 "result_ready","assistant_reply_observed","chatgpt_send_confirmed")},
            "authorized_explicit_restart":True,
            "old_result_verified":False,
            "possible_previous_delivery":True,
            "original_job_replayed":False}
    if audit.exists():
        if json.loads(audit.read_text(encoding="utf-8"))!=record:
            raise ValueError("RESTART_AUDIT_CONFLICT_REFUSE_OVERWRITE")
    else:
        save(audit,record)
    # Save first; then clear only the old *active* pointer, not completed rows.
    statefile.unlink()
    active.unlink()
    print("EXPLICIT_STALLED_WINDOW_ARCHIVED_NEW_ROOM",key,
          "OLD_JOB",FAILED_JOB,"POSSIBLE_OLD_DELIVERY_AUDITED",flush=True)

def check_worker_ready():
    """Read the live API's own worker availability before making a new send."""
    with urlopen(PUBLIC_API+"/status",timeout=12) as response:
        status=json.load(response)
    fields=("worker_connected","worker_heartbeat_recent",
            "worker_bootstrap_ready","worker_available_for_new_job",
            "worker_busy","worker_active_jobs_count","worker_capacity")
    snapshot={k:status.get(k) for k in fields}
    print("LIVE_WORKER_PREFLIGHT",json.dumps(snapshot,ensure_ascii=False),flush=True)
    if status.get("worker_available_for_new_job") is not True:
        raise RuntimeError("API_WORKER_UNAVAILABLE_NO_QUESTION_SENT")


def report_failed_api_job(statefile):
    """Read remote status for diagnosis; never mutate or recreate the request."""
    if not statefile.exists():
        print("CLIENT_STATE_NOT_SAVED",flush=True)
        return
    state=json.loads(statefile.read_text(encoding="utf-8"))
    print("CLIENT_EXIT_STATE",json.dumps({k:state.get(k) for k in
          ("room_name","status","job_id","error_code")},ensure_ascii=False),
          flush=True)
    job_id=state.get("job_id")
    if not job_id:
        return
    try:
        with urlopen(PUBLIC_API+"/jobs/"+job_id,timeout=12) as response:
            remote=json.load(response)
        if any(remote.get(k)!=state.get(k) for k in
               ("job_id","room_id","request_id")):
            raise ValueError("API_JOB_SCOPE_MISMATCH")
        print("API_JOB_TERMINAL_SNAPSHOT",json.dumps(
            {k:remote.get(k) for k in
             ("job_id","status","stage","error_code","result_ready",
              "chatgpt_send_confirmed","assistant_reply_observed")},
            ensure_ascii=False),flush=True)
    except Exception as exc:
        print("API_JOB_SNAPSHOT_UNAVAILABLE",type(exc).__name__,
              str(exc)[:250],flush=True)


def load_verified(rows,out):
    verified={}
    for f in sorted((out/"completed").glob("*.json")):
        d=json.loads(f.read_text(encoding="utf-8"))
        for a in d["rows"]:
            n=int(a["no"])
            if n in verified or not 1<=n<=len(rows):
                raise ValueError("VERIFIED_ROW_DUPLICATE_OR_OUT_OF_RANGE")
            if str(rows[n-1]["문서 ID"])!=str(a["id"]):
                raise ValueError("VERIFIED_ROW_SOURCE_ID_CHANGED")
            verified[n]=a
    if len(verified)<REQUIRED_INITIAL:
        raise ValueError("INITIAL_340_VERIFIED_ROWS_MISSING")
    # No gaps may be marked processed merely because an old job was skipped.
    if list((out/"skipped").glob("*.json")):
        raise ValueError("LEGACY_SKIPPED_MARKERS_NOT_CLEARED")
    return verified

def next_batch(rows,verified):
    first=next((i for i in range(1,len(rows)+1) if i not in verified),None)
    if first is None:return []
    result=[]
    for n in range(first,min(len(rows)+1,first+20)):
        if n in verified:break
        result.append(rows[n-1])
    return result


def run_one(rows,out,client):
    verified=load_verified(rows,out)
    batch=next_batch(rows,verified)
    if not batch:
        print("COMPLETE_VERIFIED_ALL",len(verified),flush=True)
        output_file(rows,out)
        return 0
    key=f'{batch[0]["번호"]:05d}-{batch[-1]["번호"]:05d}'
    expected_ids=[{"no":a["번호"],"id":str(a["문서 ID"])} for a in batch]
    prompt=title_prompt(batch)
    digest=hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    if len(prompt)>24000:raise ValueError("PROMPT_EXCEEDS_SAFE_LENGTH")
    wsdir=out/"ws";wsdir.mkdir(parents=True,exist_ok=True)
    archive_failed_window_before_restart(out,key,digest,expected_ids)
    active=wsdir/"active_batch.json"
    statefile=wsdir/(key+".json")
    chosen_room=fresh_room_name(key)
    if active.exists():
        saved=json.loads(active.read_text(encoding="utf-8"))
        if saved.get("key")!=key or saved.get("prompt_sha256")!=digest or saved.get("source_ids")!=expected_ids:
            raise ValueError("PENDING_WS_BATCH_SCOPE_MISMATCH")
    else:
        if statefile.exists():
            old=json.loads(statefile.read_text(encoding="utf-8"))
            if old.get("status") in ("sending","running","unverified"):
                raise ValueError("PREVIOUS_PENDING_JOB_NOT_RESOLVED")
        save(active,{"key":key,"source_ids":expected_ids,"prompt_sha256":digest,
                     "transport":"HITEL_PUBLIC_PERSISTENT_WEBSOCKET","room_name":chosen_room})
    room_state=json.loads(statefile.read_text(encoding="utf-8")) if statefile.exists() else {}
    if room_state.get("room_name") not in (None,chosen_room):
        raise ValueError("SAVED_WS_ROOM_NAME_CHANGED")
    if room_state.get("status")=="completed" and active.exists() and room_state.get("text_sha256")==digest:
        # A previous job returned successfully but the GitHub runner exited
        # before the completed row JSON could be written.
        answer=room_state.get("answer")
        print("RECOVERING_VERIFIED_WS_REPLY_WITHOUT_NEW_SEND",key,flush=True)
    else:
        pending=room_state.get("status") in ("sending","running","unverified")
        if pending and room_state.get("text_sha256")!=digest:
            raise ValueError("PENDING_WS_PROMPT_CHANGED")
        if room_state.get("status") in ("rejected",) and active.exists():
            raise ValueError("PREVIOUS_WS_SEND_REJECTED_CHECK_BEFORE_RETRY")
        command=[sys.executable,str(client),"--state",str(statefile)]
        if pending:
            command.append("--resume")
            print("RESUME_ORIGINAL_WS_REQUEST_NO_RESEND",key,flush=True)
        else:
            check_worker_ready()
            command += ["--room",chosen_room,"--text",prompt]
            print("NEW_SINGLE_WS_REQUEST",key,"SOURCE_IDS",len(batch),
                  "ROOM",chosen_room,flush=True)
        # The documented client waits for API reply.done or reply.unverified.
        # There is NO locally imposed wait duration. Client stderr streams
        # job.progress live to Actions; stdout may contain private AI text.
        run=subprocess.run(command,stdout=subprocess.DEVNULL,check=False)
        if run.returncode:
            print("API_CLIENT_EXIT_WITHOUT_VERIFIED_REPLY",key,
                  "returncode",run.returncode,flush=True)
            report_failed_api_job(statefile)
            return 2
        room_state=json.loads(statefile.read_text(encoding="utf-8"))
        answer=room_state.get("answer")
    if room_state.get("status")!="completed" or not isinstance(answer,str):
        raise ValueError("WS_REPLY_NOT_COMPLETED")
    if hashlib.sha256(answer.encode("utf-8")).hexdigest()!=room_state.get("sha256"):
        raise ValueError("WS_REPLY_SHA256_MISMATCH")
    parsed=validated_rows(answer,batch)
    dest=out/"completed"/(key+".json")
    if dest.exists():raise ValueError("REFUSE_OVERWRITE_VERIFIED_ROWS")
    save(dest,{"rows":parsed,"job_id":room_state.get("job_id"),
               "room_id":room_state.get("room_id"),
               "transport":"HITEL_PUBLIC_PERSISTENT_WEBSOCKET",
               "verified_reply_sha256":room_state.get("sha256")})
    # Atomic completed checkpoint is created before removing active marker.
    active.unlink()
    summary=output_file(rows,out)
    if summary["verified_ai_completed"]!=len(verified)+len(parsed):
        raise ValueError("VERIFIED_TOTAL_MISMATCH")
    print("WS_VERIFIED_BATCH",key,"NEW",len(parsed),
          "TOTAL_VERIFIED",summary["verified_ai_completed"],
          "REMAINING",len(rows)-summary["verified_ai_completed"],flush=True)
    return 0

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--client",required=True)
    o=p.parse_args()
    client=Path(o.client)
    if not client.is_file():raise ValueError("DOCUMENTED_HITEL_CLIENT_MISSING")
    with open(o.input,encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    if len(rows)!=18109 or len(set(r["문서 ID"] for r in rows))!=18109:
        raise ValueError("ORIGINAL_CORPUS_18109_IDENTITY_FAILED")
    digest=hashlib.sha256(Path(o.input).read_bytes()).hexdigest()
    if digest!=SOURCE_SHA:raise ValueError("ORIGINAL_CORPUS_SHA256_MISMATCH")
    for i,r in enumerate(rows,1):r["번호"]=i
    return run_one(rows,Path(o.out),client)

if __name__=="__main__":raise SystemExit(main())
