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
if __name__=="__main__":
    unittest.main()
