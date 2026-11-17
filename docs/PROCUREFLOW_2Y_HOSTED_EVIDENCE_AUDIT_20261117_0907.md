# ProcureFlow hosted evidence follow-up — 2026-11-17 09:07 KST

## Source of truth and scope
Reviewed `docs/PROCUREFLOW_2Y_PUBLIC_WEB_RECON_20261116.md`, `.github/workflows/procureflow-contract-web-probe.yml`, `.github/workflows/procureflow-stage2-unprocessed-repair.yml`, and the separate `lyonbegin/procureflow` repository. This is a **read-only evidence audit**, not a claim of contract data ingestion. Preserve the 930,379 notice index, 187 original ZIP/status pairs, all operational workflows and the disabled PC runner. Do not replay the 176 other shards.

## Hosted run 43981142083
Source: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43981142083

All four jobs succeeded (public UI, JS clues, WebSquare bootstrap, isolated PostgreSQL schema). The WebSquare bootstrap job ran three Python regression tests successfully. Its emitted `BOOTSTRAP_CLASSIFICATION` has five entries: G2B, data portal, 112R, 113R and shop. **Each** has `http_status=200`, `dom_empty=true`, `websquare_loaded=true`, `oidc_302_count=2`, `observed_post_count=0`, `verified_data_rows=0`, `classification=NOT_VERIFIED`. No observed POST response can be used to infer a zero-row contract result. In this run, there is no evidence that a legitimate read-only contract list, detail, pagination, 112R/113R report, MAS product search or delivery-order response succeeded. HTTP 200 belongs to initial document/bootstrap, not a validated data request.

Artifact metadata from GitHub Actions:
- Public UI: ID 14282949130, 8,400 bytes, advertised ZIP SHA256 `d80e48f6a38423e893253539cbdf776150342d393294a91299357b6a3df42c2d`.
- JS clues: ID 14282869810, 2,514 bytes, advertised ZIP SHA256 `c8e32c6210be608ab44d863aeaa77f8667ae405a6db82092749ad0ae19da2e71`.
- Bootstrap: ID 14281564366, 88,254 bytes, advertised ZIP SHA256 `c2be0f91ea1624a4299e566ec4e172a819f5b92fca174d623f9ccb96e38478f2`.

These hashes are **GitHub-reported artifact digests**, not independently rehashed downloaded bytes; they must not be called independent ZIP integrity verification. The three artifacts were uploaded and are not expired as of this audit.

## Targeted Stage2 repair 43868699164
Source: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43868699164

The repair job and conditional continuation job succeeded. The job's `DETAIL_FINAL` for shard **169 only** states: processed=5,000 of 5,000, verified_complete=3,385, no_opening_data=1,512, no_bidder_rows_unverified=103, verified_bidder_rows=331,902, errors=0. `SHARD_CHECKPOINT_VERIFIED` reports an appended ZIP 41,473,929 bytes, SHA256 `a6c35cd037bb84d6b32261a73b1694bda8d402bc0eb3047ff4b4767315f4553d`; status JSON 483 bytes, SHA256 `4cb4201936d78322681e1ddd50dd1747c1a97fc2d0946a0e6a7d0bc742ed5165`. These are collector-reported hashes and **not independent downloaded-byte checks**. The supervisor explicitly records `all_stage2_verified=false`, `complete_shards_this_run=0`, `need_continue=true`, `new_shards_remaining=3`, `source_index_unchanged=true`, `award_linkage_verified=false`, `excel_integration_verified=false`. Therefore success of this workflow is not completion of Stage2, and unknown/empty bidder results must remain unverified. Verify 170–172 using their own runs and preserved original ZIPs, not the success flag of run 43868699164.

## Required next proof, in order
1. Preserve the original queue and inspect subsequent repair runs for shards 170–172. Independently download, rehash and CRC-check the newly appended ZIPs, compare status counts and check duplicate keys/coverage. Do not re-fetch the notice index or launch other shard repairs.
2. For the public UI, inspect a complete same-origin browser navigation/redirect trace for the bootstrap lifecycle and locate a publicly accessible contract search route. A transient nonempty DOM is not a validated data endpoint; distinguish browser-aborted POST from server HTTP responses.
3. Only when a public, unauthenticated **read-only** data request is actually observed, record the full permitted request URL/method, original response bytes and SHA256, at least one list item, corresponding detail, and pages 1–2. Do not fabricate endpoints or use authenticated requests.
4. Keep notice, bidder, opening, award, contract, negotiated reason, consortium, amendment, delivery, supplier and source evidence in independent entities. Validate official round/category/execution/contract/supplier keys and distinct notice/contract/delivery dates. Isolated PostgreSQL fixture success is not live ingestion or production JOIN verification.

**Completion status: NOT VERIFIED.** No notification or full completion claim is warranted.
