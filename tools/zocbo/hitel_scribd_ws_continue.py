#!/usr/bin/env python3
"""Continue 18,109 Scribd title judgments using proc uref main tools/hitel_chat.py.

Preserve all 340 historically verified source IDs. Do NOT count skipped rows or
retry ambiguous deliveries. Every send is bound to a durable WebSocket client
state; any unresolved delivery is resumed, never resent.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,os,subprocess,sys
from pathlib import Path
from urllib.request import urlopen
from hitel_public_named_rooms_corpus import title_prompt,validated_rows,output_file,save

ROOM="HITEL-SCRIBD-18109-RECOVERY-WS-20261120"
RECOVERY_ROOM=ROOM+"-R301-20261121"
SOURCE_SHA="c9ac45f833dd30a002cffac64cb3ced763ed4eb18b0e121c4ab00b935a9b82e3"
REQUIRED_INITIAL=340

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


def manually_retry_one_confirmed_stalled_job(out,key,statefile,room_state):
    """One user-authorized retry. Archive original uncertainty; never mark it completed.

    This is deliberately limited to one exact prior job ID supplied by the
    workflow, not a general automatic retry of unverified deliveries.
    """
    allowed=os.environ.get("HITEL_EXPLICIT_RETRY_STALLED_JOB","").strip()
    if not allowed or room_state.get("job_id")!=allowed:
        return room_state
    if (room_state.get("status")!="unverified"
        or room_state.get("room_name")!=ROOM
        or not room_state.get("request_id")
        or not room_state.get("room_id")
        or not isinstance(room_state.get("seq"),int)):
        raise ValueError("EXPLICIT_STALLED_RETRY_CHECKPOINT_INVALID")
    url=("https://hitel-integration-api-production.up.railway.app"
         "/integrations/v1/public/jobs/"+allowed)
    with urlopen(url,timeout=15) as response:
        remote=json.load(response)
    for field in ("job_id","request_id","room_id"):
        if remote.get(field)!=room_state.get(field):
            raise ValueError("EXPLICIT_STALLED_RETRY_REMOTE_SCOPE_MISMATCH_"+field)
    if (remote.get("status")!="stalled"
        or remote.get("error_code")!="WORKER_CONNECTION_LOST"
        or remote.get("result_ready") is not False
        or remote.get("assistant_reply_observed") is True
        or remote.get("chatgpt_send_confirmed") is True):
        raise ValueError("EXPLICIT_STALLED_RETRY_NOT_CONFIRMED_SAFE")
    audit=out/"ws"/"stalled_history"/(key+"-"+allowed+".json")
    prior={"batch_key":key,
           "original_state":room_state,
           "read_only_remote_snapshot":remote,
           "operator_authorization":"manual_resume_after_api_fix_20261121",
           "delivery_uncertainty":"ChatGPT send was not confirmed; duplicate possible",
           "old_request_replayed":False,
           "original_counted_verified":False}
    if audit.exists():
        existing=json.loads(audit.read_text(encoding="utf-8"))
        if existing.get("original_state")!=room_state:
            raise ValueError("EXPLICIT_STALLED_RETRY_AUDIT_CONFLICT")
    else:
        save(audit,prior)
    # Terminal work may still reserve its old room. Open a new public room
    # rather than ever attempting another chat.send against the stalled room.
    clean={"room_name":RECOVERY_ROOM,"seq":0}
    save(statefile,clean)
    print("MANUAL_RETRY_TERMINAL_STALLED_NEW_ROOM",key,
          "PRIOR_JOB",allowed,
          "UNCERTAIN_PRIOR_DELIVERY_PRESERVED",flush=True)
    return clean


def rotate_rejected_conflict_to_new_room(out,key,statefile,room_state):
    """Repair the failed same-room recovery attempt without retrying its send.

    The API explicitly rejected that send with ROOM_OR_REQUEST_CONFLICT.
    Require the archived terminal-stalled original job before changing rooms.
    """
    allowed=os.environ.get("HITEL_EXPLICIT_RETRY_STALLED_JOB","").strip()
    if not allowed or room_state.get("status")!="rejected":
        return room_state
    if room_state.get("error_code")!="ROOM_OR_REQUEST_CONFLICT":
        return room_state
    if (room_state.get("room_name")!=ROOM
        or not room_state.get("room_id")
        or not room_state.get("request_id")
        or not isinstance(room_state.get("seq"),int)):
        raise ValueError("REJECTED_ROOM_ROTATION_CHECKPOINT_INVALID")
    audit=out/"ws"/"stalled_history"/(key+"-"+allowed+".json")
    if not audit.exists():
        raise ValueError("REJECTED_ROOM_ROTATION_ORIGINAL_AUDIT_MISSING")
    prior=json.loads(audit.read_text(encoding="utf-8"))
    if (prior.get("original_state",{}).get("job_id")!=allowed
        or prior.get("original_state",{}).get("room_id")!=room_state["room_id"]
        or prior.get("original_counted_verified") is not False):
        raise ValueError("REJECTED_ROOM_ROTATION_AUDIT_SCOPE_MISMATCH")
    rejected_audit=out/"ws"/"rejected_history"/(key+"-"+room_state["request_id"]+".json")
    if rejected_audit.exists():
        saved=json.loads(rejected_audit.read_text(encoding="utf-8"))
        if saved.get("rejected_state")!=room_state:
            raise ValueError("REJECTED_ROOM_ROTATION_AUDIT_CONFLICT")
    else:
        save(rejected_audit,{"batch_key":key,"rejected_state":room_state,
                             "prior_stalled_job":allowed,
                             "rejection_confirmed":True,
                             "counted_verified":False})
    clean={"room_name":RECOVERY_ROOM,"seq":0}
    save(statefile,clean)
    print("ROTATE_CONFIRMED_CONFLICT_TO_NEW_ROOM",key,
          "PRIOR_STALLED_JOB",allowed,
          "REJECTED_ATTEMPT_ARCHIVED",flush=True)
    return clean

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
    active=wsdir/"active_batch.json"
    statefile=wsdir/"scribd_room.json"
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
                     "transport":"HITEL_PUBLIC_PERSISTENT_WEBSOCKET","room_name":ROOM})
    room_state=json.loads(statefile.read_text(encoding="utf-8")) if statefile.exists() else {}
    if room_state.get("room_name") not in (None,ROOM,RECOVERY_ROOM):
        raise ValueError("SAVED_WS_ROOM_NAME_CHANGED")
    room_state=manually_retry_one_confirmed_stalled_job(out,key,statefile,room_state)
    room_state=rotate_rejected_conflict_to_new_room(out,key,statefile,room_state)
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
            command += ["--room",room_state.get("room_name",ROOM),"--text",prompt]
            print("NEW_SINGLE_WS_REQUEST",key,"SOURCE_IDS",len(batch),flush=True)
        try:
            run=subprocess.run(command,text=True,capture_output=True,timeout=600,check=False)
        except subprocess.TimeoutExpired:
            print("WS_PENDING_TIMEOUT_NOT_REPOSTED",key,flush=True)
            return 2
        if run.returncode:
            # No batch advances after any uncertain transport or JSON error.
            # The documented client emits only safe transport diagnostics to stderr.
            # Do not print its stdout: it may contain a full AI reply.
            print("WS_CLIENT_FAILED_CHECK_SAVED_STATE",key,"returncode",run.returncode,
                  "stderr_tail",run.stderr[-1200:],flush=True)
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
