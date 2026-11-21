#!/usr/bin/env python3
"""Fail-closed, no-network tests of persisted 5-minute progress observations."""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import hitel_scribd_watchdog_progress as p


def sample(count=1940,first=1941,seconds=0,artifact_age=900,checks=1,
           state="running",phase="ai"):
    return {
        "version":1,"observed_at":100000+seconds,"verified":count,
        "first_missing":first,"checkpoint_at":100000+seconds-artifact_age,
        "unchanged_checks":checks,"suspected_stagnation":True,
        "classifier_job":phase,"classifier_step":p.base.CLASSIFY_STEP,
        "classifier_run":123,"classifier_phase":"ai / classified",
        "worker":{"connected":True,"heartbeat":True},
        "remote":{"status":state},
    }


class SampleSafety(unittest.TestCase):
    def test_first_observation_is_not_called_stalled(self):
        n,stale,why=p.comparison(None,sample())
        self.assertEqual(n,1)
        self.assertFalse(stale)
    def test_repeated_after_one_minute_not_counted(self):
        prev=sample(seconds=0,checks=1)
        now=sample(seconds=60)
        self.assertEqual(p.comparison(prev,now)[0],1)
        self.assertFalse(p.comparison(prev,now)[1])
    def test_second_five_minute_check_with_ten_minute_checkpoint_age(self):
        prev=sample(seconds=0,checks=1)
        now=sample(seconds=300,artifact_age=1000)
        n,stale,_=p.comparison(prev,now)
        self.assertEqual(n,2)
        self.assertTrue(stale)
    def test_unchanged_not_stale_before_ten_minutes(self):
        prev=sample(seconds=0,checks=1)
        now=sample(seconds=300,artifact_age=450)
        self.assertFalse(p.comparison(prev,now)[1])
    def test_progress_resets_unmodified_counter(self):
        prev=sample(count=1940,first=1941,checks=7)
        now=sample(count=1960,first=1961,seconds=300)
        self.assertEqual(p.comparison(prev,now)[0],1)
        self.assertFalse(p.comparison(prev,now)[1])
    def test_stable_worker_alive_and_ai_running_never_cancelled(self):
        cur=sample(state="running")
        client=object()
        with patch.object(p.base,"maybe_cancel_definitely_stuck") as c:
            reason=p.respond_safely(client,cur,
                      {"id":123,"status":"in_progress"},{"id":6})
            self.assertEqual(reason,
                             "remote_model_or_worker_active_do_not_duplicate")
            c.assert_not_called()
    def test_completed_verified_reply_allows_exact_read_only_resume(self):
        cur=sample(state="completed")
        cur["remote"].update({flag:True for flag in p.REMOTE_COMPLETED_FLAGS})
        with patch.object(p.base,"maybe_cancel_definitely_stuck",
                          return_value="safe_cancelled_verified_remote") as c:
            reason=p.respond_safely(object(),cur,
                                    {"id":123,"status":"in_progress"},{"id":6})
            self.assertEqual(reason,"safe_cancelled_verified_remote")
            self.assertEqual(c.call_args.kwargs["threshold_seconds"],600)
    def test_completed_without_send_evidence_not_cancelled(self):
        cur=sample(state="completed")
        cur["remote"].update({"result_ready":True,
                              "chatgpt_send_confirmed":None,
                              "assistant_reply_observed":True})
        with patch.object(p.base,"maybe_cancel_definitely_stuck") as c:
            self.assertEqual(
                p.respond_safely(object(),cur,
                      {"id":123,"status":"in_progress"},{"id":6}),
                "remote_not_verifiably_complete_preserve_old_job")
            c.assert_not_called()
    def test_unknown_and_send_seen_must_preserve(self):
        cur=sample(state="unknown")
        cur["remote"]["chatgpt_send_confirmed"]=True
        self.assertEqual(p.respond_safely(object(),cur,
            {"id":123,"status":"in_progress"},{"id":6}),
            "delivery_uncertain_or_seen_do_not_duplicate")
    def test_queued_classifier_not_cancelled(self):
        cur=sample()
        self.assertEqual(p.respond_safely(object(),cur,
            {"id":123,"status":"queued"},{"id":6}),
            "queued_worker_preserved")
    def test_no_active_run_uses_existing_single_handoff(self):
        cur=sample()
        self.assertEqual(p.respond_safely(object(),cur,None,{"id":6}),
            "restart_from_checkpoint_by_existing_monitor")
    def test_worker_wait_does_not_cancel_if_no_newer_checkpoint(self):
        cur=sample(phase="worker_ready")
        with patch.object(p.base,"retire_shadowed_preflight",
                          return_value=False) as c:
            self.assertEqual(p.respond_safely(object(),cur,
                  {"id":123,"status":"in_progress"},{"id":6}),
                  "waiting_for_chrome_without_ai_send")
            c.assert_called_once()
    def test_worker_wait_only_cancels_if_existing_guard_proves_safe(self):
        cur=sample(phase="worker_ready")
        with patch.object(p.base,"retire_shadowed_preflight",
                          return_value=True):
            self.assertEqual(p.respond_safely(object(),cur,
                 {"id":123,"status":"in_progress"},{"id":6}),
                 "shadowed_preflight_cancelled_no_ai_was_sent")
    def test_plain_observation_never_submits_any_chat(self):
        cur=sample();cur["suspected_stagnation"]=False
        with patch.object(p.base,"maybe_cancel_definitely_stuck") as c:
            self.assertEqual(p.respond_safely(object(),cur,
                    {"id":123,"status":"in_progress"},{"id":6}),
                    "healthy_or_not_proven_stale")
            c.assert_not_called()
    def test_previous_no_artifact_is_normal_first_run(self):
        api=type("Fake",(),{"request":lambda self,*args:
             (200,{"artifacts":[]})})()
        self.assertIsNone(p.prior_observation(api))
    def test_corrupt_sample_is_not_read_as_authorization(self):
        api=type("Fake",(),{
            "repository":"lyonbegin/hitel-scribd-runner",
            "token":"mock",
            "request":lambda self,*args:(200,{
                "artifacts":[{"name":p.SAMPLE_ARTIFACT,
                 "created_at":"2026-11-21T04:00:00Z",
                 "expired":False,
                 "workflow_run":{"id":9,"head_branch":"main"}}]})
        })()
        def write_invalid(*args,**kwargs):
            Path(args[0][args[0].index("-D")+1],p.SAMPLE_FILE).write_text("{}")
            return type("Result",(),{"returncode":0})()
        with patch.object(p.subprocess,"run",side_effect=write_invalid):
            with self.assertRaisesRegex(ValueError,"CORRUPTED"):
                p.prior_observation(api)


if __name__=="__main__":
    unittest.main()
