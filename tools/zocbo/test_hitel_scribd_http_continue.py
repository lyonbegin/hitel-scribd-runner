#!/usr/bin/env python3
"""Offline safety/transport regression tests for the proven HTTP public chat."""
import hashlib
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import hitel_scribd_http_continue as runner


class HttpOnceOnlyTests(unittest.TestCase):
    def state(self,folder):
        path=Path(folder)/"http"/"01101-01120.json"
        state={"key":"01101-01120","digest":"d"*64,
               "source_ids":[{"no":1101,"id":"x"}],
               "request_id":"scribd18109-01101-01120-"+("d"*32),
               "room_name":"HITEL-SCRIBD-18109-PROVEN-HTTP-20261121-01101-01120",
               "submit_attempted":False}
        runner.save(path,state)
        return path,state

    def test_one_post_and_checkpoint_then_resume_with_no_second_post(self):
        with tempfile.TemporaryDirectory() as d:
            path,state=self.state(d)
            job={"request_id":state["request_id"],"room_name":state["room_name"],
                 "room_id":"room_"+"a"*32,"job_id":"job_"+"b"*32,
                 "accepted":True}
            with patch.object(runner,"fetch_existing",return_value=None):
                with patch.object(runner,"call",return_value=(202,job)) as call:
                    got=runner.ensure_one_http_job(path,state,"prompt")
            self.assertEqual(call.call_count,1)
            self.assertTrue(json.loads(path.read_text())["submit_attempted"])
            with patch.object(runner,"call") as call:
                runner.ensure_one_http_job(path,got,"prompt")
                call.assert_not_called()

    def test_uncertain_post_never_retransmits_when_lookup_has_no_result(self):
        with tempfile.TemporaryDirectory() as d:
            path,state=self.state(d)
            state["submit_attempted"]=True
            runner.save(path,state)
            with patch.object(runner,"fetch_existing",return_value=None):
                with patch.object(runner,"call") as call:
                    with self.assertRaisesRegex(RuntimeError,"REFUSE_DUPLICATE_SEND"):
                        runner.ensure_one_http_job(path,state,"prompt")
                    call.assert_not_called()

    def test_lost_post_reply_can_recover_existing_request_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            path,state=self.state(d)
            state["submit_attempted"]=True
            runner.save(path,state)
            job={"request_id":state["request_id"],
                 "room_id":"room_"+"a"*32,"job_id":"job_"+"b"*32}
            status={"room_name":state["room_name"],"room_id":job["room_id"]}
            with patch.object(runner,"fetch_existing",return_value=job):
                with patch.object(runner,"call",return_value=(200,status)) as call:
                    got=runner.ensure_one_http_job(path,state,"prompt")
            self.assertEqual(got["job_id"],job["job_id"])
            self.assertEqual(call.call_count,1)
            self.assertEqual(call.call_args.args[0],runner.API+"/jobs/"+job["job_id"])

    def test_completed_reply_is_verified_by_three_evidence_flags(self):
        with tempfile.TemporaryDirectory() as d:
            path,state=self.state(d)
            state.update({"job_id":"job_"+"b"*32,"room_id":"room_"+"a"*32})
            runner.save(path,state)
            reply='{"rows":[]}'
            remote={"job_id":state["job_id"],"request_id":state["request_id"],
                    "room_id":state["room_id"],"status":"completed",
                    "result_ready":True,"chatgpt_send_confirmed":True,
                    "assistant_reply_observed":True}
            with patch.object(runner,"call",return_value=(200,remote)):
                with patch.object(runner,"read_completed_result",return_value=reply) as get:
                    answer,_=runner.await_http_reply(path,state)
            get.assert_called_once()
            self.assertEqual(answer,reply)
            self.assertEqual(json.loads(path.read_text())["answer_sha256"],
                             hashlib.sha256(reply.encode()).hexdigest())

    def test_failed_or_unknown_reply_cannot_be_counted_or_resent(self):
        with tempfile.TemporaryDirectory() as d:
            path,state=self.state(d)
            state.update({"job_id":"job_"+"b"*32,"room_id":"room_"+"a"*32})
            runner.save(path,state)
            remote={"job_id":state["job_id"],"request_id":state["request_id"],
                    "room_id":state["room_id"],"status":"unknown",
                    "error_code":"SERVER_RESTARTED_DELIVERY_UNKNOWN"}
            with patch.object(runner,"call",return_value=(200,remote)):
                with self.assertRaisesRegex(RuntimeError,"KEEP_CHECKPOINT"):
                    runner.await_http_reply(path,state)
            self.assertEqual(json.loads(path.read_text())["status"],"unverified")

    def test_legacy_unknown_job_audited_without_destroying_1100(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);key=runner.OLD_1101_KEY;digest="d"*64
            ids=[{"no":i,"id":str(i)} for i in range(1101,1121)]
            state={"job_id":runner.OLD_1101_JOB,
                   "room_id":"room_"+"a"*32,
                   "request_id":"hitel-client-"+"b"*32,
                   "room_name":runner.OLD_1101_ROOM,
                   "text_sha256":digest}
            runner.save(root/"ws"/(key+".json"),state)
            runner.save(root/"ws"/"active_batch.json",
                        {"key":key,"prompt_sha256":digest,"source_ids":ids})
            verified=root/"completed"/"01081-01100.json"
            runner.save(verified,{"rows":[{"no":1100,"id":"kept"}]})
            remote={"job_id":runner.OLD_1101_JOB,
                    "room_id":state["room_id"],"request_id":state["request_id"],
                    "result_ready":False,"status":"unknown","stage":"server_restarted",
                    "chatgpt_send_confirmed":None,"assistant_reply_observed":None}
            with patch.object(runner,"call",return_value=(200,remote)):
                runner.validate_old_1101(root,key,digest,ids)
            self.assertTrue(verified.exists())
            self.assertTrue((root/"ws"/"active_batch.json").exists())
            audit=json.loads((root/"http"/"old_ws_1101_audit.json").read_text())
            self.assertTrue(audit["prior_delivery_unknown"])
            self.assertTrue(audit["prior_job_not_counted_completed"])


if __name__=="__main__":
    unittest.main()
