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

    @staticmethod
    def _model_identity_batch():
        batch=[{"번호":n,"문서 ID":str(700000000+n)}
               for n in range(1921,1941)]
        batch[1933-1921]["문서 ID"]="712752016"
        batch[1934-1921]["문서 ID"]="712805770"
        reply={"rows":[{
            "no":r["번호"],"id":r["문서 ID"],
            "school":"대상외","grade":"해당없음",
            "semester":"해당없음","subject":"해당없음",
            "edition":"해당없음","download":"제외",
            "reason":"교육과정 교재가 아닌 기타 문서"
        } for r in batch]}
        return batch,reply

    def test_actual_1934_duplicate_id_fixed_only_from_verified_source(self):
        batch,reply=self._model_identity_batch()
        reply["rows"][1934-1921]["id"]="712752016"
        original=json.dumps(reply,ensure_ascii=False)
        audit=[]
        parsed=runner.validated_rows(original,batch,audit)
        self.assertEqual(len(parsed),20)
        self.assertEqual(parsed[1933-1921]["id"],"712752016")
        self.assertEqual(parsed[1934-1921]["id"],"712805770")
        self.assertEqual(audit[0]["no"],1934)
        self.assertEqual(audit[0]["model_id"],"712752016")
        self.assertEqual(audit[0]["verified_source_id"],"712805770")
        self.assertEqual(len(audit),1)
        self.assertEqual(json.loads(original)["rows"][1934-1921]["id"],
                         "712752016")

    def test_foreign_future_id_is_not_repaired(self):
        batch,reply=self._model_identity_batch()
        reply["rows"][1934-1921]["id"]="999999999"
        with self.assertRaisesRegex(ValueError,"future document IDs"):
            runner.validated_rows(json.dumps(reply),batch,[])

    def test_unique_but_swapped_ids_are_not_automatically_repaired(self):
        batch,reply=self._model_identity_batch()
        a,b=reply["rows"][12],reply["rows"][13]
        a["id"],b["id"]=b["id"],a["id"]
        with self.assertRaisesRegex(ValueError,"future document IDs"):
            runner.validated_rows(json.dumps(reply),batch,[])

    def test_duplicate_source_numbers_are_rejected(self):
        batch,reply=self._model_identity_batch()
        reply["rows"][13]["no"]=reply["rows"][12]["no"]
        reply["rows"][13]["id"]=reply["rows"][12]["id"]
        with self.assertRaises(ValueError):
            runner.validated_rows(json.dumps(reply),batch,[])

    def test_two_wrong_ids_are_rejected(self):
        batch,reply=self._model_identity_batch()
        reply["rows"][13]["id"]=reply["rows"][12]["id"]
        reply["rows"][15]["id"]=reply["rows"][14]["id"]
        with self.assertRaisesRegex(ValueError,"future document IDs"):
            runner.validated_rows(json.dumps(reply),batch,[])

    def test_exact_source_ids_produce_no_repair_audit(self):
        batch,reply=self._model_identity_batch()
        audit=[]
        parsed=runner.validated_rows(json.dumps(reply),batch,audit)
        self.assertEqual(len(parsed),20)
        self.assertEqual(audit,[])

    def test_exact_audited_2134_transcription_restored_without_requery(self):
        batch=[{"번호":n,"문서 ID":str(900000000+n)} for n in range(2121,2141)]
        batch[2134-2121]["문서 ID"]="748137062"
        reply={"rows":[{"no":item["번호"],"id":item["문서 ID"],
                "school":"고등","grade":"해당없음","semester":"해당없음",
                "subject":"미적분Ⅰ","edition":"판본검토",
                "download":"판본검토",
                "reason":"고등 수학Ⅱ 학생용 문제집으로 판본이 불확실합니다."}
                for item in batch]}
        reply["rows"][2134-2121]["id"]="748137352"
        immutable=json.dumps(reply,ensure_ascii=False)
        audit=[]
        result=runner.validated_rows(immutable,batch,audit)
        self.assertEqual(len(result),20)
        self.assertEqual(result[2134-2121]["id"],"748137062")
        self.assertEqual(audit[0]["no"],2134)
        self.assertEqual(audit[0]["immutable_result_job"],
                         "job_a0b91c0b09d044c9a9fb58e17129bc7e")
        self.assertEqual(json.loads(immutable)["rows"][2134-2121]["id"],
                         "748137352")

    def test_isolated_chat_uses_task_specific_post_not_legacy_public(self):
        with tempfile.TemporaryDirectory() as d:
            path,state=self.state(d)
            state["task_id"]="scribd-18109"
            runner.save(path,state)
            job={"request_id":state["request_id"],
                 "task_id":"scribd-18109",
                 "room_id":"room_"+"a"*32,"job_id":"job_"+"b"*32,
                 "accepted":True}
            with patch.object(runner,"fetch_existing",return_value=None):
                with patch.object(runner,"isolated_chat_once",
                                  return_value=(202,job)) as post:
                    with patch.object(runner,"call") as public_call:
                        result=runner.ensure_one_http_job(path,state,"prompt")
                        public_call.assert_not_called()
            post.assert_called_once()
            self.assertEqual(result["job_id"],job["job_id"])
            self.assertTrue(json.loads(path.read_text())["submit_attempted"])

    def test_isolated_existing_job_enforces_prefixed_task_room(self):
        with tempfile.TemporaryDirectory() as d:
            path,state=self.state(d)
            state["task_id"]="scribd-18109"
            state["submit_attempted"]=True
            runner.save(path,state)
            job={"request_id":state["request_id"],
                 "room_id":"room_"+"a"*32,"job_id":"job_"+"b"*32}
            status={"room_name":runner.expected_server_room_name(state),
                    "room_id":job["room_id"]}
            with patch.object(runner,"fetch_existing",return_value=job):
                with patch.object(runner,"call",return_value=(200,status)) as get:
                    result=runner.ensure_one_http_job(path,state,"prompt")
            self.assertEqual(result["job_id"],job["job_id"])
            get.assert_called_once()
            wrong={"room_name":state["room_name"],"room_id":job["room_id"]}
            state.pop("job_id")
            with patch.object(runner,"fetch_existing",return_value=job):
                with patch.object(runner,"call",return_value=(200,wrong)):
                    with self.assertRaisesRegex(ValueError,"ROOM_MISMATCH"):
                        runner.ensure_one_http_job(path,state,"prompt")

    def test_no_github_oidc_token_means_no_isolated_submission(self):
        with tempfile.TemporaryDirectory() as d:
            _,state=self.state(d)
            state["task_id"]="scribd-18109"
            with patch.dict("os.environ",{},clear=True):
                with self.assertRaisesRegex(RuntimeError,"OIDC_PRODUCER_NOT_AVAILABLE"):
                    runner.isolated_chat_once(state,"prompt")

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

    def test_isolated_false_stalled_job_keeps_get_only_when_task_active(self):
        with tempfile.TemporaryDirectory() as d:
            path,state=self.state(d)
            state.update({"task_id":"scribd-18109",
                          "job_id":"job_"+"b"*32,"room_id":"room_"+"a"*32})
            runner.save(path,state)
            initial={"job_id":state["job_id"],
                     "request_id":state["request_id"],
                     "room_id":state["room_id"],
                     "status":"stalled",
                     "error_code":"WORKER_NOT_ACTIVE_FOR_JOB"}
            task={"task_id":"scribd-18109","worker_connected":True,
                  "worker_heartbeat_recent":True,"worker_active_jobs_count":1}
            completed={**initial,"status":"completed","error_code":None,
                       "result_ready":True,
                       "chatgpt_send_confirmed":True,
                       "assistant_reply_observed":True}
            with patch.object(runner,"call",side_effect=[
                    (200,initial),(200,task),(200,completed)]) as gets:
                with patch.object(runner.time,"sleep") as sleep:
                    with patch.object(runner,"read_completed_result",
                                      return_value='{"rows":[]}'):
                        got,_=runner.await_http_reply(path,state)
            self.assertEqual(got,'{"rows":[]}')
            self.assertEqual(gets.call_count,3)
            sleep.assert_called_once_with(10)

    def test_isolated_false_stall_with_no_active_worker_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            path,state=self.state(d)
            state.update({"task_id":"scribd-18109",
                          "job_id":"job_"+"b"*32,"room_id":"room_"+"a"*32})
            runner.save(path,state)
            initial={"job_id":state["job_id"],
                     "request_id":state["request_id"],
                     "room_id":state["room_id"],
                     "status":"stalled",
                     "error_code":"WORKER_NOT_ACTIVE_FOR_JOB"}
            absent={"task_id":"scribd-18109","worker_connected":False,
                    "worker_heartbeat_recent":False,"worker_active_jobs_count":0}
            with patch.object(runner,"call",side_effect=[
                    (200,initial),(200,absent)]):
                with self.assertRaisesRegex(RuntimeError,"KEEP_CHECKPOINT"):
                    runner.await_http_reply(path,state)
            self.assertEqual(json.loads(path.read_text())["status"],"unverified")

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

    def test_worker_lost_terminal_request_can_prepare_one_audited_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); key="01861-01880";digest="a"*64
            original_req="scribd18109-"+key+"-"+digest[:32]
            room="HITEL-SCRIBD-18109-PROVEN-HTTP-20261121-"+key
            original={"key":key,"digest":digest,"source_ids":[{"no":1861,"id":"x"}],
                      "request_id":original_req,"room_name":room,
                      "job_id":"job_"+"f"*32,"status":"unverified",
                      "remote_status":"stalled",
                      "remote_error_code":"WORKER_CONNECTION_LOST"}
            file=root/"http"/(key+".json")
            runner.save(file,original)
            remote={"job_id":original["job_id"],"request_id":original_req,
                    "room_name":room,"status":"unknown",
                    "error_code":"WORKER_CONNECTION_LOST",
                    "result_ready":False,
                    "chatgpt_send_confirmed":None,
                    "assistant_reply_observed":None}
            with patch.object(runner,"call",return_value=(200,remote)):
                newfile,new=runner.recovery_after_verified_worker_disconnect(
                    root,key,digest,original["source_ids"],file,original,
                    original_req,room)
            self.assertNotEqual(newfile,file)
            self.assertEqual(new["request_id"],original_req+"-recovery1")
            self.assertTrue(new["prior_delivery_unknown"])
            self.assertEqual(json.loads(file.read_text()),original)
            self.assertFalse(new["submit_attempted"])
            with patch.object(runner,"call") as call:
                later,stored=runner.recovery_after_verified_worker_disconnect(
                    root,key,digest,original["source_ids"],file,original,
                    original_req,room)
                call.assert_not_called()
            self.assertEqual(later,newfile)
            self.assertEqual(stored,new)

    def test_worker_lost_but_send_seen_refuses_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);key="01861-01880";digest="b"*64
            rid="scribd18109-"+key+"-"+digest[:32]
            room="old-room"
            original={"key":key,"digest":digest,"source_ids":[],
                      "request_id":rid,"room_name":room,
                      "job_id":"job_"+"e"*32,"status":"unverified",
                      "remote_status":"stalled",
                      "remote_error_code":"WORKER_CONNECTION_LOST"}
            remote={"job_id":original["job_id"],"request_id":rid,
                    "room_name":room,"status":"stalled",
                    "error_code":"WORKER_CONNECTION_LOST",
                    "result_ready":False,
                    "chatgpt_send_confirmed":True}
            with patch.object(runner,"call",return_value=(200,remote)):
                with self.assertRaisesRegex(RuntimeError,
                                            "RECOVERY_NOT_SAFE_NO_REPOST"):
                    runner.recovery_after_verified_worker_disconnect(
                        root,key,digest,[],root/"original",original,rid,room)
            self.assertFalse((root/"http"/"worker_recoveries").exists())

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
