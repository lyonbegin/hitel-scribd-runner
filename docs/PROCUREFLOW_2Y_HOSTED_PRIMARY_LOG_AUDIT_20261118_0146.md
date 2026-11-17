# 2026-11-18 01:46 KST — latest hosted public-web primary log audit

## Evidence
- Chain runs: [g2b 44106619001](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44106619001), [data 44106868445](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44106868445), [shop 44107272675](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44107272675); all completed success. Full public UI run [44106618973](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44106618973).
- GitHub-hosted Chrome+Xvfb only. Successful Actions jobs are not evidence of contract extraction.
- g2b visible navigation after 14,278 ms, 20 controls. Homepage POST `/fa/faz/fazf/PrtlFtre/selectPrtlFtreMainList.do` HTTP 200, 120914 bytes, SHA256 `93b342272a384773dabe33517bea39519d5063b73cd69580ca8e7c276795ab0c`. This is portal footer data, **not contract rows**. `getSession.do` failed `net::ERR_FAILED`; on-page server-error code 0. No contract search/list/detail/page-2 proof.
- data visible after 14,768 ms, 15 controls. Direct 113R remained empty; 112R displayed portal shell and server-error code 0, not report rows. Homepage/common-code POSTs were observed, but no 112R/113R result list/detail/pagination proof. `getSession.do` failed.
- shop visible after 12,174 ms, 23 controls. Homepage POSTs HTTP 200: `selectTemaLst.do` 1901 bytes SHA256 `cbac9d24e1fed9d4f5986b93c9060ee280edbeaeab4366ff4956958c3dda783d`; `selectCertLst.do` 2375 bytes SHA256 `9c00954ae5cb6ffd0e4665de938503d086f10e63cdea7b3ac38558a7a370fb54`; `selectCgryLst.do` 28965 bytes SHA256 `3d9a1799f344da96ac3a0bf68dd759ad521d179bdb5f43205d2e3badd05eb267`. These are landing-page theme/certification/category calls, **not product-search, MAS contracts or delivery orders**.
- Above SHA256 values are computed by the probe from response bytes as logged, not an independently downloaded response body; log records only response byte length/hash. Artifact ZIP independent rehash not performed this run.
- The older [43868699164](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43868699164) had one successful recovery job and a successful next-shard dispatch, but this alone does not prove 170–172 completion.

## Disposition
- Change interpretation from “all WebSquare DOM always empty” to “homepage shell and initial POSTs can load after ~12–15s; target business screens remain unverified.”
- No authentication bypass, API keys, bids, contract actions, purchases or submissions.
- Do not classify `no_bidder_rows_unverified` as zero bidders; do not rerun 930379 notice index or mass-recollect other shards.
- Next read-only investigation must trigger the actual public contract/menu/product-search UI and capture request/response **bytes** (not only hash), list/detail/page 2, provenance URL, and JOIN keys. Only then allow isolated-table loading and byte SHA256/ZIP/duplicate/missing/JOIN audits.
- No completed extraction, real-table JOIN or whole-data audit is claimed.
