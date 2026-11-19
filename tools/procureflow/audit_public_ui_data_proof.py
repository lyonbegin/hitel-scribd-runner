#!/usr/bin/env python3
"""Audit public UI response bytes separately from contract-data completeness."""
import argparse
import hashlib
import json
from pathlib import Path

def classify(report, report_dir=None):
    proofs = report.get("read_only_response_proofs") or []
    counted = report.get("post_response_count_total", 0)
    tracked = report.get("tracked_post_responses") or []
    issues = []
    verified = 0
    if counted < len(tracked):
        issues.append("POST_RESPONSE_COUNT_INCONSISTENT")
    if counted > len(tracked):
        issues.append("POST_RESPONSE_SAMPLE_TRUNCATED")
    for event in tracked:
        status = event.get("status")
        if not isinstance(status, int) or isinstance(status, bool):
            issues.append("POST_HTTP_STATUS_MISSING")
        elif 300 <= status < 400:
            issues.append("POST_REDIRECT_NOT_DATA")
        elif status >= 400:
            issues.append("POST_HTTP_ERROR_NOT_DATA")
    for p in proofs:
        proof_status = p.get("status")
        if not isinstance(proof_status, int) or isinstance(proof_status, bool):
            issues.append("PROOF_HTTP_STATUS_MISSING")
        elif proof_status != 200:
            issues.append("PROOF_HTTP_NON_200_NOT_DATA")
        if proof_status == 200 and p.get("body_bytes", 0) == 0:
            issues.append("HTTP_200_EMPTY_BODY")
        digest = p.get("body_sha256")
        if digest and (not isinstance(digest, str) or len(digest) != 64 or
                       any(c not in "0123456789abcdef" for c in digest)):
            issues.append("INVALID_SHA256_FORMAT")
        if not p.get("raw_saved"):
            continue
        rel = p.get("raw_path")
        if (not isinstance(rel, str) or not rel or Path(rel).name != rel or
                rel in (".", "..")):
            issues.append("UNSAFE_RAW_PATH")
            continue
        if report_dir is None:
            issues.append("RAW_BYTES_NOT_AVAILABLE")
            continue
        path = Path(report_dir) / rel
        try:
            root_resolved = Path(report_dir).resolve(strict=True)
            path_resolved = path.resolve(strict=True)
            if path_resolved.parent != root_resolved:
                issues.append("RAW_PATH_ESCAPES_ROOT")
                continue
            raw = path_resolved.read_bytes()
        except OSError:
            issues.append("RAW_BYTES_MISSING")
            continue
        sha = hashlib.sha256(raw).hexdigest()
        if (sha != digest or sha != p.get("raw_sha256") or
            len(raw) != p.get("body_bytes") or len(raw) != p.get("raw_bytes")):
            issues.append("RAW_BYTES_HASH_OR_LENGTH_MISMATCH")
            continue
        if proof_status != 200 or p.get("raw_verified") is not True:
            if p.get("raw_verified") is False:
                issues.append("PRODUCER_RAW_VERIFICATION_FAILED")
            elif p.get("raw_verified") is not True:
                issues.append("PRODUCER_RAW_VERIFICATION_NOT_CONFIRMED")
            continue
        verified += 1
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
        "verified_raw_response_bytes": verified,
        "verified_join_rows": 0,
        "status": "NOT_VERIFIED",
        "reason": "Rehashed raw response bytes alone do not prove record semantics, pagination or official-key joins."
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
            reports.append(classify(json.loads(path.read_text(encoding="utf-8")), path.parent))
        except (ValueError, OSError) as exc:
            reports.append({"file": str(path), "status": "READ_ERROR", "error": type(exc).__name__})
    verified = sum(x.get("verified_raw_response_bytes", 0) for x in reports)
    result = {"classification": "PUBLIC_WEB_EVIDENCE_ONLY", "reports": reports,
              "complete": False, "raw_bytes_rehashed": verified > 0,
              "raw_response_files_verified": verified}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
