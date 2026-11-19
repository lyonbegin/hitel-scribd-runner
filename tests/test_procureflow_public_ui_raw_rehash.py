import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from tools.procureflow.audit_public_ui_data_proof import classify

class PublicUiRawAuditTest(unittest.TestCase):
    def test_rehash_and_mismatch_do_not_prove_contract(self):
        with tempfile.TemporaryDirectory() as d:
            raw = b'{"result":{"success":false,"successBidInfo":[]}}'
            digest = hashlib.sha256(raw).hexdigest()
            Path(d, "sample.json").write_bytes(raw)
            proof = {"status": 200, "body_bytes": len(raw),
                     "body_sha256": digest, "raw_saved": True,
                     "raw_path": "sample.json", "raw_bytes": len(raw),
                     "raw_sha256": digest}
            report = {"site": "g2b", "post_response_count_total": 1,
                      "tracked_post_responses": [{"status": 200}],
                      "read_only_response_proofs": [proof]}
            good = classify(report, d)
            self.assertEqual(good["verified_raw_response_bytes"], 1)
            self.assertEqual(good["verified_list_records"], 0)
            self.assertEqual(good["status"], "NOT_VERIFIED")
            Path(d, "sample.json").write_bytes(raw + b" ")
            bad = classify(report, d)
            self.assertEqual(bad["verified_raw_response_bytes"], 0)
            self.assertIn("RAW_BYTES_HASH_OR_LENGTH_MISMATCH", bad["issues"])
    def test_missing_and_path_escape(self):
        with tempfile.TemporaryDirectory() as d:
            report = {"read_only_response_proofs": [
                {"raw_saved": True, "raw_path": "../outside.json"},
                {"raw_saved": True, "raw_path": "missing.json"}]}
            audit = classify(report, d)
            self.assertIn("UNSAFE_RAW_PATH", audit["issues"])
            self.assertIn("RAW_BYTES_MISSING", audit["issues"])
            self.assertEqual(audit["verified_raw_response_bytes"], 0)

if __name__ == "__main__":
    unittest.main()
