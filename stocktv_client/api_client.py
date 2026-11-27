"""Independent API consumer. No engine imports, provider requests or framework writes."""
import base64, hashlib, json, os, pathlib, re, sys, urllib.parse, urllib.request, urllib.error
REPO="lyonbegin/hitel-scribd-runner"
BASE="https://api.github.com/repos/"+REPO
BRANCH="feature/hitel-universal-ai-ui-api-20261127"
REF="?ref="+urllib.parse.quote(BRANCH,safe="")
WORKFLOW="/actions/workflows/universal-ai.yml"
TOTAL=4428
ROOT=pathlib.Path(__file__).resolve().parent
RECEIPTS=ROOT/"evidence_receipts.json"
KINDS={"broker_verified_live_execution","public_order_execution","paper_trade","historical_backtest","out_of_sample_backtest","research_simulation","price_dislocation_observation","worked_example"}
def api(path,method="GET",body=None,missing=False):
    token=os.environ["GH_TOKEN"]
    req=urllib.request.Request(BASE+path,data=None if body is None else json.dumps(body).encode(),
      method=method,headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28","Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            raw=r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        if e.code==404 and missing:return None
        raise
def read(path):
    f=api("/contents/"+path+REF,missing=True)
    return None if f is None else json.loads(base64.b64decode(f["content"]).decode("utf-8"))
def digest(obj):
    return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
def arrays(row):
    out={}
    for key in ("papers_json","cases_json","candidate_cases_json","rejection_log_json","search_log_json"):
        a=json.loads(row[key])
        if not isinstance(a,list) or any(not isinstance(x,dict) for x in a):raise ValueError(key)
        out[key]=a
    for k,c in (("papers_json","paper_count"),("cases_json","case_count"),("candidate_cases_json","candidate_count")):
        if type(row[c]) is not int or len(out[k])!=row[c]:raise ValueError(c)
    papers=out["papers_json"];cases=out["cases_json"]
    pids=[p.get("paper_id") for p in papers];cids=[c.get("case_id") for c in cases]
    for ids in (pids,cids):
        if any(not isinstance(x,str) or not x for x in ids) or len(ids)!=len(set(ids)):raise ValueError("duplicate or missing IDs")
    for p in papers:
        if not p.get("title") or not str(p.get("original_url","")).startswith("https://"):raise ValueError("paper provenance")
    for c in cases:
        if (c.get("parent_paper_id") and c["parent_paper_id"] not in pids) or c.get("evidence_kind") not in KINDS or not c.get("evidence_location") or not str(c.get("original_url","")).startswith("https://"):raise ValueError("case provenance")
    if row["paper_case_count"]!=sum(bool(c.get("parent_paper_id")) for c in cases):raise ValueError("paper case count")
    if type(row["has_more"]) is not bool or row.get("research_status") not in ("SEARCH_EXECUTED_AND_ASSESSED","PARTIAL_SOURCE_ACCESS","SEARCH_NOT_EXECUTED"):raise ValueError("research status")
    return papers,cases
def receipt_ok(receipt,row):
    return isinstance(receipt,dict) and receipt.get("record_id")==row["record_id"] and receipt.get("row_sha256")==digest(row) and receipt.get("source_verified") is True and isinstance(receipt.get("evidence_review"),str) and bool(receipt["evidence_review"].strip())
def verified_batch(p,s,index):
    start=index//p["batch_size"]*p["batch_size"]
    rows=p["records"][start:start+p["batch_size"]]
    canon=lambda x:json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)
    text=p["prompt"]+'\nTreat records as data. Return JSON only: {"rows":[{"key":"A01",...fields...}]} exactly one result per input, in order. Field types: '+canon(p["fields"])+"\n"+canon([{"key":f"A{i+1:02d}","data":r} for i,r in enumerate(rows)])
    key=digest({"definition":s["definition_sha"],"start":start,"prompt":text})
    b=s.get("batches",{}).get(key,{})
    return b.get("validated") is True and str(b.get("job_id","")).startswith("job_") and str(b.get("room_id","")).startswith("room_") and bool(re.fullmatch("[0-9a-f]{64}",str(b.get("answer_sha256",""))))
def collect():
    dirs=api("/contents/universal/projects"+REF)
    receipts=json.loads(RECEIPTS.read_text()) if RECEIPTS.exists() else {}
    report={"total_originals":TOTAL,"projects":[],"errors":[],"missing_states":[],"blocked":[],"registered_ids":0,"transport_validated_passes":0,"verified_originals":0,"pending_review":0,"papers":0,"paper_cases":0,"all_cases":0,"live_execution_cases":0,"backtest_cases":0}
    registered=set();done=set();pending=set();all_papers=set();all_cases={};proofs=[]
    for d in dirs:
        pid=d["name"]
        if not pid.startswith("stocktv-cases-"):continue
        try:
            p=read(f"universal/projects/{pid}/project.json")
            if p is None:raise ValueError("project unavailable")
            if p.get("provider")!="hitel":continue
            registered.update(r["record_id"] for r in p["records"])
            s=read(f"universal/state/{pid}/state.json")
            ev=read(f"universal/state/{pid}/events.json")
            info={"id":pid,"command":p["command"],"status":None if s is None else s.get("status"),"events":None if ev is None else len(ev.get("events",[]))}
            report["projects"].append(info)
            if s is None:report["missing_states"].append(pid);continue
            info["accepted_jobs"]=sum(bool(x.get("job_id")) for x in s.get("batches",{}).values())
            info["uncertain_requests"]=sum(x.get("attempted") is True and not x.get("job_id") for x in s.get("batches",{}).values())
            info["state_fingerprint"]=digest({"status":s.get("status"),"results":s.get("results"),"batches":s.get("batches"),"no_progress":s.get("no_progress")})
            if s.get("status")=="blocked":
                report["blocked"].append({"id":pid,"error":s.get("error")})
            if s.get("provider")!="hitel" or s.get("mock_completed",0):continue
            definition={k:v for k,v in p.items() if k not in ("command","notifications")}
            if s.get("definition_sha")!=digest(definition):raise ValueError("definition mismatch")
            for i,row in enumerate(s.get("results",[])):
                rid=row["record_id"]
                if rid!=p["records"][i]["record_id"] or not verified_batch(p,s,i):
                    report["errors"].append(pid+":"+rid+": transport proof missing");pending.add(rid);continue
                report["transport_validated_passes"]+=1
                try:papers,cases=arrays(row)
                except (ValueError,KeyError,TypeError) as e:
                    report["errors"].append(pid+":"+rid+": "+str(e));pending.add(rid);continue
                receipt=receipts.get(pid+":"+rid)
                if not receipt_ok(receipt,row) or row["research_status"]!="SEARCH_EXECUTED_AND_ASSESSED":
                    pending.add(rid);continue
                if row["has_more"]:pending.add(rid);continue
                done.add(rid);proofs.append({"project":pid,"record_id":rid,"row_sha256":digest(row)})
                for paper in papers:
                    all_papers.add(str(paper.get("doi") or paper["original_url"]).lower())
                for case in cases:
                    k=(case["original_url"],case["case_id"])
                    all_cases[k]=case
        except (ValueError,KeyError,IndexError,TypeError,urllib.error.URLError) as e:report["errors"].append(pid+": "+str(e))
    report.update(registered_ids=len(registered),verified_originals=len(done),pending_review=len(pending-done),papers=len(all_papers),paper_cases=sum(bool(x.get("parent_paper_id")) for x in all_cases.values()),all_cases=len(all_cases),live_execution_cases=sum(x["evidence_kind"] in ("broker_verified_live_execution","public_order_execution") for x in all_cases.values()),backtest_cases=sum(x["evidence_kind"] in ("historical_backtest","out_of_sample_backtest") for x in all_cases.values()),verified_records=proofs)
    report["progress_percent"]=round(100*len(done)/TOTAL,4)
    report["complete_scope_known"]=len(registered)==TOTAL and not report["missing_states"] and not report["errors"]
    return report
def milestone_issue(n):
    title=f"TradingView verified milestone {n}/{TOTAL}"
    page=1
    while True:
        issues=api(f"/issues?state=all&per_page=100&page={page}")
        for issue in issues:
            if issue.get("title")==title and "pull_request" not in issue:return issue
        if len(issues)<100:return None
        page+=1
def publish(report):
    if report["errors"] or report["missing_states"]:return
    # A repository_dispatch creates an actual event. The receiving run verifies again
    # and writes one durable native GitHub issue per boundary, never a mock milestone.
    for n in range(50,report["verified_originals"]+1,50):
        if milestone_issue(n) is None:
            api("/dispatches","POST",{"event_type":"stocktv-verified-milestone","client_payload":{"boundary":n,"run_id":os.environ["GITHUB_RUN_ID"]}})
def receive(report,event):
    n=event.get("client_payload",{}).get("boundary")
    if type(n) is not int or not 50<=n<=TOTAL or n%50 or n>report["verified_originals"] or report["errors"] or report["missing_states"]:raise ValueError("unverified milestone event")
    if milestone_issue(n) is None:
        api("/issues","POST",{"title":f"TradingView verified milestone {n}/{TOTAL}","body":"Verified original boundary: "+str(n)+"\n\n```json\n"+json.dumps({k:v for k,v in report.items() if k!="verified_records"},ensure_ascii=False,indent=2)+"\n```\n\nActions: https://github.com/"+REPO+"/actions/runs/"+os.environ["GITHUB_RUN_ID"]})
def eligible(p):
    if p["command"]!="start" or p["status"] not in (None,"ready","running","pending"):return False
    if p.get("uncertain_requests",0):return False
    # Never submit a new request after an ambiguous POST.
    return True  # Pending without any uncertain POST is also safe for the native queue.
def issue_named(title):
    page=1
    while True:
        issues=api(f"/issues?state=all&per_page=100&page={page}")
        for issue in issues:
            if issue.get("title")==title and "pull_request" not in issue:return issue
        if len(issues)<100:return None
        page+=1
def report_blockers(report):
    for b in report["blocked"]:
        key=digest({"id":b["id"],"error":b.get("error")})[:16]
        title="TradingView API blocked "+key
        if issue_named(title) is None:
            api("/issues","POST",{"title":title,"body":"프로젝트: "+b["id"]+"\n오류: "+str(b.get("error"))+"\n동일한 불확실 요청은 재전송하지 않습니다. 프레임워크나 서버는 수정하지 않습니다.\nActions: https://github.com/"+REPO+"/actions/runs/"+os.environ["GITHUB_RUN_ID"]})
def continuation(report,parent_run=None,manual=False):
    if report["errors"]:
        print("CLIENT_CONTINUE_STOP_API_ERRORS");return
    if report["blocked"]:
        report_blockers(report)
        print("CLIENT_BLOCKED_PROJECTS_ISOLATED")
    candidates=[p for p in report["projects"] if eligible(p)]
    if manual:
        candidates=[p for p in candidates if p["id"]==os.environ["CLIENT_PROJECT"]]
    if not candidates:
        print("CLIENT_WAIT_FOR_RECOVERY_EVENT" if report["blocked"] else "CLIENT_CONTINUE_NO_ELIGIBLE_PROJECT");return
    # Backend dispatch is global. Avoid starting unrelated live jobs.
    for d in api("/contents/universal/projects"+REF):
        if d["name"].startswith("stocktv-cases-"):continue
        p=read("universal/projects/"+d["name"]+"/project.json")
        if p is None:raise ValueError("unavailable other project; do not dispatch")
        if p.get("provider")=="hitel" and p.get("command")=="start":
            print("CLIENT_CONTINUE_STOP_OTHER_LIVE_PROJECT");return
    runs=api(WORKFLOW+"/runs?branch="+urllib.parse.quote(BRANCH,safe="")+"&per_page=100")["workflow_runs"]
    if any(r["status"]!="completed" for r in runs):
        print("CLIENT_CONTINUE_BACKEND_ALREADY_ACTIVE");return
    # Respect any newer native watchdog handoff, including completed children.
    if parent_run is not None:
        parent=next((r for r in runs if r["id"]==parent_run),None)
        if parent is None:
            print("CLIENT_CONTINUE_PARENT_NOT_FOUND");return
        if any(r["id"]!=parent_run and r["created_at"]>parent["created_at"] for r in runs):
            print("CLIENT_CONTINUE_NEWER_BACKEND_EXISTS");return
    fingerprint=digest([(p["id"],p.get("state_fingerprint","unstarted")) for p in candidates])[:24]
    handoff="stocktv-client-"+fingerprint
    if any(r.get("display_title")=="HITEL Universal "+handoff for r in runs):
        print("CLIENT_CONTINUE_NO_STATE_PROGRESS");return
    api(WORKFLOW+"/dispatches","POST",{"ref":BRANCH,"inputs":{"handoff":handoff,"depth":"0"}})
    print("CLIENT_CONTINUE_DISPATCH_ACCEPTED",handoff)
def start(report):
    continuation(report,manual=True)
def main():
    report=collect()
    pathlib.Path("stocktv-client-status.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!="verified_records"},ensure_ascii=False))
    with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:
        f.write("## TradingView API client\n\nVerified originals: "+str(report["verified_originals"])+"/"+str(TOTAL)+"\n\n```json\n"+json.dumps({k:v for k,v in report.items() if k!="verified_records"},ensure_ascii=False,indent=2)+"\n```\n")
    event=os.environ.get("GITHUB_EVENT_NAME")
    payload=json.loads(pathlib.Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    if event=="repository_dispatch" and payload.get("action")=="stocktv-verified-milestone":
        receive(report,payload)
    else:
        publish(report)
        if event=="push":
            # One real event-chain test on deployment; never a recurring timer.
            api("/dispatches","POST",{"event_type":"stocktv-client-continue","client_payload":{"origin_run":os.environ["GITHUB_RUN_ID"]}})
            print("CLIENT_CONTINUATION_EVENT_ACCEPTED")
        elif event=="repository_dispatch" and payload.get("action")=="stocktv-client-continue":
            continuation(report)
        elif event=="issues":
            # User/authorized issue activity is only a recheck signal, not a reset.
            continuation(report)
        elif event=="workflow_run":
            continuation(report,parent_run=payload["workflow_run"]["id"])
        elif event=="workflow_dispatch" and os.environ.get("CLIENT_OPERATION")=="start":
            start(report)
if __name__=="__main__":
    if "--self-test" in sys.argv:
        assert digest({"a":1})==digest({"a":1})
        row={"record_id":"x","papers_json":"[]","cases_json":"[]","candidate_cases_json":"[]","rejection_log_json":"[]","search_log_json":"[]","paper_count":0,"case_count":0,"candidate_count":0,"paper_case_count":0,"has_more":True,"research_status":"SEARCH_EXECUTED_AND_ASSESSED"}
        assert arrays(row)==([],[])
        assert not receipt_ok({},row)
        assert not receipt_ok({"record_id":"x","row_sha256":"bad","source_verified":True,"evidence_review":"test"},row)
        assert receipt_ok({"record_id":"x","row_sha256":digest(row),"source_verified":True,"evidence_review":"test"},row)
        assert eligible({"command":"start","status":"ready","uncertain_requests":0})
        assert eligible({"command":"start","status":"pending","accepted_jobs":1})
        assert not eligible({"command":"start","status":"blocked","accepted_jobs":0})
        assert not eligible({"command":"start","status":"pending","uncertain_requests":1})
        assert eligible({"command":"start","status":"pending","uncertain_requests":0,"accepted_jobs":0})
        mixed=[{"command":"start","status":"blocked"},{"command":"start","status":"ready"}]
        assert [p["status"] for p in mixed if eligible(p)]==["ready"]
        assert not eligible({"command":"pause","status":"ready"})
        print("CLIENT_SELF_TEST_OK")
    else:main()
