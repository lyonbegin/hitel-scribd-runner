"""Regression tests for raw HTTP 200 + empty successBidInfo classification."""
import importlib.util
import json
import unittest
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "tools/procureflow/audit_stage2_empty_bidder_response.py"
spec = importlib.util.spec_from_file_location("stage2_empty_audit", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Stage2EmptyResponseTests(unittest.TestCase):
    def test_empty_list_is_not_zero_bidders(self):
        raw = json.dumps({"result": {"successBidInfo": [], "bidInfo": {"state": "unknown"}, "etcData": {}}}).encode()
        result = module.classify(200, raw)
        self.assertEqual(result["status"], "no_bidder_rows_unverified")
        self.assertFalse(result["verified_zero_bidders"])
        self.assertEqual(result["response_bytes"], len(raw))
        self.assertEqual(len(result["response_sha256"]), 64)
        self.assertEqual(result["bidInfo_type"], "dict")
        self.assertEqual(result["etcData_type"], "dict")
        self.assertIsNone(result["application_success_root"])
        self.assertIsNone(result["application_success_result"])

    def test_empty_response_preserves_application_context_without_claiming_zero(self):
        raw = json.dumps({"success": True, "result": {"success": True, "successBidInfo": [], "bidInfo": [], "etcData": None}}).encode()
        result = module.classify(200, raw)
        self.assertEqual(result["status"], "no_bidder_rows_unverified")
        self.assertEqual(result["bidInfo_type"], "list")
        self.assertEqual(result["etcData_type"], "NoneType")
        self.assertTrue(result["application_success_root"])
        self.assertTrue(result["application_success_result"])
        self.assertFalse(result["verified_zero_bidders"])

    def test_http_200_explicit_application_failure_is_not_empty_bidder_result(self):
        for doc in (
            {"success": False, "result": {"successBidInfo": []}},
            {"result": {"success": False, "successBidInfo": []}},
        ):
            with self.subTest(doc=doc):
                raw = json.dumps(doc).encode()
                result = module.classify(200, raw)
                self.assertEqual(result["reason"], "APPLICATION_EXPLICIT_FAILURE")
                self.assertEqual(result["status"], "unverified")
                self.assertFalse(result["verified_zero_bidders"])
                self.assertEqual(result["response_sha256"], __import__("hashlib").sha256(raw).hexdigest())

    def test_cli_rejects_original_byte_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "response.json"
            out_path = Path(tmp) / "audit.json"
            raw = b'{"result":{"successBidInfo":[]}}'
            raw_path.write_bytes(raw)
            base = [sys.executable, str(SOURCE), "--response", str(raw_path), "--http-status", "200", "--out", str(out_path), "--expected-sha256"]
            good = subprocess.run(base + [hashlib.sha256(raw).hexdigest()], capture_output=True, text=True)
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertTrue(json.loads(out_path.read_text())["original_sha256_matches"])
            bad = subprocess.run(base + ["0" * 64], capture_output=True, text=True)
            self.assertEqual(bad.returncode, 2)
            audit = json.loads(out_path.read_text())
            self.assertEqual(audit["reason"], "ORIGINAL_RESPONSE_SHA256_MISMATCH")
            self.assertFalse(audit["original_sha256_matches"])
            self.assertFalse(audit["verified_zero_bidders"])

    def test_non_200_does_not_become_zero(self):
        result = module.classify(503, b'{"result":{"successBidInfo":[]}}')
        self.assertEqual(result["reason"], "HTTP_NON_200")
        self.assertFalse(result["verified_zero_bidders"])

    def test_non_json_and_missing_fields(self):
        self.assertEqual(module.classify(200, b"<html>")[ "reason"], "NON_JSON_RESPONSE")
        self.assertEqual(module.classify(200, b'{"result":{}}')["reason"], "MISSING_OR_INVALID_SUCCESS_BID_INFO")

    def test_nonempty_not_automatically_complete(self):
        result = module.classify(200, b'{"result":{"successBidInfo":[{}]}}')
        self.assertEqual(result["status"], "bidder_rows_present_unverified")
        self.assertFalse(result["verified_zero_bidders"])


if __name__ == "__main__":
    unittest.main()
