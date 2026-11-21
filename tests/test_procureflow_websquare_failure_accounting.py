"""Regression guard: sampled WebSquare failures must not mask totals."""
import ast
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "tools/procureflow/probe_websquare_bootstrap.py"

class WebsquareFailureAccountingTests(unittest.TestCase):
    def test_total_is_not_capped_sample(self):
        source = SOURCE.read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn('"request_failure_count_total":len(failed_requests)', source)
        self.assertIn('"request_failure_sample_truncated":len(failed_requests)>40', source)
        self.assertIn('"client_guard_sample_truncated":len(guard_decisions)-guard_start>80', source)
        self.assertIn('"failed_request_count":r["request_failure_count_total"]', source)
        self.assertNotIn('"failed_request_count":len(r["request_failures"])', source)

if __name__ == "__main__":
    unittest.main()
