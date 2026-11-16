# ProcureFlow 2Y — hosted browser evidence review (2026-11-17 02:50 KST)

## Scope and immutable controls
Research branch only. No changes to the 930,379-key notice index, original 187 Release pairs, source/repair workflows or PC runner. No login, API key, bypass, procurement transaction, or user submission.

## Evidence checked
- [Actions 43921212068](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43921212068): all four jobs succeeded (public UI 133488674587; isolated PostgreSQL 133488674973; bootstrap 133488675092; public JS 133488675290).
- Diagnostic artifacts: `procureflow-websquare-bootstrap-43921212068` (ID 14253372615, 198723 bytes), `procureflow-g2b-public-ui-43921212068` (ID 14252649253, 8030 bytes), `procureflow-public-websquare-js-43921212068` (ID 14254422165, 2515 bytes). These sizes are artifact metadata, **not** independently recomputed SHA256.
- Directly read job logs for bootstrap and public UI. Bootstrap classification output: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43921212068

## New, material finding
The **G2B homepage is no longer consistently empty**. The bootstrap job's 2026-11-16 17:43:06 UTC record reports HTTP 200, `document.readyState=complete`, `WebSquare=object`, `bodyChildren=7`, `bodyTextLength=461`, `htmlLength=611632`, `activeElement=INPUT`, and 28 scripts. Earlier runs recorded `bodyChildren=0`. Thus a blanket claim that all three portals always return an empty DOM is now disproved. This is a homepage bootstrap success, not contract data collection.

Data hub homepage and both report URLs 112R/113R still show `bodyChildren=0` with document HTTP 200. Shopping homepage also shows `bodyChildren=0` and HTTP 200. Classification reports two OIDC 302 observations for each target. G2B bootstrap shows two **client-blocked POST** requests and no observed POST responses; its `non_static_response_count=6` is not proof of contract results. Data hub and shopping report no validated POST result. The separate public UI job still has no contract controls or validated list/detail/second-page data.

## Interpretation and next bounded experiment
1. Compare the rendered G2B DOM and screenshot from artifact 14253372615 with the public UI job's DOM; isolate timing, WebSquare bootstrap sequence and whether the visible controls expose **public read-only contract navigation**. Do not assume the homepage's 461 text characters are a contract list.
2. Preserve the request method, URL, status, original bytes, SHA256, official identifiers and first/second page only if a public read-only contract endpoint is genuinely observed. Explicitly separate client-blocked POST from server failure. Do not relax the guard for unclassified endpoints.
3. Investigate data hub 112R/113R and shopping MAS/public catalog independently; do not infer public access to buyer-only delivery-order actions.
4. Keep actual ingestion and JOIN verification marked **NOT VERIFIED** until official source rows and independently hashed payloads are available. Fixture schema success does not qualify.

## Stage2 boundary
Four previously zero-processed shards 169–172 each processed 5,000 keys in runs 43868699164, 43869729252, 43870757534, 43871778282. Supervisor 43872817232 reported no further zero-processed shards but `all_stage2_verified=false`. The 9,877 unknown status outcomes must not be relabeled zero-bid. Do not recrawl unrelated shards or the notice index.

**Completion status: NOT COMPLETE.** This review records a reproducible homepage-rendering improvement, not verified contract, supplier, MAS or delivery-order rows.
