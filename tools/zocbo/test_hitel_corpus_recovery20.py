#!/usr/bin/env python3
"""Offline regression for the 20-title Web2API continuation checkpoint.

No requests to the live HITEL server and no ChatGPT prompts are sent here.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parent))
import hitel_public_named_rooms_corpus as corpus


class TestResume20(unittest.TestCase):
    def fixture(self,root,server_stage="web2api_failed"):
        out=Path(root)
        old_room="room_"+"1"*32
        old_job="job_"+"2"*32
        corpus.save(out/"rooms"/"G000.json",{"room_id":old_room,
            "room_name":"HITEL-SCRIBD-FRESH-TEST","block":0})
        corpus.save(out/"errors"/"00041-00050.json",{"type":"failed",
            "response":{"job_id":old_job,"room_id":old_room,
                "status":"failed","stage":"web2api_failed",
                "error":"WEB2API_SEND_OR_VERIFY_FAILED"},
            "checkpoint":{"job_id":old_job,"room_id":old_room}})
        return out,old_room,old_job

    def test_terminal_failure_recovery_new_room_and_history(self):
        with tempfile.TemporaryDirectory() as root:
            out,old_room,jid=self.fixture(root)
            new_room="room_"+"3"*32
            requests=[]
            def fake_call(path,body=None):
                requests.append((path,body))
                if path.endswith("/"+jid):
                    return 200,{"job_id":jid,"room_id":old_room,"status":"failed",
                        "stage":"web2api_failed","error":"WEB2API_SEND_OR_VERIFY_FAILED"}
                if path.endswith("/rooms") and body:
                    return 200,{"room_id":new_room}
                raise AssertionError("unexpected request "+path)
            with patch.object(corpus,"call",side_effect=fake_call):
                corpus.recover_terminal_failure(out,0,True)
                room=corpus.open_room(out,0)
                corpus.recover_terminal_failure(out,0,True)
            self.assertEqual(room,new_room)
            state=json.loads((out/"rooms"/"G000.json").read_text())
            self.assertEqual(state["prior_room_id"],old_room)
            self.assertEqual(state["recovered_from_job"],jid)
            self.assertEqual(state["room_id"],new_room)
            self.assertEqual(len(requests),2)
            self.assertIn("RECOVER-G000",requests[1][1]["name"])

    def test_never_recover_without_exact_server_terminal_proof(self):
        with tempfile.TemporaryDirectory() as root:
            out,old_room,jid=self.fixture(root)
            def fake_call(path,body=None):
                return 200,{"job_id":jid,"room_id":old_room,"status":"running",
                            "stage":"web2api_running"}
            with patch.object(corpus,"call",side_effect=fake_call):
                with self.assertRaisesRegex(ValueError,"SERVER_CONFIRMED"):
                    corpus.recover_terminal_failure(out,0,True)
            state=json.loads((out/"rooms"/"G000.json").read_text())
            self.assertEqual(state["room_id"],old_room)

    def test_recovery_requires_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as root:
            out,old_room,_=self.fixture(root)
            with patch.object(corpus,"call",side_effect=AssertionError("network not allowed")):
                corpus.recover_terminal_failure(out,0,False)
            state=json.loads((out/"rooms"/"G000.json").read_text())
            self.assertEqual(state["room_id"],old_room)


if __name__=="__main__":
    unittest.main()
