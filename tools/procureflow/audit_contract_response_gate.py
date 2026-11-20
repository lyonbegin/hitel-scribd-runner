"""Fail-closed classification of public procurement response evidence.

Never infer a procurement record from HTTP 200, a valid SHA256, or an empty list.
This tool does not perform network requests, login, or data writes.
"""
import argparse
import hashlib
import json
from pathlib import Path


def classify(raw: bytes, *, http_status: int, url: str, kind: str, page: int | None = None):
    digest = hashlib.sha256(raw).hexdigest()
    result = {"url": url, "http_status": http_status, "kind": kind,
              "page": page, "byte_length": len(raw), "sha256": digest,
              "verified_records": 0, "status": "NOT_VERIFIED", "reason": ""}
    if http_status != 200:
        result["reason"] = "non_200_response"
        return result
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        result["reason"] = "not_valid_json_record_proof"
        return result
    if not isinstance(body, dict):
        result["reason"] = "not_object_response"
        return result
    if kind == "bidder" and isinstance(body.get("result"), dict):
        rows = body["result"].get("successBidInfo")
        if rows == []:
            result["reason"] = "no_bidder_rows_unverified"
            return result
    # A raw response is not a verified list/detail without documented,
    # independently inspected field mapping and an official identity key.
    result["reason"] = "record_schema_and_official_key_not_validated"
    return result


def audit_manifest(manifest: dict, root: Path):
    results = []
    for item in manifest.get("responses", []):
        path = (root / item["file"]).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError("Missing or outside-root response: " + item["file"])
        raw = path.read_bytes()
        row = classify(raw, http_status=item["http_status"], url=item["url"],
                       kind=item["kind"], page=item.get("page"))
        expected = item.get("sha256")
        if not expected or row["sha256"] != expected:
            raise ValueError("Raw SHA256 mismatch: " + item["file"])
        results.append(row)
    return {"classification": "PUBLIC_RAW_BYTES_ONLY", "complete": False,
            "responses_verified": len(results), "records_verified": 0,
            "results": results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    output = audit_manifest(json.loads(Path(args.manifest).read_text(encoding="utf-8")),
                            Path(args.root))
    Path(args.out).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    print(json.dumps({"complete": output["complete"],
                      "responses_verified": output["responses_verified"]}))


if __name__ == "__main__":
    main()
