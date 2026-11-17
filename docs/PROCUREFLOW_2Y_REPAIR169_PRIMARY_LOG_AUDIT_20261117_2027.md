# Stage2 selective repair and public UI evidence — 2026-11-17 20:27 KST

## Verified primary logs
- Selective recovery run: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43868699164 ; job 133303823234, GitHub-hosted Ubuntu 26.04.1, completed successfully.
- Segment **169**: `DETAIL_FINAL` processed=5000/5000, verified_complete=3385, no_opening_data=1512, no_bidder_rows_unverified=103, error=0, verified_bidder_rows=331902. These are **collector log counts**, not independent ZIP-row recount.
- New recovery ZIP `g2b-repair-shard-169-43868699164-1794833218.zip`: 41,473,929 bytes, logged SHA256 `a6c35cd037bb84d6b32261a73b1694bda8d402bc0eb3047ff4b4767315f4553d`; state JSON 483 bytes, logged SHA256 `4cb4201936d78322681e1ddd50dd1747c1a97fc2d0946a0e6a7d0bc742ed5165`. The log reports `SHARD_CHECKPOINT_VERIFIED`, but this audit did **not** independently download and rehash those bytes.
- Supervisor explicitly reported `need_continue=true`, `new_shards_remaining=3`, `segments_checked_this_run=[169]`, `all_stage2_verified=false`. Therefore the initial four zero-processed shards were **not all completed in this run**; check subsequent dispatch runs and independently audit 170–172 before any completion claim.
- The 103 empty-success bidder lists remain **unverified**, not proven no-bidder rows. `no_opening_data` also must not be conflated with confirmed zero bidders.
- Public UI run https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44032453529 ; job 133867955138: shop homepage HTTP 200, `bodyCount=0`, `webSquareDefined=true`, observed POST responses 0, OIDC GET 302. Report URLs 112R and 113R return initial HTTP 200 but no verified report data.
- Schema-only disposable PostgreSQL tests are not actual production data ingestion or official-key JOIN audit.

## Restrictions and next verification
Do not modify original 930379-key index, 187 original ZIP/status pairs, operational workflows or self-hosted PC Runner. Do not replay other 176 shards. Next audit must identify continuation run IDs and verify 169–172 replacement ZIP byte SHA256/CRC and status counts; retain `no_bidder_rows_unverified` as unresolved until original official status fields support a disposition. For contract/MAS/delivery collection, require real public list, detail, pagination, source URL, raw bytes and SHA256 before ingestion. No authentication bypass or transaction actions.
