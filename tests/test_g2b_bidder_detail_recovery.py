"""Offline regression tests; never contacts G2B or Stage 1."""
import asyncio
import csv
import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tools.procureflow import g2b_bidder_detail_stage2_recovery as stage2


class RecoveryTests(unittest.TestCase):
    def test_invalid_round_is_quarantined_not_worker_crash(self):
        async def test():
            with tempfile.TemporaryDirectory() as root:
                row={"bid_no":"R25BK00123456","bid_ord":"?","bid_clsfc_no":"0","bid_prgrs_ord":"000"}
                result=await stage2.inspect_bid(None,None,Path(root),row,None)
                self.assertEqual(result["status"],"error")
                original=list(Path(root).rglob("original_queue_row.json"))
                self.assertEqual(len(original),1)
                self.assertEqual(json.loads(original[0].read_text(encoding="utf-8"))["bid_ord"],"?")
        asyncio.run(test())

    def test_cached_verified_skips_only_if_raw_and_csv_are_complete(self):
        with tempfile.TemporaryDirectory() as root:
            d=Path(root)
            raw=b'{"result":{"successBidInfo":[{"grpNm":"ABC","totCnt":1}]}}'
            (d/"raw_00001.json.gz").write_bytes(gzip.compress(raw))
            with (d/"bidders.csv").open("w",newline="",encoding="utf-8") as f:
                writer=csv.DictWriter(f,fieldnames=stage2.COLUMNS)
                writer.writeheader()
                writer.writerow({"bid_no":"R25BK00123456","bidder_name":"ABC"})
            meta={"status":"verified_complete","bidder_count":1,
                  "pages":[{"page":1,"sha256_uncompressed":hashlib.sha256(raw).hexdigest()}]}
            self.assertTrue(stage2.cached_complete(d,meta))
            (d/"raw_00001.json.gz").write_bytes(b"corrupt")
            self.assertFalse(stage2.cached_complete(d,meta))

    def test_no_opening_is_not_zero_bidders(self):
        body=json.dumps({"ErrorMsg":"개찰결과 데이터가 존재하지 않습니다"},ensure_ascii=False).encode()
        rows,state=stage2.parse_response(422,body)
        self.assertIsNone(rows)
        self.assertEqual(state,"no_data")

    def test_duplicate_rows_across_pages_rejected(self):
        class Response:
            status=200
            def __init__(self,page):
                self.page=page
            async def body(self):
                value={"result":{"successBidInfo":[{
                    "grpNm":"ACME","bzmnRegNo":"123","totCnt":2,
                    "nextRowYn":"Y" if self.page==1 else "N"
                }]}}
                return json.dumps(value).encode()
        class Requests:
            async def post(self,url,data,headers,timeout):
                page=json.loads(data)["dlSrchOnbsRsltBidInM"]["currentPage"]
                return Response(page)
        async def test():
            with tempfile.TemporaryDirectory() as root:
                row={"bid_no":"R25BK00123456","bid_ord":"000",
                     "bid_clsfc_no":"0","bid_prgrs_ord":"000"}
                ctx=SimpleNamespace(request=Requests())
                args=SimpleNamespace(max_pages=20)
                result=await stage2.inspect_bid(ctx,asyncio.Semaphore(1),Path(root),row,args)
                self.assertEqual(result["status"],"error")
                self.assertIn("duplicate_bidder_rows_across_pages",result["error"])
                self.assertEqual(len(list(Path(root).rglob("raw_*.json.gz"))),2)
        asyncio.run(test())


if __name__=="__main__":
    unittest.main()
