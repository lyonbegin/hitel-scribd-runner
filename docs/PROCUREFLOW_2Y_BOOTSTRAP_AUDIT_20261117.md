# ProcureFlow 2Y — WebSquare bootstrap evidence review (2026-11-17 KST)

## Scope and immutable boundaries
Only the recent two-year contract/supplier/MAS/delivery research branch is in scope. Do not alter the 930,379 notice-key source, the 721 verified days or ten unverified days, the 187 original Release pairs, production collection workflows, or self-hosted runners. No authentication bypass, API keys, purchasing, or submitting.

## Reproduced hosted evidence
GitHub Actions [43880097308](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43880097308) completed four jobs successfully: isolated Postgres fixture validation, public UI inspection, JS inspection, and Chrome/Xvfb bootstrap inspection. **Job success is not data extraction success.**

The bootstrap diagnostic logged:
- G2B home: final document HTTP 200, 526,128 HTML characters, zero body children, zero body text, WebSquare object, 29 scripts, 100 observed responses, initial G2B -> SSO 302 -> G2B 302 redirect chain. Saved DOM HTML SHA256 `91a57b536da969e3715217e7e10de498a13eaeba1567c13d50426cf6706b35c2`.
- Data hub home: HTTP 200, zero body children, zero body text, 32 scripts, DOM SHA256 `b8634754fb38730ac785044da580fa388d93f6c15ced2be42bfb48b72f049bfe`.
- 112R direct report: HTTP 200, zero body children, zero body text, DOM SHA256 `8a17a4c1d57ed303dcf583ab514487a3d709efd0a338f81dce426de3d63db5ab`.
- 113R direct report: HTTP 200, zero body children, zero body text, DOM SHA256 `e6947e7bc758e0fecd40b41a74d66cc432230557513ebf02a980467bcde023f8`.
- Shopping mall home: HTTP 200, zero body children, zero body text, 27 scripts, DOM SHA256 `5d6797d6e3df01b7dd6f2fef5d0df2169da1167abbf98a97ef46f72e650f142f`.
- The observed non-static requests were initial documents and WebSquare `suffix.txt`/`serverTime.wq`; no contract list/detail, report data, shopping product search or delivery-order data request was reproduced. An HTTP 200 for an HTML bootstrap page does not prove the underlying report is accessible.
- Bootstrap artifact ID 14231991961, ZIP SHA256 `35c1e357d24875bc98c6b9382631ac7e6fd1e352691499bb1acb0ecff82e1e4b`. Public UI artifact ID 14232485588, ZIP SHA256 `9abc9d2694b260e5670ca45e9b99e16dc5316ca771ade2f19ee6e3080e5ba5d3`. These are artifact ZIP hashes, not source contract-record hashes.

## Interpretation
An SSO 302 alone does not establish that all public reports require login. WebSquare exists, yet its body remains empty; the root cause is **unconfirmed**. Distinguish bootstrap initialization, script/runtime loading, routing, and server-side access controls by inspecting actual observed requests, failures and DOM; never synthesize or replay a privileged POST.

## Narrow follow-up
`probe_websquare_bootstrap.py` now retains a bounded inventory of script sources, WebSquare version when exposed, and failed requests in the next read-only hosted diagnostic. Compare those with the previous successful run; do not infer contract records from JS function names. If and only if a genuinely public read-only contract list endpoint is observed, collect a single list/detail/page-2 sample with response bytes, URL, SHA256 and linkage keys before scaling.

## Separate data integrity status
Earlier original Release audit found 187 status JSONs verified by byte SHA256, 187 ZIP metadata pairs matched, and ZIP 0/93/186 checked by full byte SHA256 and CRC. This is **not** an audit of all ZIP payloads. Recovery runs 43868699164, 43869729252, 43870757534 and 43871778282 each processed 5,000 previously zero-processed notice keys (169–172); new rows contain 368 unknown outcomes in those four shards. The final supervisor run 43872817232 reported no remaining zero-processed shards and `all_stage2_verified=false`. Combined old+new unknown count is 9,877 based on status logs; it is not a fully independent ZIP-content count. `successBidInfo=[]` is not proof of a true no-bid event. No other shards were restarted.

The isolated PostgreSQL schema fixture test passed, but **real contract, sole-source, joint-supply, MAS, delivery-order ingestion and actual joins remain unverified and incomplete**. Do not declare overall completion.
