import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from tools.procureflow.public_readonly_raw import retain_public_json

class PublicRawTest(unittest.TestCase):
    def test_exact_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            raw=b'{"result":{"successBidInfo":[],"success":false}}'
            r=retain_public_json(raw,"application/json; charset=utf-8",d,1)
            self.assertTrue(r["raw_verified"])
            self.assertEqual((Path(d)/r["raw_path"]).read_bytes(),raw)
            self.assertEqual(r["raw_sha256"],hashlib.sha256(raw).hexdigest())
    def test_reject_html_and_oversize(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(retain_public_json(b"<html/>","text/html",d,1)["raw_saved"])
            self.assertFalse(retain_public_json(b"x"*262145,"application/json",d,2)["raw_saved"])
            self.assertEqual(list(Path(d).iterdir()),[])

from tools.procureflow.audit_public_ui_data_proof import classify

class PublicRawAuditRegression(unittest.TestCase):
    def test_rehash_is_not_contract_proof(self):
        with tempfile.TemporaryDirectory() as d:
            raw=b'{"result":{"success":false}}'
            proof=retain_public_json(raw,"application/json",d,0)
            proof.update({"status":200,"body_sha256":hashlib.sha256(raw).hexdigest(),"body_bytes":len(raw)})
            report={"read_only_response_proofs":[proof]}
            self.assertEqual(classify(report,d)["verified_raw_response_bytes"],1)
            self.assertEqual(classify(report,d)["verified_list_records"],0)
            (Path(d)/proof["raw_path"]).write_bytes(b"corrupt")
            self.assertIn("RAW_BYTES_HASH_OR_LENGTH_MISMATCH",classify(report,d)["issues"])

if __name__=="__main__":
    unittest.main()
