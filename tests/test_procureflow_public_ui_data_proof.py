"""Regression tests: HTTP 200 and response SHA do not establish real records."""
import importlib.util
import pathlib
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "tools/procureflow/audit_public_ui_data_proof.py"
spec = importlib.util.spec_from_file_location("public_audit", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class PublicAuditTests(unittest.TestCase):
    def test_http200_and_digest_are_not_records(self):
        r = module.classify({"site": "shop", "post_response_count_total": 1,
            "tracked_post_responses": [{"method": "POST"}],
            "read_only_response_proofs": [{"status": 200, "body_bytes": 42,
                "body_sha256": "a"*64}]})
        self.assertEqual(r["status"], "NOT_VERIFIED")
        self.assertEqual(r["verified_list_records"], 0)
        self.assertEqual(r["verified_raw_response_bytes"], 0)

    def test_empty_200_is_flagged(self):
        r = module.classify({"read_only_response_proofs": [
            {"status": 200, "body_bytes": 0, "body_sha256": "0"*64}]})
        self.assertIn("HTTP_200_EMPTY_BODY", r["issues"])

    def test_missing_proof_is_not_success(self):
        self.assertEqual(module.classify({})["status"], "NOT_VERIFIED")

if __name__ == "__main__":
    unittest.main()
