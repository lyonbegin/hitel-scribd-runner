"""Durable, task-isolated Scribd result recovery (no inferred source IDs).
The approved signed transport owns delivery reconciliation. This layer only
reclassifies after a terminal, hash-verified reply fails content validation.
"""
from __future__ import annotations
import hashlib
import json
import time
import unicodedata
import urllib.error
from pathlib import Path
from hitel_public_named_rooms_corpus import title_prompt, save, validated_rows

FIELDS=("school","grade","semester","subject","edition","download","reason")
SCHEMA="scribd-keyed-v1"
MAX_SINGLE_ATTEMPTS=3

class InvalidReply(ValueError):
    pass

def digest(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def batch_key(batch):
    return f'{batch[0]["번호"]:05d}-{batch[-1]["번호"]:05d}'

def identity(batch):
    return [{"no":int(r["번호"]),"id":str(r["문서 ID"])} for r in batch]

def keyed_inputs(batch):
    return [{"key":f"A{i:02d}","title":unicodedata.normalize("NFC",r["원문 제목"])}
            for i,r in enumerate(batch,1)]

def keyed_prompt(batch):
    # Reuse the existing education rules verbatim; only replace the
    # model-facing identity format. Long Scribd IDs never enter this prompt.
    rules=title_prompt(batch).split("\n",1)[0]
    rules=rules.replace("no(정수),id(원본 문서ID),","key(짧은 식별키),title(입력 제목 그대로),")
    rules=rules.replace("no와 id는 바꾸지 말고","key와 title은 바꾸지 말고")
    if "no(정수)" in rules or "id(원본 문서ID)" in rules:
        raise RuntimeError("KEYED_PROMPT_FORMAT_CHANGED")
    return (rules+"\n반드시 각 key와 원본 title을 한 글자도 바꾸지 말고 반환하십시오. "
            "입력 순서를 지키고, 서로 다른 제목의 분류를 섞지 마십시오. "
            "JSON 객체 하나만 출력하십시오. schema는 "+SCHEMA+"이며 rows 배열을 포함하십시오.\n"
            +json.dumps({"schema":SCHEMA,"items":keyed_inputs(batch)},ensure_ascii=False,separators=(",",":")))

def validate_keyed(answer,batch):
    s=answer.strip()
    if s.startswith(chr(96)*3):
        if not s.endswith(chr(96)*3):
            raise InvalidReply("INCOMPLETE_FENCE")
        s=s.split("\n",1)[-1].rsplit(chr(96)*3,1)[0].strip()
    try:
        obj=json.loads(s)
        if not isinstance(obj,dict) or ("schema" in obj and obj["schema"]!=SCHEMA):
            raise InvalidReply("WRONG_SCHEMA")
        got=obj.get("rows")
        expected=keyed_inputs(batch)
        if not isinstance(got,list) or len(got)!=len(expected):
            raise InvalidReply("WRONG_ROW_COUNT")
        normalized=[]
        for actual,entry,src in zip(got,expected,batch):
            if (not isinstance(actual,dict) or actual.get("key")!=entry["key"]
                or not isinstance(actual.get("title"),str)
                or unicodedata.normalize("NFC",actual["title"])!=entry["title"]):
                raise InvalidReply("KEY_OR_TITLE_MISMATCH")
            if any(not isinstance(actual.get(k),str) or not actual[k].strip() for k in FIELDS):
                raise InvalidReply("MISSING_CATEGORY")
            if (actual["school"] not in ("초등","중등","고등","대상외","판정보류")
                or actual["edition"] not in ("2022확인","2015전용","판본검토","해당없음")
                or actual["download"] not in ("대상","제외","판본검토")):
                raise InvalidReply("CATEGORY_ENUM_INVALID")
            # Copy source identity solely from the verified corpus, not the AI.
            normalized.append({"no":int(src["번호"]),"id":str(src["문서 ID"]),
                              **{k:actual[k] for k in FIELDS}})
        # Reuse domain checks; exact source identities make repair impossible.
        audit=[]
        checked=validated_rows(json.dumps({"rows":normalized},ensure_ascii=False),batch,audit)
        if audit:
            raise InvalidReply("UNEXPECTED_ID_REPAIR")
        if "schema" not in obj:
            print("SUPERVISOR_SCHEMA_ABSENT_EXACT_ROWS_VALIDATED",flush=True)
        return checked
    except InvalidReply:
        raise
    except (ValueError,TypeError,KeyError,AttributeError) as exc:
        raise InvalidReply(str(exc)[:240]) from exc

def strict_legacy(answer,batch):
    audit=[]
    try:
        parsed=validated_rows(answer,batch,audit)
        if audit:
            raise InvalidReply("LEGACY_ID_REPAIR_REFUSED_RECLASSIFY")
        if any(any(not isinstance(row.get(k),str) or not row[k].strip() for k in FIELDS)
               for row in parsed):
            raise InvalidReply("MISSING_CATEGORY")
        return parsed
    except InvalidReply:
        raise
    except (ValueError,TypeError,KeyError,AttributeError) as exc:
        raise InvalidReply(str(exc)[:240]) from exc

def safe_read(fn, sleep=time.sleep, tries=6):
    """Retry read-only operations only. Honor HTTP Retry-After when supplied."""
    for i in range(tries):
        try:
            return fn()
        except urllib.error.HTTPError as exc:
            if exc.code not in (408,429,500,502,503,504) or i+1==tries:
                raise
            retry_after=(exc.headers or {}).get("Retry-After","")
            wait=min(120,5*2**i)
            if str(retry_after).isdigit():
                wait=max(wait,int(retry_after))
            print("SUPERVISOR_READ_BACKOFF_HTTP",exc.code,wait,flush=True)
        except (urllib.error.URLError,TimeoutError,ConnectionError) as exc:
            if i+1==tries:
                raise
            wait=min(120,5*2**i)
            print("SUPERVISOR_READ_BACKOFF_NETWORK",type(exc).__name__,wait,flush=True)
        sleep(wait)

def scope_record(root,batch,legacy_failure=None):
    p=root/"supervisor"/batch_key(batch)/"scope.json"
    expected={"schema":SCHEMA,"source_ids":identity(batch)}
    if p.exists():
        old=json.loads(p.read_text("utf-8"))
        if any(old.get(k)!=v for k,v in expected.items()):
            raise RuntimeError("SUPERVISOR_SCOPE_CHANGED")
        return old
    record={**expected,"legacy_failure":legacy_failure}
    save(p,record)
    return record

def evidence(state,remote,answer):
    sha=digest(answer)
    if (remote.get("status")!="completed" or remote.get("result_ready") is not True
        or remote.get("chatgpt_send_confirmed") is not True
        or remote.get("assistant_reply_observed") is not True
        or remote.get("result_sha256")!=sha
        or remote.get("job_id")!=state.get("job_id")
        or remote.get("room_id")!=state.get("room_id")
        or remote.get("request_id")!=state.get("active_request_id",state.get("request_id"))):
        raise RuntimeError("SUPERVISOR_TERMINAL_REPLY_EVIDENCE_MISSING")
    return {"job_id":state["job_id"],"room_id":state["room_id"],
            "request_id":remote["request_id"],"result_sha256":sha}

def validate_cached(record,batch):
    if record.get("source_ids")!=identity(batch):
        raise RuntimeError("SUPERVISOR_CACHED_SCOPE_MISMATCH")
    parsed=record.get("rows")
    if not isinstance(parsed,list) or [(int(x["no"]),str(x["id"])) for x in parsed]!=[
            (x["no"],x["id"]) for x in identity(batch)]:
        raise RuntimeError("SUPERVISOR_CACHED_IDENTITY_MISMATCH")
    audit=[]
    validated_rows(json.dumps({"rows":parsed},ensure_ascii=False),batch,audit)
    if audit or not record.get("evidence"):
        raise RuntimeError("SUPERVISOR_CACHED_EVIDENCE_MISSING")
    return parsed,record["evidence"]

def process_scope(root,parent,batch,ensure_job,await_reply,sleep=time.sleep):
    """20 -> 5 -> 1. Persist every accepted/rejected leaf before advancing.
    Never resubmit a running or delivery-unknown request. Any transport error
    leaves the exact same request checkpoint for reconciliation.
    """
    key=batch_key(batch)
    folder=root/"supervisor"/parent/key
    cache=folder/"verified.json"
    if cache.exists():
        return validate_cached(json.loads(cache.read_text("utf-8")),batch)
    n=len(batch)
    max_attempts=MAX_SINGLE_ATTEMPTS if n==1 else 2
    prompt=keyed_prompt(batch)
    d=digest(prompt)
    if len(prompt)>24000:
        if n==1:
            raise RuntimeError("SINGLE_TITLE_PROMPT_LIMIT")
        return split_scope(root,parent,batch,ensure_job,await_reply,sleep)
    ids=identity(batch)
    # A single-source content rejection must not create a permanent retry
    # ceiling. Existing rejected attempts are immutable, and a fresh round
    # may only follow hash-verified terminal replies. Multi-row scopes split.
    if n==1:
        while all((folder/f"rejected-{a}.json").is_file()
                  for a in range(1,max_attempts+1)):
            max_attempts+=1
    for attempt in range(1,max_attempts+1):
        file=folder/f"attempt-{attempt}.json"
        rejected=folder/f"rejected-{attempt}.json"
        req=f"scribd18109-sv1-{parent}-{key}-{d[:24]}-a{attempt}"
        room=f"HITEL-SCRIBD-SV1-{parent}-{key}-{d[:12]}-A{attempt}"
        fixed={"key":key,"digest":d,"source_ids":ids,"request_id":req,
               "room_name":room,"task_id":"scribd-18109"}
        if rejected.exists():
            r=json.loads(rejected.read_text("utf-8"))
            if r.get("scope")!=fixed or not r.get("evidence"):
                raise RuntimeError("SUPERVISOR_REJECTED_SCOPE_MISMATCH")
            # Revalidate the exact previously received raw reply under the
            # current schema parser; no new turn if only the envelope was absent.
            ev=r["evidence"]; raw=r.get("raw_reply")
            if (isinstance(raw,str) and digest(raw)==ev.get("result_sha256")
                and str(ev.get("job_id","")).startswith("job_")
                and str(ev.get("room_id","")).startswith("room_")
                and ev.get("request_id")==req):
                try:
                    parsed=validate_keyed(raw,batch)
                except InvalidReply:
                    pass
                else:
                    save(cache,{"source_ids":ids,"rows":parsed,"evidence":[ev]})
                    print("SUPERVISOR_REVALIDATED_TERMINAL_REPLY",key,n,flush=True)
                    return parsed,[ev]
            continue
        if file.exists():
            state=json.loads(file.read_text("utf-8"))
            if any(state.get(k)!=v for k,v in fixed.items()):
                raise RuntimeError("SUPERVISOR_ATTEMPT_SCOPE_CHANGED")
        else:
            state={**fixed,"status":"prepared","submit_attempted":False}
            save(file,state)
        print("SUPERVISOR_ATTEMPT",parent,key,attempt,flush=True)
        state=ensure_job(file,state,prompt)
        answer,remote=await_reply(file,state)
        ev=evidence(state,remote,answer)
        try:
            parsed=validate_keyed(answer,batch)
        except InvalidReply as exc:
            save(rejected,{"scope":fixed,"evidence":ev,"reason":str(exc)[:240],
                           "raw_reply":answer,"not_counted":True})
            print("SUPERVISOR_REJECTED_REPLY",key,attempt,str(exc)[:120],flush=True)
            if attempt<max_attempts:
                sleep(min(30,5*2**(attempt-1)))
            continue
        record={"source_ids":ids,"rows":parsed,"evidence":[ev]}
        save(cache,record)
        print("SUPERVISOR_VERIFIED_SCOPE",key,n,flush=True)
        return parsed,[ev]
    if n>1:
        return split_scope(root,parent,batch,ensure_job,await_reply,sleep)
    raise RuntimeError("SUPERVISOR_SINGLE_ROW_RETRY_LIMIT_"+key)

def split_scope(root,parent,batch,ensure_job,await_reply,sleep):
    step=5 if len(batch)>5 else 1
    rows=[]; proof=[]
    print("SUPERVISOR_SPLIT",batch_key(batch),"SIZE",step,flush=True)
    for i in range(0,len(batch),step):
        child,ev=process_scope(root,parent,batch[i:i+step],ensure_job,await_reply,sleep)
        rows.extend(child);proof.extend(ev)
    record={"source_ids":identity(batch),"rows":rows,"evidence":proof}
    parsed,ev=validate_cached(record,batch)
    save(root/"supervisor"/parent/batch_key(batch)/"verified.json",record)
    return parsed,ev

def run_supervised(root,batch,ensure_job,await_reply,legacy_failure=None,sleep=time.sleep):
    scope_record(root,batch,legacy_failure)
    return process_scope(root,batch_key(batch),batch,ensure_job,await_reply,sleep)
