import hashlib
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
        raw = ('{"page":%d,"kind":"%s","official_key":"%s"}' % (page, kind, key or f"{family}-{kind}-{page}")).encode()
        (self.root / path).write_bytes(raw)
        result = {"family": family, "kind": kind,
                  "url": "https://www.g2b.go.kr/public/search",
                  "method": "POST", "http_status": 200, "raw_path": path,
                  "sha256": hashlib.sha256(raw).hexdigest(),
                  "page": page, "record_keys": [key or f"{family}-{kind}-{page}"]}
        if family == "contract":
            result["contract_date"] = "2026-11-17"
        if family == "delivery_order":
            result["delivery_order_date"] = "2026-11-17"
        return result

    def test_sample_pass_does_not_mean_full_coverage(self):
        result = audit_module.audit([self.entry(1), self.entry(2),
                                     self.entry(1, "detail")], self.root)
        self.assertTrue(result["pass_sample_evidence"])
        self.assertFalse(result["full_2y_complete"])
        self.assertFalse(result["join_verified"])

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

    def test_manifest_key_not_in_raw_is_rejected(self):
        items = [self.entry(1), self.entry(2), self.entry(1, "detail")]
        items[0]["record_keys"] = ["invented-key"]
        result = audit_module.audit(items, self.root)
        self.assertIn("entry[0]:OFFICIAL_KEYS_NOT_IN_RAW", result["issues"])
        self.assertFalse(result["pass_sample_evidence"])

    def test_invalid_raw_json_is_rejected_even_with_matching_hash(self):
        items = [self.entry(1), self.entry(2), self.entry(1, "detail")]
        raw = b"not-json"
        (self.root / items[0]["raw_path"]).write_bytes(raw)
        items[0]["sha256"] = hashlib.sha256(raw).hexdigest()
        result = audit_module.audit(items, self.root)
        self.assertIn("entry[0]:RAW_NOT_JSON", result["issues"])

    def test_empty_bidder_unverified(self):
        items = [self.entry(1, family="bidder"), self.entry(2, family="bidder"),
                 self.entry(1, "detail", "bidder")]
        items[0].update({"classification": "no_bidders", "successBidInfo": []})
        self.assertIn("entry[0]:EMPTY_BIDDER_UNVERIFIED",
                      audit_module.audit(items, self.root)["issues"])


if __name__ == "__main__":
    unittest.main()
