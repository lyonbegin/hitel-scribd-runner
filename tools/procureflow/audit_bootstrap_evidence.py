#!/usr/bin/env python3
"""Classify read-only WebSquare bootstrap evidence without inferring public data success."""
import argparse
import hashlib
import json
from pathlib import Path

def classify(reports):
    result = []
    for site, entries in reports.items():
        for row in entries:
            dom = row.get("dom") or {}
            responses = row.get("responses") or []
            failures = row.get("request_failures") or []
            non_static = row.get("non_static") or []
            aborted_posts = [f for f in failures if f.get("method") == "POST"]
            confirmed_guard = [f for f in aborted_posts if f.get("client_guard_blocked") is True]
            ambiguous_failures = [f for f in aborted_posts if f.get("client_guard_blocked") is not True]
            guard_decisions = row.get("client_guard_decisions") or []
            explicit_guard_posts = [g for g in guard_decisions if g.get("method") == "POST" and g.get("reason") == "non_readonly_method_blocked_before_network"]
            observed_posts = [r for r in responses if r.get("method") == "POST"]
            successful_posts = [r for r in observed_posts if r.get("status") == 200]
            # A POST aborted by the read-only guard is not an HTTP error from the server.
            # A 200 POST is not a validated report/contract data response.
            result.append({
                "site": site, "url": row.get("requested_url"),
                "http_status": row.get("http_status"),
                "dom_empty": dom.get("bodyChildren") == 0,
                "websquare_loaded": dom.get("websquare") == "object",
                "oidc_302_count": len(row.get("get_302") or []),
                "failed_post_count": len(aborted_posts),
                "confirmed_client_guard_post_count": max(len(confirmed_guard), len(explicit_guard_posts)),
                "explicit_guard_post_count": len(explicit_guard_posts),
                "ambiguous_post_failure_count": len(ambiguous_failures),
                "observed_post_count": len(observed_posts),
                "http_200_post_count": len(successful_posts),
                "non_static_response_count": len(non_static),
                "verified_data_rows": 0,
                "classification": "NOT_VERIFIED",
                "reason": ("post_failure_origin_unverified" if ambiguous_failures
                           else "client_blocked_post_not_server_failure" if (confirmed_guard or explicit_guard_posts)
                           else "no_validated_list_detail_pagination")
            })
    return result

EXPECTED_TARGETS = {
    "g2b": {"https://www.g2b.go.kr/"},
    "data": {
        "https://data.g2b.go.kr/",
        "https://data.g2b.go.kr/link/AISC001_01/?reptNm=UI-ADOXFA-112R",
        "https://data.g2b.go.kr/link/AISC001_01/?reptNm=UI-ADOXFA-113R",
    },
    "shop": {"https://shop.g2b.go.kr/"},
}

def missing_targets(reports):
    """Fail closed if a probe did not run or its report was silently lost."""
    return sorted(
        url for site, urls in EXPECTED_TARGETS.items()
        for url in urls
        if url not in {row.get("requested_url") for row in reports.get(site, [])}
    )

def verify_dom_bytes(root, reports):
    """Independently verify saved DOM bytes; never treat a missing file as evidence."""
    issues = []
    for site, rows in reports.items():
        for row in rows:
            dom = row.get("dom") or {}
            name, expected = dom.get("html_file"), dom.get("html_sha256")
            url = row.get("requested_url") or "<unknown>"
            if not name or not expected:
                issues.append({"site": site, "url": url, "reason": "missing_dom_file_or_sha256"})
                continue
            # Only a basename in the expected site's output directory is allowed.
            if Path(name).name != name or not name.endswith("_dom.html"):
                issues.append({"site": site, "url": url, "reason": "unsafe_dom_filename"})
                continue
            path = root / ("boot-" + site) / name
            if not path.is_file():
                issues.append({"site": site, "url": url, "reason": "missing_dom_bytes"})
                continue
            if not path.resolve().is_relative_to((root / ("boot-" + site)).resolve()) or path.is_symlink():
                issues.append({"site": site, "url": url, "reason": "unsafe_dom_symlink"})
                continue
            if not isinstance(expected, str) or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
                issues.append({"site": site, "url": url, "reason": "invalid_dom_sha256"})
                continue
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                issues.append({"site": site, "url": url, "reason": "dom_sha256_mismatch"})
    return issues

def duplicate_targets(reports):
    """Repeated target entries must not silently masquerade as distinct observations."""
    duplicates = []
    for site, rows in reports.items():
        seen = set()
        for row in rows:
            url = row.get("requested_url")
            if url in seen:
                duplicates.append({"site": site, "url": url})
            seen.add(url)
    return duplicates

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    data = {}
    for site in ("g2b", "data", "shop"):
        path = args.root / ("boot-" + site) / "bootstrap_report.json"
        data[site] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    integrity_issues = verify_dom_bytes(args.root, data)
    duplicates = duplicate_targets(data)
    result = {"version": 4, "duplicate_targets": duplicates, "dom_bytes_verified": not integrity_issues,
              "dom_integrity_issues": integrity_issues, "policy": "no_200_or_empty_list_implies_no_bidder_or_verified_data",
              "complete_probe_coverage": not missing_targets(data),
              "missing_targets": missing_targets(data),
              "coverage": classify(data)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("BOOTSTRAP_CLASSIFICATION", json.dumps(result, ensure_ascii=False))
    if duplicates:
        raise SystemExit("DUPLICATE_PROBE_TARGETS: " + json.dumps(duplicates, ensure_ascii=False))
    if integrity_issues:
        raise SystemExit("DOM_BYTE_INTEGRITY_FAILED: " + json.dumps(integrity_issues, ensure_ascii=False))
    if result["missing_targets"]:
        raise SystemExit("INCOMPLETE_PROBE_COVERAGE: " + ", ".join(result["missing_targets"]))

if __name__ == "__main__":
    main()
