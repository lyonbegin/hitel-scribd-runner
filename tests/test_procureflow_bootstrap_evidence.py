#!/usr/bin/env python3
"""Regression checks: blocked POST and empty data cannot be marked complete."""
import unittest
from tools.procureflow.audit_bootstrap_evidence import classify

class BootstrapEvidenceTest(unittest.TestCase):
    def test_client_blocked_post_is_not_server_http_failure(self):
        row={"requested_url":"https://data.g2b.go.kr/","http_status":200,
             "dom":{"bodyChildren":0,"websquare":"object"},
             "request_failures":[{"method":"POST","failure":"net::ERR_ABORTED"}],
             "responses":[{"method":"GET","status":200}]}
        item=classify({"data":[row]})[0]
        self.assertEqual(item["blocked_post_count"],1)
        self.assertEqual(item["observed_post_count"],0)
        self.assertEqual(item["verified_data_rows"],0)
        self.assertEqual(item["classification"],"NOT_VERIFIED")
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
