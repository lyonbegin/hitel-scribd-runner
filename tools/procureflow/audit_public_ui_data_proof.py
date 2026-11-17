#!/usr/bin/env python3
"""Conservative audit of public UI probe reports; never infer records from HTTP 200."""
import argparse
import hashlib
import json
from pathlib import Path

def classify(report):
    proofs = report.get("read_only_response_proofs") or []
    counted = report.get("post_response_count_total", 0)
    issues = []
    tracked = report.get("tracked_post_responses") or []
    if counted < len(tracked):
        issues.append("POST_RESPONSE_COUNT_INCONSISTENT")
    if counted > len(tracked):
        issues.append("POST_RESPONSE_SAMPLE_TRUNCATED")
    for event in tracked:
        status = event.get("status")
        if status is None:
            issues.append("POST_HTTP_STATUS_MISSING")
        elif 300 <= status < 400:
            issues.append("POST_REDIRECT_NOT_DATA")
        elif status >= 400:
            issues.append("POST_HTTP_ERROR_NOT_DATA")
    for p in proofs:
        if p.get("status") == 200 and p.get("body_bytes", 0) == 0:
            issues.append("HTTP_200_EMPTY_BODY")
        if p.get("body_sha256") and (len(p["body_sha256"]) != 64 or
                                     any(c not in "0123456789abcdef" for c in p["body_sha256"])):
            issues.append("INVALID_SHA256_FORMAT")
    return {
        "site": report.get("site"),
        "http_200_is_not_data_proof": True,
        "observed_post_responses": counted,
        "sampled_post_responses": len(tracked),
        "read_only_response_digests": len(proofs),
        "issues": sorted(set(issues)),
        "verified_list_records": 0,
        "verified_detail_records": 0,
        "verified_page_transitions": 0,
        "verified_raw_response_bytes": 0,
        "verified_join_rows": 0,
        "status": "NOT_VERIFIED",
        "reason": "Digest-only network metadata cannot prove original response bytes, record semantics, pagination or official-key joins."
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    root = Path(args.root)
    reports = []
    for path in sorted(root.glob("procureflow-*-probe/report.json")):
        try:
            reports.append(classify(json.loads(path.read_text(encoding="utf-8"))))
        except (ValueError, OSError) as exc:
            reports.append({"file": path.name, "status": "READ_ERROR", "error": type(exc).__name__})
    result = {"classification": "PUBLIC_WEB_EVIDENCE_ONLY", "reports": reports,
              "complete": False, "raw_bytes_rehashed": False}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
if __name__ == "__main__":
    main()
