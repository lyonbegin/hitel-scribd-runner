# Universal Actions backend — API contract (v0.1)
The backend is GitHub Actions, not Railway or a Pages-hosted Python server. The existing authorized HITEL service remains the AI transport only. No Scribd task or production workflow is reused or reactivated.

UI and other programs call the same GitHub REST API with a user-authorized token. No token is embedded in Pages or persisted by the UI. Token permissions: Contents read/write on the target repository, Actions read/write if dispatch or cancellation is needed. Never put secrets or confidential data in a public repository. For confidential work install the engine/workflow in a private repository; the public Pages UI can target that repository via the user's authorized token.

## Project creation / start
PUT https://api.github.com/repos/{owner}/{repo}/contents/universal/projects/{project_id}/project.json
JSON body: message, branch, content (UTF-8 project JSON encoded in base64). For update supply existing file sha from GET. GitHub push trigger on feature/hitel-universal-ai-ui-api-20261127 starts the engine. If a request is accepted by Contents API it means the commit exists, not that Actions or the AI has finished.

Project JSON example:
{
  "project_id":"demo-001",
  "command":"start",
  "provider":"mock",
  "task_id":"",
  "batch_size":2,
  "prompt":"Categorize each item.",
  "fields":{"category":"string","score":"number","valid":"boolean"},
  "records":[{"record_id":"1","text":"Synthetic sample"}]
}

provider=mock explicitly produces synthetic results and verified_ai_completed=0. provider=hitel requires a newly approved server-side task_id and repository variable HITEL_ALLOW_LIVE=true. Server OIDC audience, request and room authorization must be registered for the new producer. No silent fallback. Existing scribd-18109 is rejected. Schema v0.1 supports string/number/boolean fields; more complex domain validation is not implemented. Single project package currently limited to 850KB in UI (700KB file input). Larger input needs chunked manifests, not implemented yet. CSV export is supported; XLSX is not yet supported.

## Read / control / monitor
GET /repos/{owner}/{repo}/contents/universal/projects/{id}/project.json?ref={branch}
PUT same path with command=pause (same immutable definition and existing sha). Resume with command=start. Changing inputs/prompt/schema requires new project_id; do not replace already verified data. A blocked state is not automatically cleared by pause/resume: operator review required.
GET /repos/{owner}/{repo}/contents/universal/state/{id}/state.json?ref={branch}
GET /repos/{owner}/{repo}/contents/universal/state/{id}/results.csv?ref={branch}
GET /repos/{owner}/{repo}/actions/runs?branch={branch}
POST /repos/{owner}/{repo}/actions/workflows/universal-ai.yml/dispatches with {"ref":branch,"inputs":{...}} only after the workflow is registered on the default branch.
POST /repos/{owner}/{repo}/actions/runs/{run_id}/cancel is a GitHub run cancellation; it does not cancel an already accepted AI request.

Checkpoints are written and pushed BEFORE external POST, then after job acceptance, then after result validation. If push fails no new AI POST is permitted. HTTP GET reconciles uncertain acceptance; do not resend unknown requests. GitHub Actions serializes the branch's runs. Engine polls every 10s, bounds no-progress and respects Retry-After. Runner shutdown preserves already pushed checkpoints. Pause is cooperative at the next batch/status check. GitHub branch access is the security boundary; protect write access. All branch data and checkpoints are visible to anyone with read access. This v0.1 is a prototype, not a production multi-tenant service.

## Deployment caveat
GitHub Pages must be enabled in repository Settings > Pages (source GitHub Actions) and the Pages environment must allow the deployment branch. Workflow dispatch/scheduled watchdog require the workflow to exist on the default branch; push triggers on this feature branch can operate before that registration. No existing main workflow is changed in this feature branch. Automatic handoff must not be reported as operational until GitHub actually accepts it. Do not use a long-lived public runner as an HTTP server.
