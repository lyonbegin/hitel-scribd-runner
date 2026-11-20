#!/usr/bin/env python3
"""Offline contract tests for the current HITEL WebSocket client's native job lifecycle."""
from __future__ import annotations
import hashlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import hitel_scribd_ws_continue as runner


class CurrentAPIContractTests(unittest.TestCase):
    def setUp(self):
        self.rows=[{"번호":i,"문서 ID":str(i)} for i in range(1,21)]
        self.prompt="Twenty source-bound title judgments"
        self.digest=hashlib.sha256(self.prompt.encode("utf-8")).hexdigest()
        self.answer="Verified native API reply"
        self.sha=hashlib.sha256(self.answer.encode("utf-8")).hexdigest()
        self.key="00001-00020"

    def test_fresh_room_isolation_per_batch(self):
        self.assertNotEqual(runner.fresh_room_name("00001-00020"),
                            runner.fresh_room_name("00021-00040"))

    def test_one_live_status_without_arbitrary_worker_wait(self):
        status={"worker_connected":True,
                "worker_heartbeat_recent":True,
                "worker_bootstrap_ready":True,
                "worker_available_for_new_job":True}
        with patch.object(runner,"urlopen",
                          return_value=io.BytesIO(json.dumps(status).encode())) as fetch:
            runner.check_worker_ready()
        fetch.assert_called_once()

    def test_unavailable_worker_prevents_new_question(self):
        status={"worker_connected":True,
                "worker_heartbeat_recent":True,
                "worker_bootstrap_ready":False,
                "worker_available_for_new_job":False}
        with patch.object(runner,"urlopen",
                          return_value=io.BytesIO(json.dumps(status).encode())):
            with self.assertRaisesRegex(RuntimeError,"NO_QUESTION_SENT"):
                runner.check_worker_ready()

    def _mock_native_reply(self,command,**kwargs):
        self.assertNotIn("timeout",kwargs)
        self.assertEqual(kwargs["stdout"],subprocess.DEVNULL)
        state_path=Path(command[command.index("--state")+1])
        stored=json.loads(state_path.read_text("utf-8")) if state_path.exists() else {}
        stored.update({"room_name":runner.fresh_room_name(self.key),
                       "job_id":"job_"+"a"*32,
                       "room_id":"room_"+"b"*32,
                       "request_id":"hitel-client-"+"c"*32,
                       "status":"completed","sha256":self.sha,"answer":self.answer,
                       "text_sha256":self.digest,"seq":1})
        runner.save(state_path,stored)
        return subprocess.CompletedProcess(command,0)

    def _patch_classification(self):
        return (patch.object(runner,"load_verified",return_value={}),
                patch.object(runner,"title_prompt",return_value=self.prompt),
                patch.object(runner,"validated_rows",return_value=[
                    {"no":i,"id":str(i)} for i in range(1,21)]),
                patch.object(runner,"output_file",return_value={
                    "verified_ai_completed":20}))

    def test_new_send_waits_for_api_terminal_without_600_seconds(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            a,b,c,e=self._patch_classification()
            with a,b,c,e,patch.object(runner,"check_worker_ready") as ready:
                with patch.object(runner.subprocess,"run",
                                  side_effect=self._mock_native_reply) as proc:
                    self.assertEqual(runner.run_one(self.rows,out,Path("hitel_chat.py")),0)
            ready.assert_called_once()
            command=proc.call_args.args[0]
            self.assertIn("--text",command)
            self.assertNotIn("--resume",command)
            self.assertEqual(len(list((out/"completed").glob("*.json"))),1)
            self.assertFalse((out/"ws"/"active_batch.json").exists())

    def test_existing_pending_job_resumes_read_only_no_retransmission(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            statefile=out/"ws"/(self.key+".json")
            runner.save(statefile,{"room_name":runner.fresh_room_name(self.key),
                                   "status":"running",
                                   "text_sha256":self.digest,
                                   "request_id":"hitel-client-"+"c"*32,
                                   "job_id":"job_"+"a"*32,
                                   "room_id":"room_"+"b"*32,"seq":1})
            runner.save(out/"ws"/"active_batch.json",
                        {"key":self.key,
                         "prompt_sha256":self.digest,
                         "source_ids":[{"no":i,"id":str(i)} for i in range(1,21)]})
            a,b,c,e=self._patch_classification()
            with a,b,c,e,patch.object(runner,"check_worker_ready") as ready:
                with patch.object(runner.subprocess,"run",
                                  side_effect=self._mock_native_reply) as proc:
                    self.assertEqual(runner.run_one(self.rows,out,Path("hitel_chat.py")),0)
            ready.assert_not_called()
            self.assertIn("--resume",proc.call_args.args[0])
            self.assertNotIn("--text",proc.call_args.args[0])

    def test_rejected_api_send_does_not_create_unrelated_new_question(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            runner.save(out/"ws"/(self.key+".json"),
                        {"room_name":runner.fresh_room_name(self.key),
                         "status":"rejected","error_code":"ROOM_OR_REQUEST_CONFLICT"})
            a,b,c,e=self._patch_classification()
            with a,b,c,e:
                with self.assertRaisesRegex(ValueError,"PREVIOUS_WS_SEND_REJECTED"):
                    runner.run_one(self.rows,out,Path("hitel_chat.py"))

    def test_ambiguous_failed_request_does_not_mark_batch_completed(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            a,b,c,e=self._patch_classification()
            with a,b,c,e,patch.object(runner,"check_worker_ready"):
                with patch.object(runner.subprocess,"run",
                                  return_value=subprocess.CompletedProcess([],1)):
                    with patch.object(runner,"report_failed_api_job") as report:
                        self.assertEqual(
                            runner.run_one(self.rows,out,Path("hitel_chat.py")),2)
            report.assert_called_once()
            self.assertFalse((out/"completed").exists())
            self.assertTrue((out/"ws"/"active_batch.json").exists())


if __name__=="__main__":
    unittest.main()
