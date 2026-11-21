"""Regression: blocked requests beyond the first 40 must remain accounted for."""
import ast
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "tools/procureflow/probe_contract_public_ui.py"

class PublicUIGuardAccountingTests(unittest.TestCase):
    def test_block_count_is_not_sample_size(self):
        source = SOURCE.read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn('report["blocked_request_count_total"] += 1', source)
        self.assertIn('"block_count": report["blocked_request_count_total"]', source)
        self.assertIn('"blocked_request_sample_count": len(report["blocked_non_read_only_requests"])', source)
        self.assertIn('"blocked_request_sample_truncated": report["blocked_request_count_total"] > len(report["blocked_non_read_only_requests"])', source)
        self.assertNotIn('"block_count": len(report["blocked_non_read_only_requests"])', source)

if __name__ == "__main__":
    unittest.main()
