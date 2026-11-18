#!/usr/bin/env python3
"""Conservative classification of a preserved Stage2 HTTP response.

No network access. Never convert an empty successBidInfo into confirmed zero bidders.
"""
import argparse
import hashlib
import json
from pathlib import Path


def classify(status: int, raw: bytes) -> dict:
    result = {
        "http_status": status,
        "response_bytes": len(raw),
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "verified_zero_bidders": False,
        "status": "unverified",
    }
    if status != 200:
        result["reason"] = "HTTP_NON_200"
        return result
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        result["reason"] = "NON_JSON_RESPONSE"
        return result
    if not isinstance(doc, dict) or not isinstance(doc.get("result"), dict):
        result["reason"] = "MISSING_RESULT_OBJECT"
        return result
    body = doc["result"]
    # HTTP 200 is a transport result, not proof that the application accepted the request.
    # Preserve explicit application failure markers before interpreting bidder rows.
    for scope, obj in (("root", doc), ("result", body)):
        if obj.get("success") is False:
            result["reason"] = "APPLICATION_EXPLICIT_FAILURE"
            result["failure_scope"] = scope
            return result
    bidders = body.get("successBidInfo")
    if bidders == []:
        result["status"] = "no_bidder_rows_unverified"
        result["reason"] = "EMPTY_SUCCESS_BID_INFO_REQUIRES_OFFICIAL_OPENING_STATE"
        result["bidInfo_present"] = "bidInfo" in body
        result["etcData_present"] = "etcData" in body
    elif isinstance(bidders, list) and bidders:
        result["status"] = "bidder_rows_present_unverified"
        result["bidder_row_count"] = len(bidders)
        result["reason"] = "ROW_COUNT_ONLY_NOT_A_COMPLETE_OPENING_AUDIT"
    else:
        result["reason"] = "MISSING_OR_INVALID_SUCCESS_BID_INFO"
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument("--http-status", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    raw = args.response.read_bytes()
    result = classify(args.http_status, raw)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
