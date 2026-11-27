"""Bounded next-run reconciliation. Never blindly repeat dispatch after uncertain POST."""
import json,os,pathlib,subprocess
from engine import sha,definition,read,ROOT,live_allowed
def gh(*args):return subprocess.check_output(["gh","api",*args],text=True)
def pending():
    for p in (ROOT/"projects").glob("*/project.json"):
        project=read(p)
        if project.get("command")!="start":continue
        s=ROOT/"state"/p.parent.name/"state.json"
        if not s.exists():
            if project.get("provider")=="mock" or live_allowed(project):return True
        else:
            state=read(s)
            if state.get("definition_sha")==sha(definition(project)) and state.get("status") not in ("complete","blocked"):return True
    return False
def main():
    if not pending():print("WATCHDOG_NO_PENDING_WORK");return
    depth=int(os.getenv("HANDOFF_DEPTH","0"))
    if depth>=20:print("WATCHDOG_BUDGET_EXHAUSTED");return
    repo=os.environ["GITHUB_REPOSITORY"]; branch=os.environ["GITHUB_REF_NAME"]
    parent=os.environ["GITHUB_RUN_ID"]; token="from-"+parent
    endpoint=f"repos/{repo}/actions/workflows/universal-ai.yml"
    def observed():
        data=json.loads(gh(endpoint+"/runs","-f","branch="+branch,"-f","per_page=100","-X","GET"))
        return any(r.get("display_title")=="HITEL Universal "+token for r in data["workflow_runs"])
    try:
        if observed():print("WATCHDOG_CHILD_EXISTS");return
    except subprocess.CalledProcessError:
        print("WATCHDOG_DISPATCH_NOT_REGISTERED_OR_UNAUTHORIZED");return
    payload={"ref":branch,"inputs":{"handoff":token,"depth":str(depth+1)}}
    r=subprocess.run(["gh","api","-X","POST",endpoint+"/dispatches","--input","-"],input=json.dumps(payload),text=True)
    if r.returncode==0:print("WATCHDOG_DISPATCH_ACCEPTED")
    else:
        # Do not replay an uncertain submission.
        try: print("WATCHDOG_CHILD_FOUND" if observed() else "WATCHDOG_DISPATCH_UNCONFIRMED_NO_REPOST")
        except subprocess.CalledProcessError:print("WATCHDOG_LOOKUP_FAILED_NO_REPOST")
if __name__=="__main__":main()
