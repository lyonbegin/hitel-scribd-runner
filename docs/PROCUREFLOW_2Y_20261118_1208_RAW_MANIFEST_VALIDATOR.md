# Public 2Y raw-evidence validation hardening — 2026-11-18 12:08 KST

## Verified inputs
- Original public-web audit: `docs/PROCUREFLOW_2Y_PUBLIC_WEB_RECON_20261116.md`; original 187 pairs are not a completed 187-shard audit.
- Hosted repair 43868699164, job 133303823234: segment 169 processed 5,000; verified_complete 3,385; no_opening_data 1,512; no_bidder_rows_unverified 103; bidder rows 331,902. The checkpoint SHA256 `a6c35cd037bb84d6b32261a73b1694bda8d402bc0eb3047ff4b4767315f4553d` is **log-reported**, not independently rehashed in this run. Supervisor `new_shards_remaining=3`, `all_stage2_verified=false`. Job 133307344689 dispatched continuation, but that does not prove its result.
- Hosted report 44212573143, job 134494341587: `UI-ADOXAA-038R` GET 302, bodyChildren=0, report_rows=0. No delivery order can be inferred.
- Previous 44200587595 contract unified-search page evidence and 44205491684 shop product page evidence are not verified finalized contract details or delivery orders. 112R/113R remain unverified.

## Changes
- `tools/procureflow/audit_2y_public_raw_manifest.py` provides a read-only, fail-closed byte-level SHA256, original URL, HTTP status, 1/2 page, official record key and detail-sample gate. It rejects duplicate keys across pages, catalog rows masquerading as delivery orders, and HTTP 200 empty bidder lists labeled as verified zero bidders.
- `tests/test_procureflow_2y_public_raw_manifest.py` contains five synthetic fixture regressions; wired to hosted workflow `.github/workflows/procureflow-contract-web-probe.yml`.
- The validator explicitly leaves `full_2y_complete=false` and `join_verified=false` even when sample evidence passes. Its input is a manifest of actual captured raw bytes; no actual new contract/delivery bytes were claimed or ingested by this change.

## Next evidence gate
Populate the manifest only with preserved actual list, detail, page 1/2 raw responses and independent official-key/date fields, then verify in hosted CI. Independently verify ZIP bytes, contract round links, supplier keys, missing coverage and date-separated joins before bulk ingestion. Do not run original notice queue collection, modify original 187 Release pairs, or restart PC runner.

**Status: partial, not complete.** No user intervention required.
