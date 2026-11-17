# Hosted public web evidence reconciliation — 2026-11-17 13:11 KST

## Sources actually read
- Research audit: docs/PROCUREFLOW_2Y_PUBLIC_WEB_RECON_20261116.md
- Public probe workflow: .github/workflows/procureflow-contract-web-probe.yml
- Selective recovery workflow: .github/workflows/procureflow-stage2-unprocessed-repair.yml
- Hosted probe run: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43997169185 (job 133752727814 and 133752727795 logs)
- Zero-processed repair run: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43868699164
- Separate repository: lyonbegin/procureflow (repository metadata checked)

## Observed 2026-11-17 01:42 UTC
The bootstrap audit logged complete_probe_coverage=true, missing_targets=[], all five targets classification=NOT_VERIFIED and verified_data_rows=0.

| Target | HTTP | Empty DOM | OIDC GET 302 | Confirmed client-guard failed POST | Observed POST | Verified rows |
|---|---:|---|---:|---:|---:|---:|
| www.g2b.go.kr | 200 | no | 2 | 2 | 0 | 0 |
| data.g2b.go.kr | 200 | yes | 2 | 0 | 0 | 0 |
| data.g2b.go.kr 112R | 200 | no | 2 | 6 | 0 | 0 |
| data.g2b.go.kr 113R | 200 | no | 2 | 6 | 0 | 0 |
| shop.g2b.go.kr | 200 | yes | 2 | 0 | 0 | 0 |

IMPORTANT: **Not all five DOMs are empty.** In particular the report pages 112R and 113R have nonempty DOMs, but no verified list/detail/pagination. The two failed POST counts for G2B and six each for reports are **confirmed client-side guarded failures**, not successful server responses and not proof that the server rejected the requests. Do not confuse the zero observed POST responses with the empty HTTP 200 bidder-result case in Stage2.

The UI-probe shopping log independently showed 20 requests, zero XHR paths, zero POST paths, zero visible controls, no HTTP errors, no page errors, and a WebSquare object with empty body. This is bootstrap success only.

Artifacts on run 43997169185:
- websquare-bootstrap id 14291280060; GitHub-reported archive SHA256 07a93e7aae8d65da5926c88588a8aa5c21ce2db3cfbb1a358d6596a070dafed3; 361516 bytes
- public-websquare-js id 14290477364; GitHub-reported archive SHA256 b5efd09b519704abc150e3dcf3a3464ab26d55a689ede8ec30de15fd94f98d2c; 2515 bytes
- g2b-public-ui id 14290108168; GitHub-reported archive SHA256 b51d39f23175d0a52db92d9ed9652edc321dbdaaf62489ef4bb99a7d15aa32e6; 7619 bytes

These are GitHub metadata digests, **not independent byte-level rehashes** of the downloaded archives. No claim of validated contract/MAS/delivery rows follows from the successful jobs.

## Recovery boundary
Run 43868699164 completed its zero-processed repair job and continuation dispatch, but job success does not prove four-shard byte-level completeness. Do not re-fetch 930379 notice keys, modify original 187 ZIP/status Release pairs, restart the PC runner, or bulk retry other shards. Treat `no_bidder_rows_unverified` as unknown until actual response and opening-state evidence resolve it.

## Next bounded research
1. Inspect saved browser requestfailure metadata and the code's exact client-guard condition; compare with observed 200 response metadata. Do not label a blocked POST as a server 200 empty list.
2. For each publicly reachable page, verify a genuine contract or product list, detail, page 1/2, official source URL, and independent raw-byte SHA256 before any backfill.
3. Keep the separate 2-year contract/MAS schema distinct from preserved bidder and notice evidence; only JOIN using verified official composite keys and source evidence.
4. Independently download/re-hash the targeted repair ZIP/status assets and reconcile processed/unknown counts before any completion claim.

No authenticated operation, purchase, submission, runner restart or production data mutation was performed in this audit.
