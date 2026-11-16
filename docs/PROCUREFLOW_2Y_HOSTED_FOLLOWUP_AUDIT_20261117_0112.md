# ProcureFlow 2Y — 2026-11-17 01:12 KST hosted follow-up audit

## Scope and immutable boundaries
Research branch only: `research/procureflow-contract-web-probe-20261116`. Existing 930,379 notice keys (721 verified days / ten unverified), original 187 Release pairs, Stage2 operational workflows and PC self-hosted runner are not to be modified or restarted. No API key assumption, login, bypass, bid, signature, purchase or submission.

## Latest completed run independently inspected
- [GitHub Actions 43895030445](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43895030445), created 2026-11-16 15:19:07 UTC (2026-11-17 00:19:07 KST), completed successfully.
- Four jobs confirmed success by GitHub job API: public UI (job 133396140181), WebSquare bootstrap (133396140529), isolated Postgres schema (133396140532), and public JS inspection (133396140738).
- The bootstrap job log was read directly. G2B: document HTTP 200, readyState complete, WebSquare object, 29 script elements, bodyChildren=0, bodyTextLength=0. Data hub: document HTTP 200, WebSquare object, 32 scripts, bodyChildren=0, bodyTextLength=0. Shopping: document HTTP 200, WebSquare object, 27 scripts, bodyChildren=0, bodyTextLength=0.
- Public UI job log was read directly. G2B: visible contract controls none, POST paths none. Data hub: report URLs 113R and 112R both open as pages but body excerpts empty, visible controls none, POST paths none. Shopping: visible controls none, POST paths none. The data hub's attempted POST requests to `/co/coz/coza/util/getSession.do` and `/ai/AiComm/selectMstrApiUserIdKey.do` appear as `net::ERR_ABORTED`; they are not successful public report data responses. They cannot be treated as list/detail endpoints.
- A success conclusion means diagnostics executed, not that any contract, supplier, MAS or delivery record was extracted. HTTP 200 applies to the bootstrap document, not to a contract-result payload. OIDC 302 is evidence of redirects, not proof all public functions require authentication.
- Public bootstrap probe explicitly blocks all POST; public UI probe permits only limited read-named POST paths and blocks mutation-like paths. This distinction must be retained when interpreting blocked requests.

## Confirmed remaining gap
No verified public contract list+detail+second-page response with byte SHA256; no verified 112R/113R report payload; no verified public shopping product or delivery-order response; no real contract ingestion or real-data FK/JOIN audit. Existing isolated `procureflow_2y` PostgreSQL schema and fixture tests are not evidence of production ingestion.

## Stage2 status boundary
Previously zero-processed shards 169–172 were each processed for 5,000 keys in four GitHub-hosted runs (43868699164, 43869729252, 43870757534, 43871778282). Supervisor 43872817232 reported zero further zero-processed shards and `all_stage2_verified=false`. The four repairs recorded 368 unknown outcomes, making 9,877 unknown outcomes across original+repair status summaries. This is a status-log total, not a full independent payload recount. Empty `successBidInfo` remains unverified and must not be converted to a confirmed zero-bid outcome.

## Next bounded investigation
1. Capture and compare precise WebSquare runtime errors, script load failures and observed navigation to explain empty body; do not synthesize privileged endpoints.
2. Once a genuinely public contract read endpoint is observed, retain a minimal list, detail and second page as raw bytes with original URL, HTTP status, page number, timestamp, SHA256 and official keys.
3. Validate notice round/classification/progress, contract revision, supplier official key, and separate notice/signed/delivery dates before any historical backfill.
4. Preserve raw response bytes and audit actual duplicate, missing and JOIN results. Until then classify all new data families as unverified/not collected.
