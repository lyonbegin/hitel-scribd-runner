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

    def test_post_path_summary_uses_uncapped_counters(self):
        import importlib.util
        import sys
        tool_dir = str(SOURCE.parent)
        sys.path.insert(0, tool_dir)
        try:
            spec = importlib.util.spec_from_file_location("probe_contract_public_ui", SOURCE)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            report = {
                "tracked_post_responses": [{"method": "POST", "path": "/first"}] * 40,
                "post_response_path_counts": {
                    "www.g2b.go.kr|/first|200": 40,
                    "www.g2b.go.kr|/late-contract-list|200": 1,
                    "shop.g2b.go.kr|/late-product-list|403": 1,
                },
            }
            self.assertEqual(module.summarize_post_paths(report),
                             ["/first", "/late-contract-list", "/late-product-list"])
        finally:
            sys.path.remove(tool_dir)

    def test_all_post_response_paths_are_counted(self):
        source = SOURCE.read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn('"post_response_path_counts": {}', source)
        self.assertIn('counts[key] = counts.get(key, 0) + 1', source)
        self.assertIn('"post_response_path_counts": report["post_response_path_counts"]', source)

if __name__ == "__main__":
    unittest.main()
