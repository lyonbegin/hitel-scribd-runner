# Hosted WebSquare bootstrap timing audit — 2026-11-17 21:18 KST

## Evidence
- Workflow run: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44059369280 (commit d1544ccda10551bb3ff9356c15aa74fc979e3046).
- Job 133956916559 bootstrap log: **www.g2b.go.kr DOM changed from empty at 2, 5 and 9 seconds to visible at 12 seconds**. At 12s, `bodyChildren=6`, `controls=147`, `frameCount=1`, visible labels include 나라장터, 쇼핑몰, 조달데이터허브, 로그인. Final HTML `htmlLength=578440`, `html_sha256=caea438f03913c6b2cf7bb912ead244c3b29c12d0ac15ccd7c3edbec83081e4a` (hash reported by runner; independent download/re-hash not performed). OIDC GET 302 remains present.
- Job 133956916836 public UI probe finished earlier at 09:51:43Z with `bodyCount=0`, `post_response_count_observed=0` and no visible controls. This is **not evidence that the portal never renders**: the separate bootstrap job captured a populated DOM at 12s.
- PostgreSQL fixture/schema/JOIN audit job 133956916829 succeeded. This proves disposable fixture checks, **not production source rows or JOIN completeness**.
- Three artifacts were retained: 14318070242, 14317038941, 14316869532; GitHub-supplied archive digests are metadata, not independent byte verification.

## Corrective research sequence (not yet executed)
1. Adjust only research-branch public UI probe to wait for a specific visible public navigation control (with a bounded timeout >= 12 seconds), rather than assuming document.readyState=complete means WebSquare navigation is available. Record time-to-first-visible-control, DOM hash and all OIDC redirects. Never bypass authentication.
2. Navigate only public contract search controls once visible; capture genuine read-only request/response (method, URL, status, body SHA256, pagination and detail) before claiming extraction.
3. Repeat separately for data portal 112R/113R and shopping public product search. Distinguish public information from restricted order operations.
4. Preserve existing notice queue, 187 original release pairs and Stage2 workflows; do not restart self-hosted PC runner or blanket-retry shards.
5. Repair run 43868699164 succeeded for its first zero-processed shard, but its log reports `remaining=3`, `all_stage2_verified=false`. This does not close 170–172 or `no_bidder_rows_unverified`.

## Completion gate
**Not complete.** No verified contract/MAS/order list+detail+page source, independent ZIP bytes, or real-source entity JOIN audit. The reported HTTP 200/empty successBidInfo cannot be converted to zero bids without official status evidence.
