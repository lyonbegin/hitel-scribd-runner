"""A successful HTTP response never proves bidder/contract completeness."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/procureflow"))
from public_readonly_raw import classify_public_json


class PublicResponseSemantics(unittest.TestCase):
    def test_empty_bidder_rows_remain_unverified(self):
        body = b'{"result":{"successBidInfo":[],"bidInfo":{},"etcData":{}}}'
        self.assertEqual(classify_public_json(body, "application/json", 200),
                         "NO_BIDDER_ROWS_UNVERIFIED")

    def test_nonempty_json_is_not_verified_automatically(self):
        self.assertEqual(classify_public_json(b'{"result":{"successBidInfo":[{}]}}',
                         "application/json", 200), "JSON_STRUCTURE_UNVERIFIED")

    def test_http_errors_and_html_do_not_count_as_data(self):
        self.assertEqual(classify_public_json(b'{}', "application/json", 403), "HTTP_NOT_200")
        self.assertEqual(classify_public_json(b'<html></html>', "text/html", 200),
                         "NON_JSON_UNVERIFIED")

    def test_invalid_json_is_unverified(self):
        self.assertEqual(classify_public_json(b'{', "application/json", 200),
                         "INVALID_JSON_UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
