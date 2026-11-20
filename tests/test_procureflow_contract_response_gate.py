import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.procureflow.audit_contract_response_gate import classify, audit_manifest


class ContractResponseGateTests(unittest.TestCase):
    def test_empty_bidder_is_unknown(self):
        result = classify(b'{"result":{"successBidInfo":[]}}', http_status=200,
                          url="https://www.g2b.go.kr/", kind="bidder")
        self.assertEqual(result["reason"], "no_bidder_rows_unverified")
        self.assertEqual(result["verified_records"], 0)

    def test_html_200_not_contract_proof(self):
        result = classify(b"<html></html>", http_status=200,
                          url="https://data.g2b.go.kr/", kind="contract")
        self.assertEqual(result["status"], "NOT_VERIFIED")

    def test_json_200_not_contract_proof(self):
        result = classify(b'{"rows":[{"contractNo":"123"}]}', http_status=200,
                          url="https://www.g2b.go.kr/", kind="contract", page=1)
        self.assertEqual(result["verified_records"], 0)

    def test_manifest_integrity(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            raw = b'{"rows":[]}'
            (root / "response.json").write_bytes(raw)
            manifest = {"responses": [{"file": "response.json", "http_status": 200,
                       "url": "https://shop.g2b.go.kr/", "kind": "mas",
                       "sha256": hashlib.sha256(raw).hexdigest()}]}
            self.assertFalse(audit_manifest(manifest, root)["complete"])
            manifest["responses"][0]["sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                audit_manifest(manifest, root)

    def test_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                audit_manifest({"responses": [{"file": "../outside", "http_status": 200,
                               "url": "https://www.g2b.go.kr/", "kind": "contract",
                               "sha256": "0" * 64}]}, Path(d))


if __name__ == "__main__":
    unittest.main()
