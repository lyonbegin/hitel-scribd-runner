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


class ExplicitInterruptedWindowRecoveryTests(unittest.TestCase):
    KEY=runner.FAILED_KEY
    JOB=runner.FAILED_JOB
    PROMPT_DIGEST="f"*64
    IDS=[{"no":i,"id":str(i)} for i in range(1001,1021)]

    def make_state(self,dir):
        out=Path(dir)
        active=out/"ws"/"active_batch.json"
        statefile=out/"ws"/(self.KEY+".json")
        completed=out/"completed"/"00981-01000.json"
        state={"room_name":runner.FAILED_ROOM,
               "room_id":"room_"+"a"*32,
               "request_id":"hitel-client-"+"b"*32,
               "job_id":self.JOB,"status":"unverified",
               "error_code":runner.FAILED_ERROR,
               "text_sha256":self.PROMPT_DIGEST,
               "seq":1}
        runner.save(statefile,state)
        runner.save(active,{"key":self.KEY,"prompt_sha256":self.PROMPT_DIGEST,
                            "source_ids":self.IDS})
        runner.save(completed,{"rows":[{"no":981,"id":"confirmed"}]})
        remote={"job_id":self.JOB,"request_id":state["request_id"],
                "room_id":state["room_id"],"status":"stalled",
                "error_code":runner.FAILED_ERROR,"stage":"web2api_received",
                "result_ready":False,"assistant_reply_observed":None,
                "chatgpt_send_confirmed":None}
        return out,statefile,active,completed,state,remote

    def test_old_stalled_job_audited_before_fresh_room_and_completed_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            out,statefile,active,completed,state,remote=self.make_state(d)
            with patch.dict("os.environ",{"HITEL_EXPLICIT_RESTART_FAILED_KEY":self.KEY}):
                with patch.object(runner,"urlopen",
                        return_value=io.BytesIO(json.dumps(remote).encode())) as get:
                    runner.archive_failed_window_before_restart(
                        out,self.KEY,self.PROMPT_DIGEST,self.IDS)
                get.assert_called_once()
            self.assertFalse(statefile.exists())
            self.assertFalse(active.exists())
            self.assertTrue(completed.exists())
            audit=json.loads((out/"ws"/"restart_audit"/(self.KEY+"-"+self.JOB+".json")).read_text())
            self.assertEqual(audit["old_client_state"],state)
            self.assertTrue(audit["possible_previous_delivery"])
            self.assertFalse(audit["old_result_verified"])
            self.assertNotEqual(runner.fresh_room_name(self.KEY),runner.FAILED_ROOM)

    def test_never_restart_if_remote_reply_or_delivery_confirmed(self):
        for key,value in (("result_ready",True),("assistant_reply_observed",True),
                          ("chatgpt_send_confirmed",True),("status","running")):
            with self.subTest(key=key),tempfile.TemporaryDirectory() as d:
                out,statefile,active,completed,state,remote=self.make_state(d)
                remote[key]=value
                with patch.dict("os.environ",{"HITEL_EXPLICIT_RESTART_FAILED_KEY":self.KEY}):
                    with patch.object(runner,"urlopen",
                            return_value=io.BytesIO(json.dumps(remote).encode())):
                        with self.assertRaisesRegex(ValueError,"NOT_STALLED_OR_MAY_HAVE_REPLY"):
                            runner.archive_failed_window_before_restart(
                                out,self.KEY,self.PROMPT_DIGEST,self.IDS)
                self.assertTrue(statefile.exists())
                self.assertTrue(active.exists())
                self.assertTrue(completed.exists())

    def test_no_restart_without_exact_explicit_authorization(self):
        with tempfile.TemporaryDirectory() as d:
            out,statefile,active,completed,state,remote=self.make_state(d)
            with patch.dict("os.environ",{"HITEL_EXPLICIT_RESTART_FAILED_KEY":""}):
                with patch.object(runner,"urlopen") as get:
                    runner.archive_failed_window_before_restart(
                        out,self.KEY,self.PROMPT_DIGEST,self.IDS)
                get.assert_not_called()
            self.assertTrue(statefile.exists())
            self.assertTrue(active.exists())

    def test_reject_changed_source_mapping_or_digest(self):
        with tempfile.TemporaryDirectory() as d:
            out,statefile,active,completed,state,remote=self.make_state(d)
            with patch.dict("os.environ",{"HITEL_EXPLICIT_RESTART_FAILED_KEY":self.KEY}):
                with patch.object(runner,"urlopen") as get:
                    with self.assertRaisesRegex(ValueError,"CHECKPOINT_MISMATCH"):
                        runner.archive_failed_window_before_restart(
                            out,self.KEY,"changed-digest",self.IDS)
                get.assert_not_called()
            self.assertTrue(completed.exists())
            self.assertTrue(statefile.exists())


class CapacityRejectionRecoveryTests(unittest.TestCase):
    KEY=runner.FAILED_KEY
    DIGEST="f"*64
    IDS=[{"no":i,"id":str(i)} for i in range(1001,1021)]

    def make_state(self,dir):
        out=Path(dir)
        old=out/"ws"/"restart_audit"/(self.KEY+"-"+runner.FAILED_JOB+".json")
        runner.save(old,{"original_job":"archived"})
        statefile=out/"ws"/(self.KEY+".json")
        active=out/"ws"/"active_batch.json"
        verified=out/"completed"/"00981-01000.json"
        state={"room_name":runner.RECOVERY_ROOM,
               "room_id":"room_"+"a"*32,
               "request_id":"hitel-client-"+"b"*32,
               "job_id":runner.CAPACITY_JOB,"status":"unverified",
               "error_code":"web2api_failed",
               "text_sha256":self.DIGEST,"seq":1}
        runner.save(statefile,state)
        runner.save(active,{"key":self.KEY,"prompt_sha256":self.DIGEST,
                            "source_ids":self.IDS})
        runner.save(verified,{"rows":[{"no":981,"id":"verified"}]})
        remote={"job_id":runner.CAPACITY_JOB,"request_id":state["request_id"],
                "room_id":state["room_id"],"status":"failed",
                "stage":"web2api_failed","error":runner.CAPACITY_ERROR,
                "result_ready":False,"assistant_reply_observed":None,
                "chatgpt_send_confirmed":None}
        return out,statefile,active,verified,state,remote

    def test_exact_capacity_failure_archived_and_only_new_room_used(self):
        with tempfile.TemporaryDirectory() as d:
            out,statefile,active,verified,state,remote=self.make_state(d)
            with patch.dict("os.environ",{"HITEL_EXPLICIT_RESTART_FAILED_KEY":self.KEY}):
                with patch.object(runner,"urlopen",
                        return_value=io.BytesIO(json.dumps(remote).encode())) as get:
                    runner.archive_failed_window_before_restart(out,self.KEY,
                                                                self.DIGEST,self.IDS)
                get.assert_called_once()
            self.assertTrue(verified.exists())
            self.assertFalse(statefile.exists())
            self.assertFalse(active.exists())
            self.assertNotEqual(runner.fresh_room_name(self.KEY),runner.RECOVERY_ROOM)
            audit=json.loads((out/"ws"/"restart_audit"/
                              (self.KEY+"-"+runner.CAPACITY_JOB+".json")).read_text())
            self.assertTrue(audit["capacity_rejected_before_send"])
            self.assertFalse(audit["counted_as_completed"])

    def test_rejects_any_uncertain_capacity_delivery_or_wrong_cause(self):
        for field,value in (("status","running"),("error","OTHER_ERROR"),
                            ("result_ready",True),("chatgpt_send_confirmed",True),
                            ("assistant_reply_observed",True)):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as d:
                out,statefile,active,verified,state,remote=self.make_state(d)
                remote[field]=value
                with patch.dict("os.environ",{"HITEL_EXPLICIT_RESTART_FAILED_KEY":self.KEY}):
                    with patch.object(runner,"urlopen",
                            return_value=io.BytesIO(json.dumps(remote).encode())):
                        with self.assertRaisesRegex(ValueError,"CAPACITY_FAILURE_NOT_CONFIRMED_SAFE"):
                            runner.archive_failed_window_before_restart(out,self.KEY,
                                                                        self.DIGEST,self.IDS)
                self.assertTrue(statefile.exists())
                self.assertTrue(verified.exists())

    def test_refuses_missing_original_audit(self):
        with tempfile.TemporaryDirectory() as d:
            out,statefile,active,verified,state,remote=self.make_state(d)
            (out/"ws"/"restart_audit"/(self.KEY+"-"+runner.FAILED_JOB+".json")).unlink()
            with patch.dict("os.environ",{"HITEL_EXPLICIT_RESTART_FAILED_KEY":self.KEY}):
                with self.assertRaisesRegex(ValueError,"ORIGINAL_STALLED_AUDIT_MISSING"):
                    runner.archive_failed_window_before_restart(out,self.KEY,
                                                                self.DIGEST,self.IDS)
            self.assertTrue(statefile.exists())
            self.assertTrue(verified.exists())


class Stalled1101RestartTests(unittest.TestCase):
    KEY=runner.RETRY_1101_KEY
    DIGEST="d"*64
    IDS=[{"no":i,"id":str(i)} for i in range(1101,1121)]

    def fixture(self,path):
        root=Path(path)
        active=root/"ws"/"active_batch.json"
        statefile=root/"ws"/(self.KEY+".json")
        state={"room_name":runner.RETRY_1101_OLD_ROOM,
               "room_id":"room_"+"b"*32,
               "request_id":"hitel-client-"+"c"*32,
               "job_id":runner.RETRY_1101_JOB,"status":"unverified",
               "error_code":runner.RETRY_1101_ERROR,
               "text_sha256":self.DIGEST}
        runner.save(statefile,state)
        runner.save(active,{"key":self.KEY,"prompt_sha256":self.DIGEST,
                           "source_ids":self.IDS})
        kept=root/"completed"/"01081-01100.json"
        runner.save(kept,{"rows":[{"no":1100,"id":"retained"}]})
        remote={"job_id":state["job_id"],"request_id":state["request_id"],
                "room_id":state["room_id"],"status":"stalled",
                "error_code":runner.RETRY_1101_ERROR,"result_ready":False,
                "chatgpt_send_confirmed":None,"assistant_reply_observed":None}
        return root,active,statefile,kept,remote

    def test_stalled_1101_restart_preserves_verified_and_audits_uncertainty(self):
        with tempfile.TemporaryDirectory() as d:
            root,active,statefile,kept,remote=self.fixture(d)
            with patch.dict("os.environ",{"HITEL_EXPLICIT_RESTART_FAILED_KEY":self.KEY}):
                with patch.object(runner,"urlopen",
                    return_value=io.BytesIO(json.dumps(remote).encode())):
                    runner.archive_stalled_1101_before_authorized_restart(
                        root,self.KEY,self.DIGEST,self.IDS)
            self.assertFalse(active.exists())
            self.assertFalse(statefile.exists())
            self.assertTrue(kept.exists())
            audit=root/"ws"/"restart_audit"/(self.KEY+"-"+runner.RETRY_1101_JOB+".json")
            saved=json.loads(audit.read_text())
            self.assertTrue(saved["possible_prior_delivery"])
            self.assertFalse(saved["original_result_verified"])
            self.assertEqual(runner.fresh_room_name(self.KEY),runner.RETRY_1101_NEW_ROOM)

    def test_stalled_1101_refuses_unconfirmed_previous_delivery(self):
        for key,value in (("status","running"),("result_ready",True),
                         ("chatgpt_send_confirmed",True),
                         ("assistant_reply_observed",True)):
            with self.subTest(key=key),tempfile.TemporaryDirectory() as d:
                root,active,statefile,kept,remote=self.fixture(d)
                remote[key]=value
                with patch.dict("os.environ",{"HITEL_EXPLICIT_RESTART_FAILED_KEY":self.KEY}):
                    with patch.object(runner,"urlopen",
                        return_value=io.BytesIO(json.dumps(remote).encode())):
                        with self.assertRaisesRegex(ValueError,"NOT_SAFE_TO_RESTART"):
                            runner.archive_stalled_1101_before_authorized_restart(
                                root,self.KEY,self.DIGEST,self.IDS)
                self.assertTrue(active.exists())
                self.assertTrue(kept.exists())

    def test_stalled_1101_requires_explicit_key_and_exact_checkpoint(self):
        with tempfile.TemporaryDirectory() as d:
            root,active,statefile,kept,remote=self.fixture(d)
            with patch.dict("os.environ",{"HITEL_EXPLICIT_RESTART_FAILED_KEY":""}):
                with patch.object(runner,"urlopen") as call:
                    runner.archive_stalled_1101_before_authorized_restart(
                        root,self.KEY,self.DIGEST,self.IDS)
                call.assert_not_called()
            with patch.dict("os.environ",{"HITEL_EXPLICIT_RESTART_FAILED_KEY":self.KEY}):
                with patch.object(runner,"urlopen") as call:
                    with self.assertRaisesRegex(ValueError,"SCOPE_MISMATCH"):
                        runner.archive_stalled_1101_before_authorized_restart(
                            root,self.KEY,"changed",self.IDS)
                call.assert_not_called()
            self.assertTrue(statefile.exists())
            self.assertTrue(kept.exists())


if __name__=="__main__":
    unittest.main()
