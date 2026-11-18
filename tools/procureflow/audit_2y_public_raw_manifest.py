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
    groups = defaultdict(lambda: {"pages": set(), "keys": set(), "detail": 0, "detail_keys": set(), "list_raw_hashes": set(), "list_raw_paths": set()})
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
            declared_page = entry["page"]
            # bool and fractional floats must never become page 1 via int().
            # A page label is evidence only when it is a positive integer.
            if type(declared_page) is int:
                page = declared_page
            elif isinstance(declared_page, str) and declared_page.isascii() and declared_page.isdecimal():
                page = int(declared_page)
            else:
                raise ValueError("non-integral page")
            if page < 1:
                raise ValueError("page must be positive")
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
        # Only explicit, entity-scoped row identifiers count as evidence.
        # A matching value in metadata or an unrelated entity is never proof.
        row_path = entry.get("record_path")
        key_field = entry.get("official_key_field")
        if not isinstance(row_path, list) or not row_path or not isinstance(key_field, str) or not key_field:
            issues.append(f"{tag}:OFFICIAL_KEY_MAPPING_REQUIRED")
            continue
        try:
            rows = payload
            for segment in row_path:
                if isinstance(rows, dict) and isinstance(segment, str):
                    rows = rows[segment]
                elif isinstance(rows, list) and type(segment) is int:
                    rows = rows[segment]
                else:
                    raise KeyError(segment)
            if isinstance(rows, dict):
                rows = [rows]
            if not isinstance(rows, list) or not rows or any(not isinstance(r, dict) for r in rows):
                raise ValueError("not entity rows")
            observed = [str(r[key_field]) for r in rows if key_field in r and r[key_field] is not None]
            if len(observed) != len(rows) or not observed:
                raise ValueError("missing row identifier")
        except (KeyError, IndexError, TypeError, ValueError):
            issues.append(f"{tag}:OFFICIAL_KEY_ROW_MAPPING_INVALID")
            continue
        if sorted(observed) != sorted(keys):
            issues.append(f"{tag}:OFFICIAL_KEYS_NOT_IN_RAW")
        if len(set(keys)) != len(keys):
            issues.append(f"{tag}:DUPLICATE_WITHIN_PAGE")
        group = groups[family]
        if kind == "list":
            if page in group["pages"]:
                issues.append(f"{tag}:DUPLICATE_PAGE")
            # A second page number alone is not pagination evidence when the
            # same source bytes or source file were relabelled as page two.
            if entry["sha256"] in group["list_raw_hashes"]:
                issues.append(f"{tag}:REUSED_LIST_RESPONSE_BYTES")
            if str(path) in group["list_raw_paths"]:
                issues.append(f"{tag}:REUSED_LIST_RAW_PATH")
            group["list_raw_hashes"].add(entry["sha256"])
            group["list_raw_paths"].add(str(path))
            group["pages"].add(page)
            if group["keys"].intersection(keys):
                issues.append(f"{tag}:CROSS_PAGE_DUPLICATE")
            group["keys"].update(keys)
        else:
            if group["detail_keys"].intersection(keys):
                issues.append(f"{tag}:DUPLICATE_DETAIL_OFFICIAL_KEY")
            group["detail"] += 1
            group["detail_keys"].update(keys)
        date_field = DATE_FIELDS.get(family)
        if date_field:
            declared_date = entry.get(date_field)
            if not declared_date:
                issues.append(f"{tag}:MISSING_{date_field.upper()}")
            elif any(str(row.get(date_field, "")) != str(declared_date) for row in rows):
                issues.append(f"{tag}:DATE_NOT_IN_ENTITY_ROWS")
        if family == "delivery_order" and entry.get("source_type") == "product_catalog":
            issues.append(f"{tag}:CATALOG_NOT_DELIVERY")
        if family == "bidder" and entry.get("classification") == "no_bidders" and entry.get("successBidInfo") == []:
            issues.append(f"{tag}:EMPTY_BIDDER_UNVERIFIED")
    for family, group in groups.items():
        if not {1, 2}.issubset(group["pages"]):
            issues.append(f"{family}:TWO_PAGES_NOT_VERIFIED")
        if not group["detail"]:
            issues.append(f"{family}:DETAIL_NOT_VERIFIED")
        elif not group["detail_keys"].issubset(group["keys"]):
            issues.append(f"{family}:DETAIL_NOT_LINKED_TO_LIST")
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
