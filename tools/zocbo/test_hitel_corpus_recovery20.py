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
        corpus.save(out/"reply_audit"/(old_job+".json"),{
            "job_id":old_job,"room_id":old_room,
            "source_key":"00041-00050",
            "method":"read_only_authenticated_chatgpt_browser",
            "result":"confirmed_no_reply_in_original_chat",
            "evidence_run_url":"https://github.com/lyonbegin/procureflow/actions/runs/999999999"
        })
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


    def test_repeat_terminal_recovery_and_exact_history(self):
        with tempfile.TemporaryDirectory() as root:
            out,old_room,first_job=self.fixture(root)
            room2="room_"+"3"*32
            room3="room_"+"4"*32
            second_job="job_"+"5"*32
            def fake_call(path,body=None):
                if path.endswith("/"+first_job):
                    return 200,{"job_id":first_job,"room_id":old_room,"status":"failed",
                                "stage":"web2api_failed","error":"WEB2API_SEND_OR_VERIFY_FAILED"}
                if path.endswith("/"+second_job):
                    return 200,{"job_id":second_job,"room_id":room2,"status":"failed",
                                "stage":"web2api_failed","error":"WEB2API_SEND_OR_VERIFY_FAILED"}
                if path.endswith("/rooms"):
                    return 200,{"room_id":room2 if body["name"].endswith(first_job[4:12]) else room3}
                raise AssertionError(path)
            with patch.object(corpus,"call",side_effect=fake_call):
                corpus.recover_terminal_failure(out,0,True)
                self.assertEqual(corpus.open_room(out,0),room2)
                corpus.save(out/"errors"/"00081-00100.json",{"type":"failed",
                    "response":{"job_id":second_job,"room_id":room2,"status":"failed",
                        "stage":"web2api_failed","error":"WEB2API_SEND_OR_VERIFY_FAILED"},
                    "checkpoint":{"job_id":second_job,"room_id":room2}})
                corpus.save(out/"reply_audit"/(second_job+".json"),{
                    "job_id":second_job,"room_id":room2,
                    "source_key":"00081-00100",
                    "method":"read_only_authenticated_chatgpt_browser",
                    "result":"confirmed_no_reply_in_original_chat",
                    "evidence_run_url":"https://github.com/lyonbegin/procureflow/actions/runs/999999999"
                })
                corpus.recover_terminal_failure(out,0,True)
                self.assertEqual(corpus.open_room(out,0),room3)
            saved=json.loads((out/"rooms"/"G000.json").read_text())
            self.assertEqual([e["job_id"] for e in saved["recovery_history"]],
                             [first_job,second_job])
            self.assertEqual(saved["room_id"],room3)
            self.assertEqual(saved["prior_room_id"],room2)

    def test_failed_same_batch_job_archived_before_new_request(self):
        with tempfile.TemporaryDirectory() as root:
            out,old_room,old_job=self.fixture(root)
            newroom="room_"+"3"*32
            newjob="job_"+"4"*32
            key="00081-00100"
            batch=[{"번호":i,"문서 ID":str(8000+i),"원문 제목":f"교재 {i}"}
                   for i in range(81,101)]
            question=corpus.title_prompt(batch)
            import hashlib
            digest=hashlib.sha256(question.encode("utf-8")).hexdigest()[:20]
            corpus.save(out/"jobs"/(key+".json"),
                        {"digest":digest,"room_id":old_room,
                         "request_id":"old-request-unique-id","job_id":old_job})
            corpus.save(out/"errors"/(key+".json"),{"type":"failed",
               "checkpoint":{"room_id":old_room,"job_id":old_job},
               "response":{"status":"failed","stage":"web2api_failed"}})
            corpus.save(out/"rooms"/"G000.json",{"room_id":newroom,
               "room_name":"REBOUND-ROOM","block":0,
               "recovery_history":[{"job_id":old_job,"room_id":old_room}]})
            rows=[{"no":i,"id":str(8000+i),"school":"중등","grade":"2",
                  "semester":"1","subject":"수학","edition":"해당없음",
                  "download":"대상","reason":"중학교 교재"} for i in range(81,101)]
            def fake_call(path,body=None):
                if path.endswith("/chat"):
                    self.assertEqual(body["room_id"],newroom)
                    self.assertIn("-r"+newroom[5:13],body["request_id"])
                    return 202,{"room_id":newroom,"job_id":newjob}
                if path.endswith("/"+newjob):
                    return 200,{"room_id":newroom,"status":"completed",
                                "result_text":json.dumps({"rows":rows},ensure_ascii=False)}
                raise AssertionError(path)
            with patch.object(corpus,"call",side_effect=fake_call):
                key1,status=corpus.execute_one(batch,newroom,out,20)
            self.assertEqual((key1,status),(key,"COMPLETED"))
            self.assertTrue((out/"jobs"/"history"/f"{key}-{old_job}.json").exists())
            self.assertTrue((out/"errors"/"history"/f"{key}-{old_job}.json").exists())
            newstate=json.loads((out/"jobs"/(key+".json")).read_text())
            self.assertEqual(newstate["job_id"],newjob)
            self.assertEqual(newstate["room_id"],newroom)
            self.assertEqual(len(json.loads((out/"completed"/(key+".json")).read_text())["rows"]),20)

    def test_failed_job_does_not_replay_without_authenticated_browser_audit(self):
        with tempfile.TemporaryDirectory() as root:
            out,old_room,jid=self.fixture(root)
            (out/"reply_audit"/(jid+".json")).unlink()
            def fake_call(path,body=None):
                if path.endswith("/"+jid):
                    return 200,{"job_id":jid,"room_id":old_room,
                        "status":"failed","stage":"web2api_failed",
                        "error":"WEB2API_SEND_OR_VERIFY_FAILED"}
                raise AssertionError("Must never send or create replacement room: "+path)
            with patch.object(corpus,"call",side_effect=fake_call):
                with self.assertRaisesRegex(ValueError,"CHATGPT_REPLY_ABSENCE_NOT_VERIFIED"):
                    corpus.recover_terminal_failure(out,0,True)
            state=json.loads((out/"rooms"/"G000.json").read_text())
            self.assertEqual(state["room_id"],old_room)




    def test_connection_lost_single_same_room_retry_and_id_history(self):
        import hashlib
        with tempfile.TemporaryDirectory() as root:
            out=Path(root)
            room="room_"+"a"*32
            first="job_"+"b"*32
            second="job_"+"c"*32
            batch=[{"번호":i,"문서 ID":str(900000+i),"원문 제목":f"수학 교재 {i}"}
                   for i in range(161,181)]
            key="00161-00180"
            digest=hashlib.sha256(corpus.title_prompt(batch).encode("utf-8")).hexdigest()[:20]
            corpus.save(out/"jobs"/(key+".json"),{"digest":digest,"room_id":room,
                "request_id":"already-sent-id","job_id":first})
            valid=[{"no":i,"id":str(900000+i),"school":"중등",
                    "grade":"1","semester":"1","subject":"수학",
                    "edition":"해당없음","download":"대상","reason":"중학교 수학"}
                   for i in range(161,181)]
            post_ids=[]
            def fake_call(path,body=None):
                if path.endswith("/"+first):
                    return 200,{"job_id":first,"room_id":room,"status":"failed",
                        "stage":"connection_lost","result_text":None,
                        "error":"GitHub Chrome disconnected; not automatically retried"}
                if path.endswith("/rooms") and body is None:
                    return 200,{"rooms":[{"room_id":room,"conversation_linked":True}]}
                if path.endswith("/chat"):
                    post_ids.append(body["request_id"])
                    self.assertEqual(body["room_id"],room)
                    return 202,{"job_id":second,"room_id":room}
                if path.endswith("/"+second):
                    return 200,{"job_id":second,"room_id":room,"status":"completed",
                        "result_text":json.dumps({"rows":valid})}
                raise AssertionError("unexpected transport request "+path)
            with patch.object(corpus,"call",side_effect=fake_call):
                k,st=corpus.execute_one(batch,room,out,20)
            self.assertEqual((k,st),(key,"COMPLETED"))
            self.assertEqual(len(post_ids),1)
            state=json.loads((out/"jobs"/(key+".json")).read_text())
            self.assertEqual(state["job_id"],second)
            self.assertEqual(state["connection_lost_retries"],1)
            self.assertIn(first,state["prior_failed_jobs"])
            self.assertTrue((out/"errors"/"history"/f"{key}-{first}.json").exists())
            self.assertTrue((out/"jobs"/"history"/f"{key}-{first}.json").exists())
            self.assertEqual(len(json.loads((out/"completed"/(key+".json")).read_text())["rows"]),20)

    def test_nfc_math_titles_are_only_normalized_for_prompt(self):
        import unicodedata
        nfd=unicodedata.normalize("NFD","[유형반복r 공통수학1]서술형 03.인수분해")
        batch=[{"번호":121,"문서 ID":"1008500237","원문 제목":nfd}]
        before=dict(batch[0])
        formatted=corpus.title_prompt(batch)
        legacy=corpus.title_prompt(batch,normalize_titles=False)
        self.assertIn(unicodedata.normalize("NFC",nfd),formatted)
        self.assertIn(nfd,legacy)
        self.assertNotIn(nfd,formatted)
        self.assertEqual(batch[0],before)
        self.assertIn("1008500237",formatted)



if __name__=="__main__":
    unittest.main()
