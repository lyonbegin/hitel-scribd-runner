#!/usr/bin/env python3
"""Regression: named room reuse, second turn memory, and switching back to a prior room."""
import json
import os
from pathlib import Path
import time
import urllib.request
import urllib.error
import uuid

BASE="https://hitel-integration-api-production.up.railway.app"
HTTP=urllib.request.build_opener(urllib.request.ProxyHandler({}))
OUT=Path("hitel-named-rooms-e2e.json")
EVENTS=[]
def request(path,payload=None):
    data=json.dumps(payload,ensure_ascii=False).encode() if payload is not None else None
    req=urllib.request.Request(BASE+path,data=data,
        method="POST" if data is not None else "GET",
        headers={"Content-Type":"application/json","Accept":"application/json"})
    try:
        with HTTP.open(req,timeout=45) as r:
            return r.status,json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail=exc.read().decode("utf-8","replace")[:800]
        record("http_error",{"path":path,"status":exc.code,"detail":detail})
        raise RuntimeError("HITEL_HTTP_"+str(exc.code)+": "+detail) from None
def record(event,info):
    EVENTS.append({"event":event,**info})
    OUT.write_text(json.dumps(EVENTS,ensure_ascii=False,indent=2),encoding="utf-8")
    print("TEST_EVENT",event, json.dumps(info,ensure_ascii=False)[:1000],flush=True)
def open_room(name):
    code,r=request("/integrations/v1/public/rooms",{"name":name})
    assert code in (200,201),(code,r)
    rid=r.get("room_id")
    assert isinstance(rid,str) and rid.startswith("room_"),r
    record("room_opened",{"name":name,"room_id":rid,"code":code,"conversation_linked":r.get("conversation_linked")})
    return rid
def ask(room_id,name,text,limit_seconds=480):
    request_id="hitel-named-e2e-"+uuid.uuid4().hex
    code,v=request("/integrations/v1/public/chat",{"room_id":room_id,"text":text,"request_id":request_id})
    assert code==202,(code,v)
    assert v.get("room_id")==room_id,("accepted wrong room",v)
    jid=v["job_id"]
    record("chat_accepted",{"room":name,"room_id":room_id,"job_id":jid})
    deadline=time.monotonic()+limit_seconds
    while time.monotonic()<deadline:
        _,state=request("/integrations/v1/public/jobs/"+jid)
        assert state.get("room_id")==room_id,("job wrong room",state)
        if state.get("status")=="completed":
            answer=state.get("result_text")
            assert isinstance(answer,str) and answer.strip(),"No verified AI answer"
            record("chat_completed",{"room":name,"room_id":room_id,"job_id":jid,"result_text":answer[:600]})
            return answer
        if state.get("status")=="failed":
            record("chat_failed",{"room":name,"room_id":room_id,"job_id":jid,"error":state.get("error")})
            raise AssertionError("HITEL ChatGPT job failed: "+str(state.get("error")))
        time.sleep(5)
    raise TimeoutError("No completed response in same room for "+jid)
def main():
    stamp="hitel-scribd-18109-named-room-e2e-"+os.environ.get("GITHUB_RUN_ID","local")+"-"+os.environ.get("GITHUB_RUN_ATTEMPT","1")
    a_name=stamp+"-mathematics"
    b_name=stamp+"-english"
    _,status=request("/integrations/v1/public/status")
    assert status.get("same_room_name_reuses_conversation") is True,status
    a=open_room(a_name)
    b=open_room(b_name)
    assert a!=b,"Different named rooms share the same room_id"
    a2=open_room(a_name)
    assert a2==a,"Same named room unexpectedly created another room"
    # A turn establishes a memory token in a real ChatGPT conversation.
    first=ask(a,a_name,"이 방의 대화 연속성 시험입니다. 기억할 코드는 HITELROOM731 입니다. 정확히 '저장: HITELROOM731'만 답변하십시오.")
    assert "HITELROOM731" in first,"First reply did not acknowledge token"
    # B is an entirely separate named room and must not reuse A's room id.
    second=ask(b,b_name,"영어 교재 분류 시험입니다. 'English workbook grade 7'의 학교급이 무엇인지 한국어 한 문장으로 설명해 주십시오.")
    assert second.strip(),"Room B reply missing"
    # Return to A. This must use A's previous ChatGPT conversation, not a new one.
    third=ask(a,a_name,"이전에 같은 대화방에서 기억해 달라고 한 코드가 무엇인지 코드만 답변하십시오. 현재 질문에는 코드 자체가 쓰여 있지 않습니다.")
    assert "HITELROOM731" in third,"Conversation was not preserved after switching rooms"
    _,rooms=request("/integrations/v1/public/rooms")
    entries=rooms.get("rooms",[])
    ids={r.get("room_id") for r in entries}
    assert a in ids and b in ids,"Created rooms missing from listing"
    record("verified",{"pass":True,"room_a":a,"room_b":b,"turns":3})
if __name__=="__main__":
    try:main()
    except Exception as ex:
        record("error",{"type":type(ex).__name__,"message":str(ex)})
        raise
