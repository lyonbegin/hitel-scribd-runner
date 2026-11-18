#!/usr/bin/env python3
"""Fail-closed audit for separately collected 2-year G2B public source bytes.

Manifest is an array of records with: family, kind, url, method, http_status,
raw_path, sha256, page, record_keys, and optionally record_dates.
Never treats product catalog rows as delivery orders or empty bidder arrays as zero bids.
This tool does not fetch network resources or alter existing evidence.
"""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

FAMILIES = {"contract", "sole_source", "consortium", "supplier",
            "mas_product", "delivery_order", "award", "opening", "bidder"}
KINDS = {"list", "detail"}
DATE_FIELDS = {"contract": "contract_date", "delivery_order": "delivery_order_date"}
REQUIRED = {"family", "kind", "url", "method", "http_status", "raw_path",
            "sha256", "page", "record_keys"}


def audit(manifest, root):
    issues = []
    groups = defaultdict(lambda: {"pages": set(), "keys": set(), "detail": 0})
    for index, entry in enumerate(manifest):
        tag = f"entry[{index}]"
        if not isinstance(entry, dict) or not REQUIRED.issubset(entry):
            issues.append(f"{tag}:MISSING_FIELDS")
            continue
        family, kind = entry["family"], entry["kind"]
        if family not in FAMILIES or kind not in KINDS:
            issues.append(f"{tag}:INVALID_FAMILY_OR_KIND")
            continue
        if entry["method"] not in ("GET", "POST") or entry["http_status"] != 200:
            issues.append(f"{tag}:HTTP_NOT_VERIFIED")
        if not isinstance(entry["url"], str) or not entry["url"].startswith("https://"):
            issues.append(f"{tag}:INVALID_ORIGINAL_URL")
        path = Path(str(entry["raw_path"]))
        if path.is_absolute() or ".." in path.parts:
            issues.append(f"{tag}:UNSAFE_RAW_PATH")
            continue
        try:
            raw = (root / path).read_bytes()
        except OSError:
            issues.append(f"{tag}:RAW_BYTES_MISSING")
            continue
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            issues.append(f"{tag}:SHA256_MISMATCH")
        try:
            page = int(entry["page"])
            if page < 1:
                raise ValueError
        except (ValueError, TypeError):
            issues.append(f"{tag}:INVALID_PAGE")
            continue
        keys = entry["record_keys"]
        if not isinstance(keys, list) or not keys or any(not isinstance(k, str) or not k for k in keys):
            issues.append(f"{tag}:MISSING_OFFICIAL_KEYS")
            continue
        # Keys in a manifest are not proof unless present in the original JSON.
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            issues.append(f"{tag}:RAW_NOT_JSON")
            continue
        def source_strings(node):
            if isinstance(node, dict):
                for value in node.values():
                    yield from source_strings(value)
            elif isinstance(node, list):
                for value in node:
                    yield from source_strings(value)
            elif isinstance(node, (str, int)):
                yield str(node)
        raw_values = set(source_strings(payload))
        if any(key not in raw_values for key in keys):
            issues.append(f"{tag}:OFFICIAL_KEYS_NOT_IN_RAW")
        if len(set(keys)) != len(keys):
            issues.append(f"{tag}:DUPLICATE_WITHIN_PAGE")
        group = groups[family]
        if kind == "list":
            if page in group["pages"]:
                issues.append(f"{tag}:DUPLICATE_PAGE")
            group["pages"].add(page)
            if group["keys"].intersection(keys):
                issues.append(f"{tag}:CROSS_PAGE_DUPLICATE")
            group["keys"].update(keys)
        else:
            group["detail"] += 1
        date_field = DATE_FIELDS.get(family)
        if date_field and not entry.get(date_field):
            issues.append(f"{tag}:MISSING_{date_field.upper()}")
        if family == "delivery_order" and entry.get("source_type") == "product_catalog":
            issues.append(f"{tag}:CATALOG_NOT_DELIVERY")
        if family == "bidder" and entry.get("classification") == "no_bidders" and entry.get("successBidInfo") == []:
            issues.append(f"{tag}:EMPTY_BIDDER_UNVERIFIED")
    for family, group in groups.items():
        if not {1, 2}.issubset(group["pages"]):
            issues.append(f"{family}:TWO_PAGES_NOT_VERIFIED")
        if not group["detail"]:
            issues.append(f"{family}:DETAIL_NOT_VERIFIED")
    # No claim of full 2-year coverage or JOIN validation from sample evidence.
    return {"pass_sample_evidence": not issues and bool(groups),
            "full_2y_complete": False, "join_verified": False,
            "families_examined": sorted(groups), "issues": sorted(set(issues))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--raw-root", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = audit(json.loads(Path(args.manifest).read_text(encoding="utf-8")),
                   Path(args.raw_root))
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["pass_sample_evidence"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
