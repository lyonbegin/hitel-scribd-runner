#!/usr/bin/env python3
"""Offline regression: five-minute watchdog never causes duplicate AI sends."""
from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import hitel_scribd_watchdog as mod


def since(minutes: int) -> str:
    d = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)
    return d.isoformat()


class Fake:
    def __init__(self, results):
        self.repository = "lyonbegin/hitel-scribd-runner"
        self.token = "unused-test-token"
        self.results = list(results)
        self.calls = []
    def request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        return self.results.pop(0)


def run(status, minutes=10, id=500, conclusion=None):
    return {"id": id, "status": status, "conclusion": conclusion,
            "head_branch": "main", "event": "workflow_dispatch",
            "created_at": since(minutes),
            "updated_at": since(minutes)}


class WatchdogSafety(unittest.TestCase):
    def test_five_minute_check_never_cancels_healthy_active_run(self):
        client=Fake([(200, {"workflow_runs": [run("in_progress",5)]})])
        with patch.object(mod, "latest_artifact",return_value={"id":1}):
            with patch.object(mod, "maybe_cancel_definitely_stuck",
                              return_value="generating_or_observing_answer") as check:
                with patch.object(mod, "handoff") as handoff:
                    self.assertEqual(mod.monitor(client),"active_safe")
                    handoff.assert_not_called()
                    check.assert_called_once()
        self.assertFalse(any(method=="POST" for method,_,_ in client.calls))

    def test_queued_run_blocks_restarts_without_artifact_read(self):
        client=Fake([(200, {"workflow_runs": [run("queued",24)]})])
        with patch.object(mod, "latest_artifact") as art:
            with patch.object(mod, "handoff") as post:
                self.assertEqual(mod.monitor(client),"active_safe")
                post.assert_not_called()
                art.assert_not_called()

    def test_terminal_failure_resumes_from_verified_checkpoint(self):
        client=Fake([(200, {"workflow_runs": [run("completed",20,id=999,
                                                conclusion="failure")]})])
        with patch.object(mod,"latest_artifact",return_value={"id":1}):
            with patch.object(mod,"restore_checkpoint",
                              return_value=({n:{"id":str(n)} for n in range(1,1301)},1301)):
                with patch.object(mod,"handoff",
                                  return_value=("created",888)) as post:
                    self.assertEqual(mod.monitor(client),"created")
                    self.assertEqual(post.call_args.args[1],"watchdog-999")

    def test_no_restart_if_no_verified_checkpoint(self):
        client=Fake([(200, {"workflow_runs": [run("completed",20)]})])
        with patch.object(mod,"latest_artifact",side_effect=RuntimeError("missing")):
            with patch.object(mod,"handoff") as post:
                with self.assertRaises(RuntimeError):
                    mod.monitor(client)
                post.assert_not_called()

    def test_no_restart_during_short_visibility_grace(self):
        client=Fake([(200, {"workflow_runs": [run("completed",1)]})])
        with patch.object(mod,"latest_artifact",return_value={"id":1}):
            with patch.object(mod,"restore_checkpoint",return_value=({},1301)):
                with patch.object(mod,"handoff") as post:
                    self.assertEqual(mod.monitor(client),"grace")
                    post.assert_not_called()

    def test_complete_corpus_stops_dispatched_work(self):
        client=Fake([(200, {"workflow_runs": [run("completed",20)]})])
        with patch.object(mod,"latest_artifact",return_value={"id":1}):
            with patch.object(mod,"restore_checkpoint",return_value=({},None)):
                with patch.object(mod,"handoff") as post:
                    self.assertEqual(mod.monitor(client),"complete")
                    post.assert_not_called()

    def test_35_minutes_old_does_not_cancel_if_remote_generating(self):
        jobs={"jobs":[{"name":"ai","steps":[{"name":mod.CLASSIFY_STEP,
              "status":"in_progress","started_at":since(40)}]}]}
        client=Fake([(200,jobs)])
        with patch.object(mod,"restore_checkpoint",return_value=({1300:{}},1301)):
            with patch.object(mod,"read_remote_for_batch",
                              return_value={"status":"running"}) as remote:
                decision=mod.maybe_cancel_definitely_stuck(
                    client,run("in_progress",40),{"id":1})
        self.assertIn("remote_not_verified_preserve_run",decision)
        self.assertEqual([x[0] for x in client.calls],["GET"])

    def test_cancel_only_if_matching_remote_completed_and_verified(self):
        jobs={"jobs":[{"name":"ai","steps":[{"name":mod.CLASSIFY_STEP,
              "status":"in_progress","started_at":since(40)}]}]}
        client=Fake([(200,jobs),(202,None)])
        remote={"status":"completed",**{flag:True
               for flag in mod.SAFE_COMPLETED_FLAGS}}
        with patch.object(mod,"restore_checkpoint",return_value=({1300:{}},1301)):
            with patch.object(mod,"read_remote_for_batch",return_value=remote):
                decision=mod.maybe_cancel_definitely_stuck(
                    client,run("in_progress",40),{"id":1})
        self.assertEqual(decision,"safe_cancelled_verified_remote")
        self.assertEqual([x[0] for x in client.calls],["GET","POST"])
        self.assertIn("/cancel",client.calls[-1][1])

    def test_run_listing_failure_never_dispatches(self):
        client=Fake([(500,None)])
        with patch.object(mod,"handoff") as post:
            with self.assertRaisesRegex(RuntimeError,"LISTING_HTTP_500"):
                mod.monitor(client)
            post.assert_not_called()

    def test_checkpoint_duplicate_is_not_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"completed";p.mkdir()
            (p/"a.json").write_text('{"rows":[{"no":1300},{"no":1300}]}')
            fake=Fake([])
            with patch.object(mod.subprocess,"run") as sr:
                sr.return_value.returncode=0
                with self.assertRaisesRegex(ValueError,"DUPLICATE"):
                    mod.restore_checkpoint(fake,{"workflow_run":{"id":5}},Path(d))


if __name__=="__main__":
    unittest.main()
