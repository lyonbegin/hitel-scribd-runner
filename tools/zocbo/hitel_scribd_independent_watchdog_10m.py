#!/usr/bin/env python3
"""Independent checkpoint watchdog for the existing signed Scribd producer.
Never submit a chat message, erase an attempt, or treat unverified rows as done.
"""
import io,json,os,re,subprocess,sys,time,urllib.request,urllib.parse,zipfile
from datetime import datetime,timezone
REPO="lyonbegin/hitel-scribd-runner"
WORKFLOW="hitel-public-ai-corpus.yml"
PREFIX="HITEL Scribd AI handoff "
ACTIVE={"queued","in_progress","waiting","pending","requested"}
ARTIFACT="hitel-ai-18109-ws-recovery-checkpoint"
BASE="https://hitel-integration-api-production.up.railway.app/integrations/v1/public/"
def report(*args): print("SCRIBD_CHECKPOINT_WATCHDOG",*args,flush=True)
def api(path):
    return json.loads(subprocess.check_output(["gh","api",path],timeout=35))
def scope(r):
    return (r.get("path")==".github/workflows/"+WORKFLOW and r.get("head_branch")=="main"
            and r.get("event")=="workflow_dispatch" and str(r.get("display_title","")).startswith(PREFIX))
def runs():
    data=api(f"repos/{REPO}/actions/workflows/{WORKFLOW}/runs?per_page=100")
    return sorted((r for r in data["workflow_runs"] if scope(r)),key=lambda r:r["id"],reverse=True)
def live():
    with urllib.request.urlopen(BASE+"isolated/tasks/scribd-18109/status",timeout=15) as r:
        s=json.load(r)
    if s.get("task_id")!="scribd-18109":raise ValueError("TASK_SCOPE_MISMATCH")
    return s
def age(s):
    return (datetime.now(timezone.utc)-datetime.fromisoformat(s.replace("Z","+00:00"))).total_seconds()
def plan(rs):
    if not rs:return "no_producer"
    if any(r.get("status") in ACTIVE for r in rs):return "producer_active"
    p=rs[0]
    if p.get("status")!="completed" or p.get("conclusion") not in ("success","failure","timed_out"):
        return "hold_terminal_state"
    # Do not silently restart a manually stopped/cancelled or smoke run.
    if not re.fullmatch(PREFIX+r"(from|watchdog)-[0-9]+",p.get("display_title","")):
        return "hold_non_chain_run"
    if age(p["updated_at"])<600:return "allow_handoff_indexing"
    return "inspect_checkpoint"
class NoCrossHostAuth(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        r=super().redirect_request(req,fp,code,msg,headers,newurl)
        if r and urllib.parse.urlsplit(newurl).hostname!=urllib.parse.urlsplit(req.full_url).hostname:
            for k in ("Authorization","Accept","X-GitHub-Api-Version"):r.remove_header(k)
        return r
def checkpoint(run):
    rid=run["id"]
    jobs=api(f"repos/{REPO}/actions/runs/{rid}/jobs?filter=latest&per_page=100")["jobs"]
    ai=[j for j in jobs if j["name"]=="ai"]
    if len(ai)!=1 or not ai[0].get("started_at"):return None
    j=ai[0]
    persisted=any(s.get("name","").startswith("Preserve independently verified results") and
                  s.get("conclusion")=="success" for s in j.get("steps",[]))
    if not persisted:return None
    artifacts=api(f"repos/{REPO}/actions/runs/{rid}/artifacts?per_page=100")["artifacts"]
    valid=[a for a in artifacts if a.get("name")==ARTIFACT and not a.get("expired")
           and a["created_at"]>=j["started_at"]]
    if not valid:return None
    a=max(valid,key=lambda x:(x["created_at"],x["id"]))
    req=urllib.request.Request(f"https://api.github.com/repos/{REPO}/actions/artifacts/{a['id']}/zip",
            headers={"Authorization":"Bearer "+os.environ["GH_TOKEN"],
                     "Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"})
    with urllib.request.build_opener(NoCrossHostAuth()).open(req,timeout=60) as res:
        raw=res.read(40_000_001)
    if len(raw)>40_000_000:raise ValueError("CHECKPOINT_ARCHIVE_TOO_LARGE")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        def read(name):
            info=z.getinfo(name)
            if info.file_size>1_000_000:raise ValueError("CHECKPOINT_METADATA_TOO_LARGE")
            return json.loads(z.read(info))
        stats=read("status.json"); marker=read("supervisor-reconcile.json")
    report("exact_artifact",a["id"],"verified",stats.get("verified_ai_completed"),"phase",marker.get("phase"))
    return stats,marker
def checkpoint_plan(stats,m):
    n=stats.get("verified_ai_completed")
    if (stats.get("total")!=18109 or not isinstance(n,int) or not 5020<=n<=18109
        or stats.get("unverified_skipped")!=0 or stats.get("remaining_unverified")!=18109-n):
        return "hold_bad_checkpoint"
    if n==18109:return "all_complete"
    if m.get("phase")=="verified" and m.get("verified_after")==n and isinstance(m.get("verified_before"),int) and 0<n-m["verified_before"]<=20:
        return "resume_verified"
    # Reuse only existing bounded transport reconciliation. Do not reset a
    # budget or retry rate-limited/ambiguous delivery requests via fresh POST.
    if (m.get("phase")=="retryable_transport" and m.get("infra_retries")==1
        and m.get("verified_before")==n and m.get("error_type") in ("URLError","TimeoutError","ConnectionError")
        and isinstance(m.get("wait_seconds"),int) and 0<=m["wait_seconds"]<=600):
        return "resume_transport"
    return "hold_nonretryable_or_uncertain"
def main():
    rs=runs(); action=plan(rs);report(action)
    s=live()
    report("worker_connected",s.get("worker_connected"),"queued",s.get("queued_jobs_count"),
           "active",s.get("worker_active_jobs_count"),"recovery",s.get("worker_recovery_required_count"))
    if action!="inspect_checkpoint":return
    p=rs[0]; cp=checkpoint(p)
    if cp is None:report("hold_no_current_attempt_checkpoint");return
    decision=checkpoint_plan(*cp);report(decision)
    if decision not in ("resume_verified","resume_transport"):return
    if (decision=="resume_verified" and any(s.get(k)!=0 for k in ("queued_jobs_count",
            "worker_active_jobs_count","worker_live_jobs_count","worker_recovery_required_count"))):
        report("hold_live_or_uncertain_request");return
    time.sleep(20)
    fresh=runs()
    if plan(fresh)!="inspect_checkpoint" or fresh[0]["id"]!=p["id"]:
        report("producer_changed_no_dispatch");return
    s2=live()
    if decision=="resume_verified" and any(s2.get(k)!=0 for k in ("queued_jobs_count",
            "worker_active_jobs_count","worker_live_jobs_count","worker_recovery_required_count")):
        report("hold_live_or_uncertain_request");return
    token="from-"+str(p["id"])
    if any(r.get("display_title")==PREFIX+token for r in fresh):
        report("existing_child_no_duplicate");return
    # The existing producer's same-token ownership and concurrency fences remain intact.
    subprocess.run(["gh","workflow","run",WORKFLOW,"--repo",REPO,"--ref","main",
                    "-f","mode=full","-f","handoff_token="+token],check=True,timeout=35)
    report("checkpoint_resume_dispatch_accepted",token)
def test():
    s=dict(total=18109,verified_ai_completed=9313,unverified_skipped=0,remaining_unverified=8796)
    m=dict(phase="verified",verified_before=9293,verified_after=9313)
    assert checkpoint_plan(s,m)=="resume_verified"
    assert checkpoint_plan(s,dict(m,phase="retry_budget_exhausted"))=="hold_nonretryable_or_uncertain"
    assert checkpoint_plan(s,dict(m,verified_after=9999))=="hold_nonretryable_or_uncertain"
    retry=dict(phase="retryable_transport",infra_retries=1,verified_before=9313,error_type="URLError",wait_seconds=30)
    assert checkpoint_plan(s,retry)=="resume_transport"
    assert checkpoint_plan(s,dict(retry,error_type="HTTPError"))=="hold_nonretryable_or_uncertain"
    assert checkpoint_plan(s,dict(retry,error_type="UNCERTAIN_POST_READ_ONLY"))=="hold_nonretryable_or_uncertain"
    assert checkpoint_plan(dict(s,verified_ai_completed=18109,remaining_unverified=0),m)=="all_complete"
    assert plan([{"status":"in_progress"}])=="producer_active"
    report("offline_tests_pass")
if __name__=="__main__":
    test() if "--test" in sys.argv else main()
