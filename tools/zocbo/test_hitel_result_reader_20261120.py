#!/usr/bin/env python3
"""Scribd verified result retrieval without a live Railway/ChatGPT request."""
import base64, hashlib, json, unittest, urllib.parse
from unittest.mock import patch
import hitel_public_named_rooms_corpus as m

class ReadResultTests(unittest.TestCase):
    def setUp(self):
        self.job="job_"+"a"*32
        self.room="room_"+"b"*32
        self.payload=json.dumps({"rows":[{"no":1,"reason":"한글 테스트"*20000}]},ensure_ascii=False).encode("utf-8")
        self.meta={
          "job_id":self.job,"room_id":self.room,"status":"completed","result_ready":True,
          "result_text":None,"result_length_bytes":len(self.payload),
          "result_sha256":hashlib.sha256(self.payload).hexdigest()
        }

    def chunks(self,path):
        p=urllib.parse.urlsplit(path);q=urllib.parse.parse_qs(p.query)
        self.assertEqual(p.path,"/integrations/v1/public/jobs/"+self.job+"/result")
        off=int(q["offset"][0]);limit=int(q["limit"][0])
        b=self.payload[off:off+limit]
        return 200,{
            "job_id":self.job,"room_id":self.room,"offset":off,"bytes_returned":len(b),
            "next_offset":off+len(b),"complete":off+len(b)==len(self.payload),
            "content_base64":base64.b64encode(b).decode("ascii"),
            "result_length_bytes":len(self.payload),
            "result_sha256":self.meta["result_sha256"]
        }

    def test_large_verified_result_all_bytes_exact(self):
        self.assertGreater(len(self.payload),65536)
        with patch.object(m,"call",side_effect=self.chunks) as api:
            answer=m.read_completed_result(self.job,self.meta)
        self.assertEqual(answer.encode("utf-8"),self.payload)
        self.assertGreater(api.call_count,1)

    def test_small_inline_result_without_http(self):
        text='{"rows":[]}'
        meta={**self.meta,"result_text":text,"result_length_bytes":len(text),
              "result_sha256":hashlib.sha256(text.encode()).hexdigest()}
        with patch.object(m,"call") as api:
            self.assertEqual(m.read_completed_result(self.job,meta),text)
        api.assert_not_called()

    def test_byte_tampering_rejected(self):
        def corrupt(path):
            code,data=self.chunks(path)
            data["content_base64"]=base64.b64encode(b"X"+base64.b64decode(data["content_base64"])[1:]).decode()
            return code,data
        with patch.object(m,"call",side_effect=corrupt):
            with self.assertRaisesRegex(ValueError,"HASH_OR_LENGTH_MISMATCH"):
                m.read_completed_result(self.job,self.meta)

    def test_wrong_room_rejected_before_result_acceptance(self):
        def incorrect(path):
            code,data=self.chunks(path)
            data["room_id"]="room_"+"0"*32
            return code,data
        with patch.object(m,"call",side_effect=incorrect):
            with self.assertRaisesRegex(ValueError,"IDENTITY_OR_OFFSET_MISMATCH"):
                m.read_completed_result(self.job,self.meta)

    def test_unverified_not_accepted(self):
        with self.assertRaisesRegex(ValueError,"NOT_VERIFIED"):
            m.read_completed_result(self.job,{**self.meta,"result_ready":False})

if __name__=="__main__":
    unittest.main()
