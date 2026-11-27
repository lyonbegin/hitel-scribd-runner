# Universal Actions backend — API contract (v0.2)
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
POST /repos/{owner}/{repo}/actions/workflows/universal-ai.yml/dispatches with {"ref":branch,"inputs":{...}} when GitHub has registered the workflow (the branch-created workflow successfully accepted a dispatch in the recorded test).
POST /repos/{owner}/{repo}/actions/runs/{run_id}/cancel is a GitHub run cancellation; it does not cancel an already accepted AI request.

Checkpoints are written and pushed BEFORE external POST, then after job acceptance, then after result validation. If push fails no new AI POST is permitted. HTTP GET reconciles uncertain acceptance; do not resend unknown requests. GitHub Actions serializes the branch's runs. Engine polls every 10s, bounds no-progress and respects Retry-After. Runner shutdown preserves already pushed checkpoints. Pause is cooperative at the next batch/status check. GitHub branch access is the security boundary; protect write access. All branch data and checkpoints are visible to anyone with read access. This v0.1 is a prototype, not a production multi-tenant service.

## Deployment caveat
GitHub Pages must be enabled in repository Settings > Pages (source GitHub Actions) and the Pages environment must allow the deployment branch. Push and a subsequent watchdog workflow_dispatch were both verified on this feature branch. A cron schedule is not installed; the watchdog is a post-run Actions job. GitHub workflow registration and permissions must be checked when installing in another repository. No existing main workflow is changed in this feature branch. Automatic handoff must not be reported as operational until GitHub actually accepts it. Do not use a long-lived public runner as an HTTP server.

## Verified initial QA (2026-11-27 KST)
- Actions 45907244721: 7 offline tests passed; watchdog emitted WATCHDOG_DISPATCH_ACCEPTED.
- Child Actions 45907281993: run and watchdog succeeded; synthetic records demo-1, demo-2, demo-3 exported, two batches, mock_completed=3, verified_ai_completed=0; WATCHDOG_NO_PENDING_WORK.
- Pages initial 45907260438 failed; administrator enabled Pages and run 45915626971 subsequently succeeded. Updated notification UI run 45920728795 completed its deploy steps.
- No live AI, real browser session, full-size input, independent worker restart or production UI end-to-end test has been performed. The generic engine adapts the legacy transport/checkpoint validation, not all Scribd-specific recovery branches. Existing Scribd release and closed main remain untouched.

## v0.2 event notifications
Public Korean API guide (including all notification configuration, delivery payloads, receiver setup and ChatGPT Work limitations): [HITEL_UNIVERSAL_AI_PUBLIC_API_GUIDE_KO.md](../docs/HITEL_UNIVERSAL_AI_PUBLIC_API_GUIDE_KO.md). GET /repos/{owner}/{repo}/contents/universal/state/{id}/events.json?ref={branch}. Optional project.notifications config: channel none/github_pr/webhook, pr_number for approved PR, heartbeat_seconds 30-3600, events list. Settings excluded from definition hash, loaded on next run. External transport must be explicitly configured and authorized. HTTP 2xx is receiver acceptance, not ChatGPT delivery. Actual event ledger and 14 offline tests passed in 45920741445; no live webhook receiver or Work trigger has been verified. No arbitrary ChatGPT conversation POST endpoint exists in this implementation.
