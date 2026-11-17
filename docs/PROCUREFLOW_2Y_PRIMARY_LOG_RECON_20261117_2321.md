# 2Y hosted primary-log reconciliation — 2026-11-17 23:21 KST

## Scope and preservation
Read-only inspection of the research branch's `PROCUREFLOW_2Y_PUBLIC_WEB_RECON_20261116.md`, public UI workflow, selective zero-processed repair workflow, `lyonbegin/procureflow` repository metadata, and primary Actions job logs. No changes to original 930,379 notice keys, 187 original Release ZIP/status pairs, original/recovery operational workflows, or self-hosted PC runners. No login, purchasing, bidding or submission.

## Primary evidence and distinction between workflow success and source completeness
1. [Selective repair 43868699164](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43868699164), job 133303823234, `DETAIL_FINAL`: shard 169 selected/processed 5,000; verified_complete 3,385; no_opening_data 1,512; no_bidder_rows_unverified 103; verified bidder rows 331,902; errors 0. `SHARD_CHECKPOINT_VERIFIED`: stored ZIP 41,473,929 bytes, logged SHA256 `a6c35cd037bb84d6b32261a73b1694bda8d402bc0eb3047ff4b4767315f4553d`, `complete=false`, `exit_code=3`, `award_linkage_verified=false`. This log is NOT an independent download and byte hash. `SUPERVISOR_RESULT`: `new_shards_remaining=3`, `need_continue=true`. Run success is not proof of completion for shards 170–172.
2. [Public web probe 44059369280](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44059369280), job 133956916836: shopping portal initial GET 200, WebSquare defined, bodyCount 0, no observed POST response, OIDC GET 302, 22 responses. Public shopping product/delivery rows remain unverified. The bootstrap job 133956916559 independently observed delayed G2B DOM controls at about 12 seconds; initial empty DOM is therefore not a permanent impossibility finding.
3. The latest inspected public UI code waits up to 20 seconds for visible controls, then captures the screen after a further 9.5 seconds. This modified version must be evaluated against its own subsequent hosted run before claiming it fixed navigation or POST discovery.
4. The separate `procureflow_2y` schema and disposable PostgreSQL fixture test are not production source-row ingestion or actual official-key JOIN verification. A passing test with empty post-rollback source tables is intentionally not counted as completion.

## Unresolved gates
- Verify the 170–172 selective recovery checkpoints and independently download/rehash repair ZIPs, check CRC and row/status counts. Do not start other 176 shards in bulk.
- Preserve `no_bidder_rows_unverified` as unknown until actual official response status in `bidInfo` / `etcData` establishes meaning; HTTP 200 and empty `successBidInfo` do not mean verified zero bids.
- Obtain actual public, non-authenticated read-only contract list/detail/page 1/page 2 response evidence, source URLs and SHA256; separately repeat for 112R/113R and public shopping catalog/MAS/delivery data. OIDC 302 does not by itself prove every public read is login-gated.
- Independently ingest and audit contract, sole-source reason, consortium, modification, supplier, MAS, delivery and source-evidence entities; distinguish notice, contract and delivery-order dates and verify official composite keys, duplicates, missing rows and JOIN arithmetic.

**Disposition:** Partial evidence only. No whole-project completion claim, no original queue re-collection, no authentication bypass.
