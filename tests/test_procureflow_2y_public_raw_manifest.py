import hashlib
import json
import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools/procureflow/audit_2y_public_raw_manifest.py"
spec = importlib.util.spec_from_file_location("audit_2y_public_raw_manifest", MODULE)
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)


class PublicRawManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def entry(self, page, kind="list", family="contract", key=None):
        path = f"{family}-{kind}-{page}.json"
        row = {"official_key": key or f"{family}-{kind}-{page}"}
        if family == "contract":
            row["contract_date"] = "2026-11-17"
        if family == "delivery_order":
            row["delivery_order_date"] = "2026-11-17"
        raw = json.dumps({"page": page, "kind": kind, "official_row": row}).encode()
        (self.root / path).write_bytes(raw)
        result = {"family": family, "kind": kind,
                  "url": "https://www.g2b.go.kr/public/search",
                  "method": "POST", "http_status": 200, "raw_path": path,
                  "sha256": hashlib.sha256(raw).hexdigest(),
                  "page": page, "record_keys": [key or f"{family}-{kind}-{page}"],
                  "record_path": ["official_row"], "official_key_field": "official_key"}
        if family == "contract":
            result["contract_date"] = "2026-11-17"
        if family == "delivery_order":
            result["delivery_order_date"] = "2026-11-17"
        return result

    def test_sample_pass_does_not_mean_full_coverage(self):
        result = audit_module.audit([self.entry(1), self.entry(2),
                                     self.entry(1, "detail", key="contract-list-1")], self.root)
        self.assertTrue(result["pass_sample_evidence"])
        self.assertFalse(result["full_2y_complete"])
        self.assertFalse(result["join_verified"])

    def test_detail_must_share_official_key_with_list(self):
        items = [self.entry(1), self.entry(2), self.entry(1, "detail")]
        result = audit_module.audit(items, self.root)
        self.assertIn("contract:DETAIL_NOT_LINKED_TO_LIST", result["issues"])
        self.assertFalse(result["pass_sample_evidence"])

    def test_every_detail_key_must_be_in_list_not_just_one(self):
        items = [self.entry(1), self.entry(2),
                 self.entry(1, "detail", key="contract-list-1")]
        detail = items[2]
        raw = json.dumps({"official_rows": [
            {"official_key": "contract-list-1", "contract_date": "2026-11-17"},
            {"official_key": "unrelated-contract", "contract_date": "2026-11-17"}
        ]}).encode()
        (self.root / detail["raw_path"]).write_bytes(raw)
        detail["sha256"] = hashlib.sha256(raw).hexdigest()
        detail["record_path"] = ["official_rows"]
        detail["record_keys"] = ["contract-list-1", "unrelated-contract"]
        result = audit_module.audit(items, self.root)
        self.assertIn("contract:DETAIL_NOT_LINKED_TO_LIST", result["issues"])
        self.assertFalse(result["pass_sample_evidence"])

    def test_duplicate_detail_official_key_across_files_rejected(self):
        items = [self.entry(1), self.entry(2),
                 self.entry(1, "detail", key="contract-list-1"),
                 self.entry(2, "detail", key="contract-list-1")]
        result = audit_module.audit(items, self.root)
        self.assertIn("entry[3]:DUPLICATE_DETAIL_OFFICIAL_KEY", result["issues"])
        self.assertFalse(result["pass_sample_evidence"])

    def test_symlink_escape_rejected_before_read(self):
        items = [self.entry(1), self.entry(2),
                 self.entry(1, "detail", key="contract-list-1")]
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / "external.json"
            external.write_bytes((self.root / items[0]["raw_path"]).read_bytes())
            (self.root / items[0]["raw_path"]).unlink()
            (self.root / items[0]["raw_path"]).symlink_to(external)
            result = audit_module.audit(items, self.root)
        self.assertIn("entry[0]:RAW_PATH_ESCAPES_ROOT", result["issues"])
        self.assertFalse(result["pass_sample_evidence"])

    def test_missing_raw_bytes_and_hash_are_fail_closed(self):
        items = [self.entry(1), self.entry(2), self.entry(1, "detail")]
        items[0]["sha256"] = "0" * 64
        (self.root / items[1]["raw_path"]).unlink()
        result = audit_module.audit(items, self.root)
        self.assertIn("entry[0]:SHA256_MISMATCH", result["issues"])
        self.assertIn("entry[1]:RAW_BYTES_MISSING", result["issues"])
        self.assertFalse(result["pass_sample_evidence"])

    def test_catalog_cannot_be_delivery_order(self):
        items = [self.entry(1, family="delivery_order"),
                 self.entry(2, family="delivery_order"),
                 self.entry(1, "detail", "delivery_order")]
        items[0]["source_type"] = "product_catalog"
        result = audit_module.audit(items, self.root)
        self.assertIn("entry[0]:CATALOG_NOT_DELIVERY", result["issues"])

    def test_cross_page_duplicate_rejected(self):
        items = [self.entry(1, key="same"), self.entry(2, key="same"),
                 self.entry(1, "detail")]
        self.assertIn("entry[1]:CROSS_PAGE_DUPLICATE",
                      audit_module.audit(items, self.root)["issues"])

    def test_relabelled_second_page_bytes_are_not_pagination(self):
        items = [self.entry(1), self.entry(2),
                 self.entry(1, "detail", key="contract-list-1")]
        # Even if a malicious manifest relabels row keys, identical response
        # bytes cannot establish two independently retrieved pages.
        raw = (self.root / items[0]["raw_path"]).read_bytes()
        (self.root / items[1]["raw_path"]).write_bytes(raw)
        items[1]["sha256"] = items[0]["sha256"]
        items[1]["record_keys"] = items[0]["record_keys"]
        result = audit_module.audit(items, self.root)
        self.assertIn("entry[1]:REUSED_LIST_RESPONSE_BYTES", result["issues"])
        self.assertFalse(result["pass_sample_evidence"])

    def test_same_raw_file_cannot_prove_two_pages(self):
        items = [self.entry(1), self.entry(2),
                 self.entry(1, "detail", key="contract-list-1")]
        items[1]["raw_path"] = items[0]["raw_path"]
        items[1]["sha256"] = items[0]["sha256"]
        result = audit_module.audit(items, self.root)
        self.assertIn("entry[1]:REUSED_LIST_RAW_PATH", result["issues"])
        self.assertFalse(result["pass_sample_evidence"])

    def test_non_integral_page_labels_are_rejected(self):
        for invalid_page in (True, 1.5, 2.9, "1.5", "1e0", -1, 0):
            with self.subTest(page=invalid_page):
                items = [self.entry(1), self.entry(2),
                         self.entry(1, "detail", key="contract-list-1")]
                items[0]["page"] = invalid_page
                result = audit_module.audit(items, self.root)
                self.assertIn("entry[0]:INVALID_PAGE", result["issues"])
                self.assertFalse(result["pass_sample_evidence"])

    def test_non_string_official_keys_in_source_rows_are_rejected(self):
        for source_key in (True, 1, 1.0, None, ["contract-list-1"]):
            with self.subTest(source_key=source_key):
                items = [self.entry(1), self.entry(2),
                         self.entry(1, "detail", key="contract-list-1")]
                raw = json.dumps({"official_row": {
                    "official_key": source_key, "contract_date": "2026-11-17"
                }}).encode()
                (self.root / items[0]["raw_path"]).write_bytes(raw)
                items[0]["sha256"] = hashlib.sha256(raw).hexdigest()
                items[0]["record_keys"] = [str(source_key)]
                result = audit_module.audit(items, self.root)
                self.assertIn("entry[0]:OFFICIAL_KEY_ROW_MAPPING_INVALID", result["issues"])
                self.assertFalse(result["pass_sample_evidence"])

    def test_manifest_key_not_in_raw_is_rejected(self):
        items = [self.entry(1), self.entry(2), self.entry(1, "detail")]
        items[0]["record_keys"] = ["invented-key"]
        result = audit_module.audit(items, self.root)
        self.assertIn("entry[0]:OFFICIAL_KEYS_NOT_IN_RAW", result["issues"])
        self.assertFalse(result["pass_sample_evidence"])

    def test_key_in_unrelated_metadata_is_not_official_row_identity(self):
        items = [self.entry(1), self.entry(2), self.entry(1, "detail")]
        raw = b'{"metadata":{"official_key":"fake"},"official_row":{"official_key":"real"}}'
        (self.root / items[0]["raw_path"]).write_bytes(raw)
        items[0]["sha256"] = hashlib.sha256(raw).hexdigest()
        items[0]["record_keys"] = ["fake"]
        result = audit_module.audit(items, self.root)
        self.assertIn("entry[0]:OFFICIAL_KEYS_NOT_IN_RAW", result["issues"])

    def test_missing_mapping_fails_closed(self):
        items = [self.entry(1), self.entry(2), self.entry(1, "detail")]
        del items[0]["record_path"]
        result = audit_module.audit(items, self.root)
        self.assertIn("entry[0]:OFFICIAL_KEY_MAPPING_REQUIRED", result["issues"])

    def test_invalid_raw_json_is_rejected_even_with_matching_hash(self):
        items = [self.entry(1), self.entry(2), self.entry(1, "detail")]
        raw = b"not-json"
        (self.root / items[0]["raw_path"]).write_bytes(raw)
        items[0]["sha256"] = hashlib.sha256(raw).hexdigest()
        result = audit_module.audit(items, self.root)
        self.assertIn("entry[0]:RAW_NOT_JSON", result["issues"])

    def test_contract_date_must_match_original_row(self):
        items = [self.entry(1), self.entry(2), self.entry(1, "detail")]
        items[0]["contract_date"] = "2026-11-18"
        self.assertIn("entry[0]:DATE_NOT_IN_ENTITY_ROWS",
                      audit_module.audit(items, self.root)["issues"])

    def test_delivery_date_must_match_original_row(self):
        items = [self.entry(1, family="delivery_order"),
                 self.entry(2, family="delivery_order"),
                 self.entry(1, "detail", "delivery_order")]
        items[1]["delivery_order_date"] = "2026-11-18"
        self.assertIn("entry[1]:DATE_NOT_IN_ENTITY_ROWS",
                      audit_module.audit(items, self.root)["issues"])

    def test_empty_bidder_unverified(self):
        items = [self.entry(1, family="bidder"), self.entry(2, family="bidder"),
                 self.entry(1, "detail", "bidder")]
        items[0].update({"classification": "no_bidders", "successBidInfo": []})
        self.assertIn("entry[0]:EMPTY_BIDDER_UNVERIFIED",
                      audit_module.audit(items, self.root)["issues"])


if __name__ == "__main__":
    unittest.main()
