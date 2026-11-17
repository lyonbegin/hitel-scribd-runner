#!/usr/bin/env python3
"""Regression checks: blocked POST and empty data cannot be marked complete."""
import unittest
import tempfile
import hashlib
from pathlib import Path
from tools.procureflow.audit_bootstrap_evidence import classify, missing_targets, verify_dom_bytes

class BootstrapEvidenceTest(unittest.TestCase):
    def test_dom_bytes_integrity_and_missing_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site_dir = root / "boot-g2b"
            site_dir.mkdir()
            data = b"<html><body></body></html>"
            (site_dir / "g2b_0_dom.html").write_bytes(data)
            row = {"requested_url": "https://www.g2b.go.kr/",
                   "dom": {"html_file": "g2b_0_dom.html",
                           "html_sha256": hashlib.sha256(data).hexdigest()}}
            self.assertEqual(verify_dom_bytes(root, {"g2b": [row]}), [])
            row["dom"]["html_sha256"] = "0" * 64
            self.assertEqual(verify_dom_bytes(root, {"g2b": [row]})[0]["reason"], "dom_sha256_mismatch")
            row["dom"]["html_file"] = "../escape_dom.html"
            self.assertEqual(verify_dom_bytes(root, {"g2b": [row]})[0]["reason"], "unsafe_dom_filename")
            row["dom"] = {}
            self.assertEqual(verify_dom_bytes(root, {"g2b": [row]})[0]["reason"], "missing_dom_file_or_sha256")

    def test_missing_site_or_report_is_not_silent_success(self):
        self.assertEqual(len(missing_targets({})), 5)
        self.assertEqual(len(missing_targets({"g2b":[{"requested_url":"https://www.g2b.go.kr/"}]})), 4)

    def test_complete_five_target_coverage(self):
        reports = {
            "g2b": [{"requested_url": "https://www.g2b.go.kr/"}],
            "data": [
                {"requested_url": "https://data.g2b.go.kr/"},
                {"requested_url": "https://data.g2b.go.kr/link/AISC001_01/?reptNm=UI-ADOXFA-112R"},
                {"requested_url": "https://data.g2b.go.kr/link/AISC001_01/?reptNm=UI-ADOXFA-113R"},
            ],
            "shop": [{"requested_url": "https://shop.g2b.go.kr/"}],
        }
        self.assertEqual(missing_targets(reports), [])

    def test_client_blocked_post_is_not_server_http_failure(self):
        row={"requested_url":"https://data.g2b.go.kr/","http_status":200,
             "dom":{"bodyChildren":0,"websquare":"object"},
             "request_failures":[{"method":"POST","failure":"net::ERR_ABORTED"}],
             "responses":[{"method":"GET","status":200}]}
        item=classify({"data":[row]})[0]
        self.assertEqual(item["failed_post_count"],1)
        self.assertEqual(item["ambiguous_post_failure_count"],1)
        self.assertEqual(item["confirmed_client_guard_post_count"],0)
        self.assertEqual(item["reason"],"post_failure_origin_unverified")
        self.assertEqual(item["observed_post_count"],0)
        self.assertEqual(item["verified_data_rows"],0)
        self.assertEqual(item["classification"],"NOT_VERIFIED")
    def test_explicit_client_guard_marker_is_distinguished(self):
        row={"requested_url":"https://data.g2b.go.kr/","http_status":200,
             "request_failures":[{"method":"POST","failure":"net::ERR_BLOCKED_BY_CLIENT","client_guard_blocked":True}]}
        item=classify({"data":[row]})[0]
        self.assertEqual(item["confirmed_client_guard_post_count"],1)
        self.assertEqual(item["ambiguous_post_failure_count"],0)
        self.assertEqual(item["reason"],"client_blocked_post_not_server_failure")

    def test_successful_http_200_post_is_not_data_validation(self):
        row={"requested_url":"https://www.g2b.go.kr/","http_status":200,
             "dom":{"bodyChildren":0,"websquare":"object"},
             "responses":[{"method":"POST","status":200}],
             "get_302":[{"status":302}]}
        item=classify({"g2b":[row]})[0]
        self.assertEqual(item["http_200_post_count"],1)
        self.assertEqual(item["verified_data_rows"],0)
        self.assertEqual(item["oidc_302_count"],1)

if __name__ == "__main__":
    unittest.main()
