"""Opt-in event notifications. No project-controlled URL or secret. Durable outbox."""
import datetime,hashlib,hmac,json,os,time,urllib.parse,urllib.request,urllib.error
EVENTS={"project.started","request.prepared","request.accepted","batch.verified","project.pending","project.paused","project.blocked","project.completed","heartbeat"}
DEFAULT=["project.started","batch.verified","project.pending","project.paused","project.blocked","project.completed","heartbeat"]
def config(p):
    c=p.get("notifications",{})
    if not isinstance(c,dict) or set(c)-{"channel","pr_number","heartbeat_seconds","events"}:raise ValueError("notification config")
    channel=c.get("channel","none")
    if channel not in ("none","github_pr","webhook"):raise ValueError("notification channel")
    pr=c.get("pr_number")
    if channel=="github_pr" and (type(pr) is not int or pr<=0):raise ValueError("notification PR number")
    sec=c.get("heartbeat_seconds",60)
    if type(sec) is not int or not 30<=sec<=3600:raise ValueError("notification heartbeat: 30-3600 seconds")
    events=c.get("events",DEFAULT)
    if not isinstance(events,list) or any(not isinstance(v,str) or v not in EVENTS for v in events):raise ValueError("notification events")
    return {"channel":channel,"pr_number":pr,"heartbeat_seconds":sec,"events":events}
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def append(p,s,kind,detail=None):
    c=config(p)
    seq=s.get("event_seq",0)+1
    s["event_seq"]=seq
    event={"schema":"hitel.progress.v1","event_id":hashlib.sha256((s["definition_sha"]+":"+str(seq)).encode()).hexdigest(),"sequence":seq,"event":kind,
           "occurred_at":stamp(),"project_id":p["project_id"],"provider":p["provider"],"status":s["status"],"total":s["total"],
           "verified_ai_completed":len(s["results"]) if p["provider"]=="hitel" else 0,"mock_completed":len(s["results"]) if p["provider"]=="mock" else 0,
           "no_progress":s.get("no_progress",0),"run_id":os.getenv("GITHUB_RUN_ID",""),"repository":os.getenv("GITHUB_REPOSITORY",""),
           "branch":os.getenv("GITHUB_REF_NAME","")}
    if detail:event["detail"]=detail
    if event["repository"] and event["run_id"]:event["run_url"]="https://github.com/"+event["repository"]+"/actions/runs/"+event["run_id"]
    channel=c["channel"] if kind in c["events"] else "none"
    s.setdefault("notification_events",[]).append({"payload":event,"channel":channel,"pr_number":c["pr_number"] if channel=="github_pr" else None,"delivery":"pending" if channel!="none" else "recorded"})
    # Full per-run artifact also contains this recent ledger. No input, output or token is included in notifications.
    s["notification_events"]=s["notification_events"][-500:]
    print("HITEL_EVENT",kind,p["project_id"],event["verified_ai_completed"],event["mock_completed"],event["total"],event["event_id"],flush=True)
def observe(p,s,force_heartbeat=False):
    prior=s.setdefault("notification_observed",{})
    now=int(time.time())
    status=s["status"]; count=len(s["results"])
    prepared=sum(1 for b in s["batches"].values() if b.get("attempted"))
    accepted=sum(1 for b in s["batches"].values() if b.get("job_id"))
    if not prior:append(p,s,"project.started")
    if prepared>prior.get("prepared",0):append(p,s,"request.prepared")
    if accepted>prior.get("accepted",0):append(p,s,"request.accepted")
    if count>prior.get("count",0):append(p,s,"batch.verified")
    if status!=prior.get("status") and status in ("pending","paused","blocked","complete"):
        append(p,s,"project.completed" if status=="complete" else "project."+status)
    if force_heartbeat and status not in ("complete","blocked","paused") and now-prior.get("heartbeat",now)>=config(p)["heartbeat_seconds"]:
        append(p,s,"heartbeat");prior["heartbeat"]=now
    prior.update(status=status,count=count,prepared=prepared,accepted=accepted)
    prior.setdefault("heartbeat",now)
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*a,**kw):return None
def post(url,body,headers):
    req=urllib.request.Request(url,data=body,method="POST",headers=headers)
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=12) as r:return r.status
def request_json(url,token):
    req=urllib.request.Request(url,headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json"})
    with urllib.request.urlopen(req,timeout=12) as r:return json.load(r)
def deliver(item):
    e=item["payload"]; body=json.dumps(e,ensure_ascii=False,separators=(",",":")).encode()
    if item["channel"]=="webhook":
        url=os.getenv("HITEL_EVENT_WEBHOOK_URL","");secret=os.getenv("HITEL_EVENT_WEBHOOK_SECRET","")
        u=urllib.parse.urlsplit(url)
        if u.scheme!="https" or not u.hostname or u.username or u.password or not secret:return "not_configured"
        signed=str(int(time.time()))
        sig=hmac.new(secret.encode(),signed.encode()+b"."+body,hashlib.sha256).hexdigest()
        code=post(url,body,{"Content-Type":"application/json","X-HITEL-Event-ID":e["event_id"],"X-HITEL-Timestamp":signed,"X-HITEL-Signature":"sha256="+sig})
    elif item["channel"]=="github_pr":
        pr=item["pr_number"];repo=os.getenv("GITHUB_REPOSITORY","");token=os.getenv("GH_TOKEN","")
        allowed=os.getenv("HITEL_NOTIFY_PR_ALLOWLIST","").split(",")
        if not token or str(pr) not in [v.strip() for v in allowed]:return "not_configured"
        base="https://api.github.com/repos/"+repo
        pull=request_json(base+"/pulls/"+str(pr),token)
        if pull.get("state")!="open":return "not_configured"
        text="HITEL progress event: "+e["event"]+"\n\n"+json.dumps(e,ensure_ascii=False,indent=2)
        code=post(base+"/issues/"+str(pr)+"/comments",json.dumps({"body":text}).encode(),{"Content-Type":"application/json","Authorization":"Bearer "+token,"Accept":"application/vnd.github+json"})
    else:return "recorded"
    return "accepted" if 200<=code<300 else "rejected"
def flush(s,persist):
    # Save attempt before I/O. Uncertain delivery is not blindly replayed;
    # receiver can read the durable ledger and deduplicate by event_id.
    for item in s.get("notification_events",[]):
        if item["delivery"]!="pending":continue
        item["delivery"]="attempted";persist()
        try:item["delivery"]=deliver(item)
        except urllib.error.HTTPError as exc:item["delivery"]="rejected_http_"+str(exc.code)
        except Exception:item["delivery"]="uncertain"
        print("HITEL_EVENT_DELIVERY",item["payload"]["event_id"],item["delivery"],flush=True)
        persist()
