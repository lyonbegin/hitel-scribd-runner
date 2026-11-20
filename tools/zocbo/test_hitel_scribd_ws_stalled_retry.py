#!/usr/bin/env python3
"""Offline regression for a single explicitly authorized, source-preserving retry.

No network request or ChatGPT request is made by these tests.
"""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import hitel_scribd_ws_continue as runner


class ExplicitStalledRetryTests(unittest.TestCase):
    KEY="00301-00320"
    JOB="job_057e914e0e574fa9b66f85394db257ef"

    def fixture(self,root):
        out=Path(root)
        statefile=out/"ws"/"scribd_room.json"
        state={
            "room_name":runner.ROOM,
            "room_id":"room_"+"a"*32,
            "request_id":"hitel-client-"+"b"*32,
            "job_id":self.JOB,
            "seq":3,
            "text_sha256":"12345",
            "status":"unverified",
            "error_code":"WORKER_CONNECTION_LOST"
        }
        runner.save(statefile,state)
        remote={
            "job_id":self.JOB,
            "room_id":state["room_id"],
            "request_id":state["request_id"],
            "status":"stalled",
            "error_code":"WORKER_CONNECTION_LOST",
            "result_ready":False,
            "assistant_reply_observed":None,
            "chatgpt_send_confirmed":None
        }
        return out,statefile,state,remote

    def call(self,out,statefile,state,remote,authorized=True):
        payload=json.dumps(remote).encode("utf-8")
        with patch.dict(os.environ,{"HITEL_EXPLICIT_RETRY_STALLED_JOB":
                                 self.JOB if authorized else ""}):
            with patch.object(runner,"urlopen",return_value=io.BytesIO(payload)) as mock:
                result=runner.manually_retry_one_confirmed_stalled_job(
                    out,self.KEY,statefile,state)
                if authorized:
                    mock.assert_called_once()
                else:
                    mock.assert_not_called()
        return result

    def test_exact_one_terminal_job_archives_before_new_request(self):
        with tempfile.TemporaryDirectory() as d:
            out,path,state,remote=self.fixture(d)
            current=self.call(out,path,state,remote)
            self.assertEqual(current,{"room_name":runner.ROOM,
                                      "room_id":state["room_id"],"seq":3})
            self.assertEqual(json.loads(path.read_text("utf-8")),current)
            audit=out/"ws"/"stalled_history"/(self.KEY+"-"+self.JOB+".json")
            data=json.loads(audit.read_text("utf-8"))
            self.assertEqual(data["original_state"],state)
            self.assertEqual(data["read_only_remote_snapshot"],remote)
            self.assertFalse(data["original_counted_verified"])
            self.assertFalse(data["old_request_replayed"])

    def test_without_manual_authorization_does_not_mutate(self):
        with tempfile.TemporaryDirectory() as d:
            out,path,state,remote=self.fixture(d)
            self.assertEqual(self.call(out,path,state,remote,False),state)
            self.assertEqual(json.loads(path.read_text("utf-8")),state)
            self.assertFalse((out/"ws"/"stalled_history").exists())

    def test_rejects_mismatched_remote_identity(self):
        with tempfile.TemporaryDirectory() as d:
            out,path,state,remote=self.fixture(d)
            remote["request_id"]="another-request"
            with self.assertRaisesRegex(ValueError,"REMOTE_SCOPE_MISMATCH"):
                self.call(out,path,state,remote)
            self.assertEqual(json.loads(path.read_text("utf-8")),state)

    def test_rejects_any_reported_reply_or_live_job(self):
        for field,value in (("assistant_reply_observed",True),
                            ("chatgpt_send_confirmed",True),
                            ("result_ready",True),
                            ("status","running")):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as d:
                out,path,state,remote=self.fixture(d)
                remote[field]=value
                with self.assertRaisesRegex(ValueError,"NOT_CONFIRMED_SAFE"):
                    self.call(out,path,state,remote)
                self.assertEqual(json.loads(path.read_text("utf-8")),state)


if __name__=="__main__":
    unittest.main()
