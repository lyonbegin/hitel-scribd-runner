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
            self.assertEqual(current,{"room_name":runner.RECOVERY_ROOM,"seq":0})
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


    def test_confirmed_room_conflict_rotates_and_archives_rejected_state(self):
        with tempfile.TemporaryDirectory() as d:
            out,path,state,remote=self.fixture(d)
            prior=out/"ws"/"stalled_history"/(self.KEY+"-"+self.JOB+".json")
            runner.save(prior,{"original_state":state,"original_counted_verified":False})
            rejected=dict(state)
            rejected.pop("job_id")
            rejected["status"]="rejected"
            rejected["error_code"]="ROOM_OR_REQUEST_CONFLICT"
            rejected["request_id"]="hitel-client-"+"c"*32
            runner.save(path,rejected)
            with patch.dict(os.environ,{"HITEL_EXPLICIT_RETRY_STALLED_JOB":self.JOB}):
                result=runner.rotate_rejected_conflict_to_new_room(
                    out,self.KEY,path,rejected)
            self.assertEqual(result,{"room_name":runner.RECOVERY_ROOM,"seq":0})
            evidence=(out/"ws"/"rejected_history"/
                      (self.KEY+"-"+rejected["request_id"]+".json"))
            self.assertTrue(evidence.exists())
            self.assertEqual(json.loads(evidence.read_text("utf-8"))["rejected_state"],rejected)
            self.assertFalse(json.loads(evidence.read_text("utf-8"))["counted_verified"])

    def test_rejected_rotation_fails_without_stalled_job_audit(self):
        with tempfile.TemporaryDirectory() as d:
            out,path,state,remote=self.fixture(d)
            state["status"]="rejected"
            state["error_code"]="ROOM_OR_REQUEST_CONFLICT"
            with patch.dict(os.environ,{"HITEL_EXPLICIT_RETRY_STALLED_JOB":self.JOB}):
                with self.assertRaisesRegex(ValueError,"ORIGINAL_AUDIT_MISSING"):
                    runner.rotate_rejected_conflict_to_new_room(out,self.KEY,path,state)
            self.assertEqual(json.loads(path.read_text("utf-8"))["status"],"unverified")


class FreshStartCleanupTests(unittest.TestCase):
    KEY="00361-00380"

    def fixture(self,root):
        out=Path(root)
        state=out/"ws"/"scribd_room.json"
        active=out/"ws"/"active_batch.json"
        completed=out/"completed"/"00341-00360.json"
        saved_job={
            "room_name":runner.RECOVERY_ROOM,
            "room_id":"room_"+"d"*32,
            "request_id":"hitel-client-"+"e"*32,
            "job_id":"job_"+"f"*32,
            "seq":4,
            "status":"running"
        }
        runner.save(state,saved_job)
        runner.save(active,{"key":self.KEY,"prompt_sha256":"same","source_ids":[]})
        runner.save(completed,{"rows":[{"no":341,"id":"confirmed"}]})
        return out,state,active,completed,saved_job

    def test_fresh_room_name_changes_per_batch(self):
        self.assertNotEqual(runner.fresh_room_name("00361-00380"),
                            runner.fresh_room_name("00381-00400"))
        self.assertNotEqual(runner.fresh_room_name(self.KEY),runner.RECOVERY_ROOM)

    def test_clean_transient_removes_legacy_but_preserves_verified(self):
        with tempfile.TemporaryDirectory() as root:
            out,state,active,completed,job=self.fixture(root)
            remote={
                "job_id":job["job_id"],"room_id":job["room_id"],
                "request_id":job["request_id"],"status":"stalled",
                "stage":"connection_lost","error_code":"WORKER_CONNECTION_LOST",
                "result_ready":False}
            with patch.dict(os.environ,{"HITEL_RESET_STUCK_BATCH":self.KEY}):
                with patch.object(runner,"urlopen",return_value=io.BytesIO(
                    json.dumps(remote).encode())) as fetch:
                    runner.retire_legacy_state_once(out,self.KEY)
                fetch.assert_called_once()
            self.assertFalse(state.exists())
            self.assertFalse(active.exists())
            self.assertTrue(completed.exists())
            self.assertEqual(json.loads(completed.read_text())["rows"][0]["no"],341)
            audit=json.loads((out/"ws"/"retired_state"/(self.KEY+".json")).read_text())
            self.assertEqual(audit["old_client_state"],job)
            self.assertEqual(audit["old_remote_read_only"]["status"],"stalled")
            self.assertFalse(audit["counted_as_completed"])

    def test_no_reset_without_exact_authorization(self):
        with tempfile.TemporaryDirectory() as root:
            out,state,active,completed,job=self.fixture(root)
            with patch.dict(os.environ,{"HITEL_RESET_STUCK_BATCH":"other"}):
                with patch.object(runner,"urlopen") as fetch:
                    runner.retire_legacy_state_once(out,self.KEY)
                fetch.assert_not_called()
            self.assertTrue(state.exists())
            self.assertTrue(active.exists())
            self.assertTrue(completed.exists())

    def test_rejects_reset_of_unrelated_active_batch(self):
        with tempfile.TemporaryDirectory() as root:
            out,state,active,completed,job=self.fixture(root)
            runner.save(active,{"key":"OTHER_BATCH"})
            with patch.dict(os.environ,{"HITEL_RESET_STUCK_BATCH":self.KEY}):
                with self.assertRaisesRegex(ValueError,"OTHER_ACTIVE_BATCH"):
                    runner.retire_legacy_state_once(out,self.KEY)
            self.assertTrue(state.exists())
            self.assertTrue(active.exists())

    def test_preflight_checks_actual_worker_ready_not_runner_presence(self):
        status={"worker_connected":True,"worker_heartbeat_recent":True,
                "worker_bootstrap_ready":True,"worker_available_for_new_job":True,
                "worker_busy":False,"worker_active_jobs_count":0,"worker_capacity":2}
        with patch.object(runner,"urlopen",return_value=io.BytesIO(
                json.dumps(status).encode())) as fetch:
            runner.check_worker_ready()
        fetch.assert_called_once()


if __name__=="__main__":
    unittest.main()
