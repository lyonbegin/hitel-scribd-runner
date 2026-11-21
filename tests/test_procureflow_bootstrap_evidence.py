#!/usr/bin/env python3
"""Regression checks: blocked POST and empty data cannot be marked complete."""
import unittest
import tempfile
import hashlib
from pathlib import Path
from tools.procureflow.audit_bootstrap_evidence import classify, missing_targets, verify_dom_bytes

class BootstrapEvidenceTest(unittest.TestCase):
    def test_late_post_paths_are_not_lost_to_first_90_static_events(self):
        from tools.procureflow.probe_contract_public_ui import summarize_post_paths
        report = {
            "events": [{"method": "GET", "path": "/static/app.js"}] * 90,
            "tracked_post_responses": [
                {"method": "POST", "path": "/public/selectContractList.do"},
                {"method": "POST", "path": "/public/selectContractList.do"},
                {"method": "GET", "path": "/irrelevant"},
            ],
        }
        self.assertEqual(summarize_post_paths(report), ["/public/selectContractList.do"])
        self.assertEqual(summarize_post_paths({"events": report["events"]}), [])


    def test_duplicate_targets_are_not_accepted(self):
        from tools.procureflow.audit_bootstrap_evidence import duplicate_targets
        rows = [{"requested_url": "https://www.g2b.go.kr/"}] * 2
        self.assertEqual(len(duplicate_targets({"g2b": rows})), 1)

    def test_symlink_and_malformed_sha_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site = root / "boot-g2b"
            site.mkdir()
            outside = root / "outside_dom.html"
            outside.write_bytes(b"outside")
            (site / "g2b_0_dom.html").symlink_to(outside)
            row = {"requested_url": "https://www.g2b.go.kr/", "dom": {
                "html_file": "g2b_0_dom.html", "html_sha256": hashlib.sha256(b"outside").hexdigest()}}
            self.assertEqual(verify_dom_bytes(root, {"g2b": [row]})[0]["reason"], "unsafe_dom_symlink")
            (site / "g2b_0_dom.html").unlink()
            (site / "g2b_0_dom.html").write_bytes(b"outside")
            row["dom"]["html_sha256"] = "bad"
            self.assertEqual(verify_dom_bytes(root, {"g2b": [row]})[0]["reason"], "invalid_dom_sha256")

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

    def test_probe_records_query_free_failed_post_metadata(self):
        import ast
        source = (Path(__file__).resolve().parents[1] / "tools/procureflow/probe_websquare_bootstrap.py").read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn('"path":urlsplit(req.url).path[:240]', source)
        self.assertIn('"reason": "non_readonly_method_blocked_before_network"', source)
        self.assertIn('"server_http_status": None', source)
        self.assertIn('"resource_type":req.resource_type', source)
        self.assertIn('"client_guard_blocked":', source)
        self.assertNotIn('"post_data":', source)

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

    def test_explicit_guard_without_requestfailed_is_not_server_response(self):
        row = {"requested_url": "https://www.g2b.go.kr/",
               "client_guard_decisions": [{"method": "POST", "path": "/bootstrap",
                   "reason": "non_readonly_method_blocked_before_network", "server_http_status": None}],
               "responses": []}
        item = classify({"g2b": [row]})[0]
        self.assertEqual(item["explicit_guard_post_count"], 1)
        self.assertEqual(item["confirmed_client_guard_post_count"], 1)
        self.assertEqual(item["observed_post_count"], 0)
        self.assertEqual(item["reason"], "client_blocked_post_not_server_failure")
        self.assertEqual(item["classification"], "NOT_VERIFIED")

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
