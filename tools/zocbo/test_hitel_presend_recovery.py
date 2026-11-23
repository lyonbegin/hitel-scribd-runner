#!/usr/bin/env python3
"""All-local operator-gated pre-send recovery tests. No API, browser or AI send."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import hitel_scribd_http_continue as module


class PreSendRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file=Path(self.temp.name)/"http"/"05001-05020.json"
        self.file.parent.mkdir()
        self.state={
            "task_id":"scribd-18109","key":"05001-05020",
            "job_id":module.LEGACY_PRESEND_SCRIBD_JOB,
            "room_id":"room_"+"a"*32,
            "request_id":"scribd18109-05001-05020-e"*8,
            "status":"unverified",
        }
        self.remote={
            "job_id":self.state["job_id"],
            "room_id":self.state["room_id"],
            "request_id":self.state["request_id"],
            "status":"unknown","error_code":"UPSTREAM_DELIVERY_UNKNOWN",
            "result_ready":False,"chatgpt_send_confirmed":None,
            "assistant_reply_observed":None,
        }
        module.save(self.file,self.state)

    def run_recovery(self,receipt,env="approved",state=None,remote=None):
        state=state or self.state
        remote=remote or self.remote
        with patch.dict(os.environ,{"HITEL_SCRIBD_PRESEND_RECOVERY":env}),\
             patch.object(module,"isolated_chat_once",return_value=(202,receipt)) as submit:
            outcome=module.recover_proven_presend_once(self.file,state,remote)
        return outcome,submit

    def receipt(self):
        return {"accepted":True,"task_id":"scribd-18109",
                "job_id":"job_new_safe","room_id":"room_"+"b"*32,
                "request_id":"hitel-clean-scribd-18109-"+"a"*32,
                "recovery_kind":"source_pinned_legacy_pre_send"}

    def test_paused_by_default_refuses_any_post(self):
        result,submit=self.run_recovery(self.receipt(),env="0")
        self.assertFalse(result)
        submit.assert_not_called()

    def test_operator_approved_legacy_scope_posts_once(self):
        result,submit=self.run_recovery(self.receipt())
        self.assertTrue(result)
        submit.assert_called_once_with(self.state,"",recovery={
            "previous_job_id":module.LEGACY_PRESEND_SCRIBD_JOB,
            "previous_request_id":self.remote["request_id"]})
        saved=json.loads(self.file.read_text("utf-8"))
        self.assertEqual(saved["job_id"],"job_new_safe")
        self.assertEqual(saved["recovery_audit"][0]["source_proven_presend"],True)
        self.assertEqual(saved["recovery_audit"][0]["recovery_kind"],
                         "source_pinned_legacy_pre_send")

    def test_any_other_unknown_job_is_not_resubmitted(self):
        self.remote["job_id"]="job_not_pinned"
        self.state["job_id"]="job_not_pinned"
        outcome,submit=self.run_recovery(self.receipt())
        self.assertFalse(outcome);submit.assert_not_called()

    def test_any_positive_send_or_reply_evidence_denies_recovery(self):
        for flag in ("chatgpt_send_confirmed","assistant_reply_observed"):
            remote=dict(self.remote,**{flag:True})
            outcome,submit=self.run_recovery(self.receipt(),remote=remote)
            self.assertFalse(outcome);submit.assert_not_called()

    def test_live_or_completed_result_never_resubmitted(self):
        for status in ("running","completed"):
            remote=dict(self.remote,status=status)
            outcome,submit=self.run_recovery(self.receipt(),remote=remote)
            self.assertFalse(outcome);submit.assert_not_called()

    def test_instrumented_pre_send_can_resume_any_batch_once(self):
        state=dict(self.state,key="05021-05040",job_id="job_new_proven")
        remote=dict(self.remote,job_id="job_new_proven",
                    status="failed",
                    error_code="WEB2API_PRE_SEND_COMPOSER_NOT_FOUND")
        receipt=dict(self.receipt(),recovery_kind="instrumented_pre_send")
        outcome,submit=self.run_recovery(receipt,state=state,remote=remote)
        self.assertTrue(outcome);submit.assert_called_once()

    def test_pending_worker_does_not_mutate_request(self):
        receipt={"accepted":False,"pending":True,
                 "task_id":"scribd-18109",
                 "previous_job_id":self.state["job_id"]}
        result,submit=self.run_recovery(receipt)
        self.assertTrue(result);submit.assert_called_once()
        saved=json.loads(self.file.read_text("utf-8"))
        self.assertEqual(saved["job_id"],module.LEGACY_PRESEND_SCRIBD_JOB)

    def test_mismatched_server_receipt_fails_closed(self):
        for change in (
            {"task_id":"stock-a"},{"job_id":module.LEGACY_PRESEND_SCRIBD_JOB},
            {"recovery_kind":"transport_disconnected_uncertain"},
            {"request_id":"unknown"},{"room_id":"bad"}
        ):
            receipt=dict(self.receipt(),**change)
            with self.assertRaises(RuntimeError):
                self.run_recovery(receipt)
            self.assertEqual(json.loads(self.file.read_text("utf-8"))["job_id"],
                             module.LEGACY_PRESEND_SCRIBD_JOB)

    def test_wrong_task_never_issues_post(self):
        state=dict(self.state,task_id="stock-a")
        outcome,submit=self.run_recovery(self.receipt(),state=state)
        self.assertFalse(outcome);submit.assert_not_called()


if __name__=="__main__":
    unittest.main(verbosity=2)
