"""Regression checks for bounded POST samples versus total POST response counts."""
import ast
import pathlib
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "tools/procureflow/probe_contract_public_ui.py"


class PostAccountingTests(unittest.TestCase):
    def test_total_counter_is_not_sample_length(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('report["post_response_count_total"] += 1', source)
        self.assertIn('"post_response_count_observed": report["post_response_count_total"]', source)
        self.assertIn('"post_response_sample_count": len(report["tracked_post_responses"])', source)
        self.assertIn('report["post_response_count_total"] > len(report["tracked_post_responses"])', source)

    def test_python_syntax(self):
        ast.parse(SOURCE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
