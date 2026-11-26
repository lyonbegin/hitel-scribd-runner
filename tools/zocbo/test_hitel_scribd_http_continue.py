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

    def test_2195_one_digit_source_id_transcription_is_audited(self):
        batch=[{"번호":n,"문서 ID":str(750000000+n)} for n in range(2181,2201)]
        batch[2195-2181]["문서 ID"]="758882344"
        reply={"rows":[{
            "no":b["번호"],"id":b["문서 ID"],"school":"고등",
            "grade":"해당없음","semester":"해당없음",
            "subject":"영어","edition":"2015전용",
            "download":"제외","reason":"2024 수능 영어 어법 어휘 답지"
        } for b in batch]}
        reply["rows"][2195-2181]["id"]="758882304"
        immutable=json.dumps(reply,ensure_ascii=False)
        audit=[]
        result=runner.validated_rows(immutable,batch,audit)
        self.assertEqual(len(result),20)
        self.assertEqual(result[2195-2181]["id"],"758882344")
        self.assertEqual(len(audit),1)
        self.assertEqual(audit[0]["model_id"],"758882304")
        self.assertEqual(audit[0]["verified_source_id"],"758882344")
        self.assertEqual(json.loads(immutable)["rows"][2195-2181]["id"],
                         "758882304")

    def test_two_digit_foreign_id_not_repaired_by_generic_rule(self):
        batch=[{"번호":n,"문서 ID":str(760000000+n)} for n in range(2201,2221)]
        reply={"rows":[{
            "no":b["번호"],"id":b["문서 ID"],"school":"대상외",
            "grade":"해당없음","semester":"해당없음",
            "subject":"해당없음","edition":"해당없음",
            "download":"제외","reason":"교육과정 교재가 아님"
        } for b in batch]}
        original=batch[0]["문서 ID"]
        corrupted=list(original)
        corrupted[0]="9"
        corrupted[1]="9"
        reply["rows"][0]["id"]="".join(corrupted)
        with self.assertRaisesRegex(ValueError,"future document IDs"):
            runner.validated_rows(json.dumps(reply),batch,[])

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

    def test_exact_2181_oidc_push_403_can_retry_once_only_on_signed_dispatch(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"http"/"02181-02200.json"
            digest="c58ef9aed39a78d6ed52838df6a2d4b5a1974f6441939df40ac8175790f18fb1"
            state={"key":"02181-02200","digest":digest,
                   "source_ids":[{"no":i,"id":str(750000000+i)}
                                 for i in range(2181,2201)],
                   "request_id":"scribd18109-02181-02200-"+digest[:32],
                   "room_name":"HITEL-SCRIBD-18109-PROVEN-HTTP-20261121-02181-02200",
                   "task_id":"scribd-18109","status":"prepared",
                   "submit_attempted":True}
            runner.save(path,state)
            accepted={"request_id":state["request_id"],
                      "room_id":"room_"+"a"*32,"job_id":"job_"+"b"*32,
                      "accepted":True}
            with patch.dict("os.environ",{"GITHUB_EVENT_NAME":"workflow_dispatch"}):
                with patch.object(runner,"fetch_existing",return_value=None):
                    with patch.object(runner,"isolated_chat_once",
                                      return_value=(202,accepted)) as post:
                        out=runner.ensure_one_http_job(path,state,"prompt")
            self.assertEqual(out["job_id"],accepted["job_id"])
            post.assert_called_once()
            audit=path.parent/"producer_rejections"/"02181-02200.json"
            self.assertTrue(audit.exists())
            self.assertTrue(json.loads(audit.read_text())["single_recovery_only"])
            # If a later POST failed with an uncertain outcome, the audit
            # marker blocks any second submission even when GET is 404.
            state.pop("job_id",None)
            with patch.dict("os.environ",{"GITHUB_EVENT_NAME":"workflow_dispatch"}):
                with patch.object(runner,"fetch_existing",return_value=None):
                    with patch.object(runner,"isolated_chat_once") as post:
                        with self.assertRaisesRegex(RuntimeError,"ALREADY_RECOVERED"):
                            runner.ensure_one_http_job(path,state,"prompt")
                        post.assert_not_called()

    def test_2181_push_event_may_not_recover_prior_403(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"http"/"02181-02200.json"
            digest="c58ef9aed39a78d6ed52838df6a2d4b5a1974f6441939df40ac8175790f18fb1"
            state={"key":"02181-02200","digest":digest,
                   "source_ids":[{"no":i} for i in range(2181,2201)],
                   "request_id":"scribd18109-02181-02200-"+digest[:32],
                   "room_name":"HITEL-SCRIBD-18109-PROVEN-HTTP-20261121-02181-02200",
                   "task_id":"scribd-18109","submit_attempted":True}
            runner.save(path,state)
            with patch.dict("os.environ",{"GITHUB_EVENT_NAME":"push"}):
                with patch.object(runner,"fetch_existing",return_value=None):
                    with patch.object(runner,"isolated_chat_once") as post:
                        with self.assertRaisesRegex(RuntimeError,"REFUSE_DUPLICATE_SEND"):
                            runner.ensure_one_http_job(path,state,"prompt")
                        post.assert_not_called()

    def test_stalled_unknown_old_request_recovers_only_with_disconnected_task(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);key="02981-03000";digest="a"*64
            request="scribd18109-"+key+"-"+digest[:32]
            name="HITEL-SCRIBD-18109-PROVEN-HTTP-20261121-"+key
            source=[{"no":n,"id":str(800000000+n)} for n in range(2981,3001)]
            old={"key":key,"digest":digest,"source_ids":source,
                 "request_id":request,"room_name":name,"task_id":"scribd-18109",
                 "status":"unverified","remote_status":"stalled",
                 "remote_error_code":"UPSTREAM_DELIVERY_UNKNOWN",
                 "submit_attempted":True,"job_id":"job_"+"a"*32,
                 "room_id":"room_"+"a"*32}
            file=root/"http"/(key+".json")
            runner.save(file,old)
            remote={"job_id":old["job_id"],"room_id":old["room_id"],
                    "request_id":request,"status":"stalled",
                    "error_code":"UPSTREAM_DELIVERY_UNKNOWN",
                    "result_ready":False,"chatgpt_send_confirmed":None,
                    "assistant_reply_observed":None,"updated_at":1_795_000_000_000}
            worker={"task_id":"scribd-18109","worker_connected":False,
                    "worker_heartbeat_recent":False,"worker_active_jobs_count":1}
            with patch.object(runner.time,"time",return_value=1_795_001_000.0):
                with patch.object(runner,"call",side_effect=[(200,remote),(200,worker)]):
                    target,recovered=runner.recover_signed_task_only_after_terminal_disconnect(
                        root,key,digest,source,file,old,file,old,request,name)
            self.assertEqual(recovered["task_id"],"scribd-18109")
            self.assertEqual(recovered["request_id"],request+"-recovery1")
            self.assertTrue(recovered["prior_delivery_unknown"])
            self.assertEqual(recovered["recovery_from_job"],old["job_id"])
            self.assertFalse(recovered["submit_attempted"])
            self.assertEqual(json.loads(file.read_text()),old)
            self.assertTrue(target.exists())

    def test_signed_recovery_refuses_live_worker_or_seen_send(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);key="02981-03000";digest="a"*64
            source=[{"no":n,"id":str(n)} for n in range(2981,3001)]
            original={"key":key,"digest":digest,"source_ids":source,
                "request_id":"scribd18109-"+key+"-"+digest[:32],
                "room_name":"HITEL-SCRIBD-18109-PROVEN-HTTP-20261121-"+key,
                "task_id":"scribd-18109","status":"unverified",
                "remote_status":"stalled","remote_error_code":"UPSTREAM_DELIVERY_UNKNOWN",
                "job_id":"job_"+"a"*32,"room_id":"room_"+"a"*32}
            file=root/"http"/(key+".json")
            runner.save(file,original)
            remote={"job_id":original["job_id"],"room_id":original["room_id"],
                    "request_id":original["request_id"],"status":"stalled",
                    "error_code":"UPSTREAM_DELIVERY_UNKNOWN",
                    "result_ready":False,"chatgpt_send_confirmed":None,
                    "assistant_reply_observed":None,"updated_at":1_795_000_000_000}
            worker={"task_id":"scribd-18109","worker_connected":True,
                    "worker_heartbeat_recent":True}
            with patch.object(runner.time,"time",return_value=1_795_001_000):
                with patch.object(runner,"call",side_effect=[(200,remote),(200,worker)]):
                    with self.assertRaisesRegex(RuntimeError,"WORKER_STILL_PRESENT"):
                        runner.recover_signed_task_only_after_terminal_disconnect(
                            root,key,digest,source,file,original,file,original,
                            original["request_id"],original["room_name"])
                remote["assistant_reply_observed"]=True
                with patch.object(runner,"call",return_value=(200,remote)):
                    with self.assertRaisesRegex(RuntimeError,"SEND_OR_REPLY"):
                        runner.recover_signed_task_only_after_terminal_disconnect(
                            root,key,digest,source,file,original,file,original,
                            original["request_id"],original["room_name"])

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



class SupervisorRecoveryTests(unittest.TestCase):
    def sample(self,n=20):
        return [{"번호":8961+i,"문서 ID":str(371313300+i),
                 "원문 제목":f"distinct title {i}"} for i in range(n)]

    def response(self,batch):
        from hitel_scribd_supervisor import keyed_inputs, SCHEMA
        return {"schema":SCHEMA,"rows":[{**entry,"school":"대상외","grade":"해당없음",
                "semester":"해당없음","subject":"기타","edition":"해당없음",
                "download":"제외","reason":"학교 교재가 아님"} for entry in keyed_inputs(batch)]}

    def transport(self,batch,invalid_scopes=(),fail_first=False,stop_after=None):
        from hitel_scribd_supervisor import digest
        jobs={}
        sends=[]
        def ensure(path,state,prompt):
            req=state["request_id"]
            if req not in jobs:
                self.assertNotIn("문서 ID",prompt)
                self.assertTrue("schema" in prompt)
                jobs[req]=len(jobs)+1
                sends.append(req)
            num=jobs[req]
            state.update({"job_id":f"job_{num:032x}","room_id":f"room_{num:032x}",
                          "submit_attempted":True,"status":"accepted"})
            runner.save(path,state)
            return state
        def await_(path,state):
            if stop_after is not None and len(sends)>stop_after:
                raise RuntimeError("simulated runner shutdown")
            ids={r["no"] for r in state["source_ids"]}
            sub=[x for x in batch if x["번호"] in ids]
            reply=self.response(sub)
            n=len(sub)
            attempt=int(state["request_id"].split("-a")[-1])
            if n in invalid_scopes or (fail_first and n==20 and attempt==1):
                reply["rows"][0]["title"]="WRONG PREVIOUS TITLE"
            answer=json.dumps(reply,ensure_ascii=False)
            remote={"status":"completed","result_ready":True,
                    "chatgpt_send_confirmed":True,"assistant_reply_observed":True,
                    "job_id":state["job_id"],"room_id":state["room_id"],
                    "request_id":state["request_id"],"result_sha256":digest(answer)}
            state["status"]="completed"
            runner.save(path,state)
            return answer,remote
        return ensure,await_,sends

    def test_keyed_exact_map_uses_original_id_not_model(self):
        from hitel_scribd_supervisor import validate_keyed,keyed_prompt
        b=self.sample()
        a=self.response(b)
        a["rows"][0]["id"]="NOT_A_SOURCE_ID"
        result=validate_keyed(json.dumps(a,ensure_ascii=False),b)
        self.assertEqual([x["id"] for x in result],[x["문서 ID"] for x in b])
        self.assertNotIn(b[0]["문서 ID"],keyed_prompt(b))

    def test_wrong_title_or_swapped_key_rejected(self):
        from hitel_scribd_supervisor import validate_keyed, InvalidReply
        b=self.sample()
        a=self.response(b)
        a["rows"][13]["title"],a["rows"][14]["title"]=a["rows"][14]["title"],a["rows"][13]["title"]
        with self.assertRaisesRegex(InvalidReply,"KEY_OR_TITLE_MISMATCH"):
            validate_keyed(json.dumps(a,ensure_ascii=False),b)

    def test_terminal_bad_reply_retries_fresh_room_without_counting_bad(self):
        from hitel_scribd_supervisor import run_supervised
        b=self.sample()
        ensure,await_,sends=self.transport(b,fail_first=True)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            parsed,proof=run_supervised(root,b,ensure,await_,sleep=lambda _:None)
            self.assertEqual(len(parsed),20)
            self.assertEqual(len(proof),1)
            self.assertEqual(len(set(sends)),2)
            self.assertEqual(len(list(root.rglob("rejected-*.json"))),1)
            # Idempotent restart: verified checkpoint reuses reply, no send.
            parsed2,proof2=run_supervised(root,b,ensure,await_,sleep=lambda _:None)
            self.assertEqual(parsed2,parsed)
            self.assertEqual(proof2,proof)
            self.assertEqual(len(sends),2)

    def test_split_20_to_5_to_1_preserves_all_exact_ids(self):
        from hitel_scribd_supervisor import run_supervised
        b=self.sample()
        ensure,await_,sends=self.transport(b,invalid_scopes=(20,5))
        with tempfile.TemporaryDirectory() as d:
            parsed,proof=run_supervised(Path(d),b,ensure,await_,sleep=lambda _:None)
            self.assertEqual(len(parsed),20)
            self.assertEqual(len(proof),20)
            self.assertEqual([x["id"] for x in parsed],[x["문서 ID"] for x in b])
            self.assertEqual(len(sends),30)

    def test_single_rejection_is_not_a_success(self):
        from hitel_scribd_supervisor import run_supervised
        b=self.sample(1)
        ensure,await_,sends=self.transport(b,invalid_scopes=(1,))
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(RuntimeError,"SINGLE_ROW_RETRY_LIMIT"):
                run_supervised(Path(d),b,ensure,await_,sleep=lambda _:None)
            self.assertEqual(len(sends),3)
            self.assertFalse(list(Path(d).rglob("verified.json")))

    def test_lost_reply_does_not_allocate_a_new_request(self):
        from hitel_scribd_supervisor import run_supervised
        b=self.sample()
        ensure,await_,sends=self.transport(b)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(RuntimeError,"lost reply"):
                run_supervised(Path(d),b,ensure,
                               lambda p,s: (_ for _ in ()).throw(RuntimeError("lost reply")),
                               sleep=lambda _:None)
            parsed,proof=run_supervised(Path(d),b,ensure,await_,sleep=lambda _:None)
            self.assertEqual(len(parsed),20)
            self.assertEqual(len(sends),1)

    def test_read_backoff_does_not_repost(self):
        from hitel_scribd_supervisor import safe_read
        waits=[]
        errors=[urllib.error.HTTPError("https://example.invalid",429,"limited",{"Retry-After":"30"},None),
                urllib.error.URLError("temporarily offline"),"ok"]
        def read():
            value=errors.pop(0)
            if isinstance(value,Exception):
                raise value
            return value
        self.assertEqual(safe_read(read,sleep=waits.append),"ok")
        self.assertEqual(waits,[30,10])

    def test_legacy_bad_mapping_is_rejected_not_repaired(self):
        from hitel_scribd_supervisor import strict_legacy, InvalidReply
        b=self.sample()
        a=self.response(b)
        converted=[]
        for entry,source in zip(a["rows"],b):
            converted.append({"no":source["번호"],"id":source["문서 ID"],
                              **{k:v for k,v in entry.items() if k not in ("key","title")}})
        converted[13]["id"]=converted[14]["id"]
        converted[14]["id"]=converted[15]["id"]
        converted[15]["id"]=converted[14]["id"]
        with self.assertRaises(InvalidReply):
            strict_legacy(json.dumps({"rows":converted},ensure_ascii=False),b)



class Incident09134RecoveryTests(unittest.TestCase):
    def test_recover_exact_partial_only_when_request_absent_and_task_idle(self):
        rows=[{"번호":n,"문서 ID":str(400000000+n),"원문 제목":"sample"}
              for n in range(1,18110)]
        rows[9133]["문서 ID"]="408651836"
        verified={n:{} for n in range(1,9121)}
        prior={"first_missing":9121,"error_type":"UNCERTAIN_POST_READ_ONLY","infra_retries":5}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            parent=root/"supervisor"/"09121-09140"
            state={"request_id":runner.HELD_9134_REQUEST,"source_ids":[runner.HELD_9134_SOURCE],
                   "task_id":"scribd-18109","status":"prepared","submit_attempted":True}
            runner.save(parent/"09134-09134"/"attempt-1.json",state)
            for first,last in ((9121,9125),(9126,9130),(9131,9131),(9132,9132),(9133,9133)):
                ids=[{"no":n,"id":rows[n-1]["문서 ID"]} for n in range(first,last+1)]
                parsed=[{**item,"school":"대상외","grade":"해당없음","semester":"해당없음",
                         "subject":"해당없음","edition":"해당없음","download":"제외",
                         "reason":"교육과정 교재가 아닌 기타 문서"} for item in ids]
                runner.save(parent/f"{first:05d}-{last:05d}"/"verified.json",
                            {"source_ids":ids,"rows":parsed,"evidence":[{"job_id":"job_sample",
                             "room_id":"room_sample","request_id":"sample","result_sha256":"a"*64}]})
            idle={"task_id":"scribd-18109","queued_jobs_count":0,"worker_active_jobs_count":0,
                  "worker_live_jobs_count":0,"worker_recovery_required_count":0,
                  "worker_reset_required":False,"worker_connected":False,"generation":151}
            with patch.object(runner,"fetch_existing",return_value={"job_id":"job_found"}), \
                 patch.object(runner,"call") as call,patch.object(runner,"commit_supervised") as commit:
                self.assertFalse(runner.recover_09134_partial(rows,root,verified,prior))
                call.assert_not_called()
                commit.assert_not_called()
            with patch.object(runner,"fetch_existing",return_value=None), \
                 patch.object(runner,"call",return_value=(200,{**idle,"queued_jobs_count":1})), \
                 patch.object(runner,"commit_supervised") as commit:
                self.assertFalse(runner.recover_09134_partial(rows,root,verified,prior))
                commit.assert_not_called()
            with patch.object(runner,"fetch_existing",return_value=None), \
                 patch.object(runner,"call",return_value=(200,idle)), \
                 patch.object(runner,"commit_supervised") as commit, \
                 patch.object(runner,"isolated_chat_once") as post:
                self.assertTrue(runner.recover_09134_partial(rows,root,verified,prior))
                post.assert_not_called()
                commit.assert_called_once()
                args=commit.call_args.args
                self.assertEqual(args[2],"09121-09133")
                self.assertEqual([r["no"] for r in args[4]],list(range(9121,9134)))
                self.assertEqual(runner.held_numbers(rows,root),{9134})
                self.assertEqual(json.loads((parent/"09134-09134"/"attempt-1.json").read_text("utf-8")),state)
                verified.update({n:{} for n in range(9121,9134)})
                self.assertEqual(runner.next_eligible_batch(rows,verified,root)[0]["번호"],9135)


class TerminalUnknownWindowTests(unittest.TestCase):
    def test_quarantine_only_exact_terminal_scope_and_continue(self):
        rows=[{"번호":n,"문서 ID":str(n),"원문 제목":"sample"} for n in range(1,61)]
        batch=rows[20:40]
        ids=[{"no":x["번호"],"id":x["문서 ID"]} for x in batch]
        verified={n:{} for n in range(1,21)}
        st={"task_id":"scribd-18109","submit_attempted":True,"status":"unverified",
            "remote_error_code":"UPSTREAM_DELIVERY_UNKNOWN","job_id":"job_test",
            "room_id":"room_test","request_id":"original","active_request_id":"recovery",
            "source_ids":ids}
        remote={"job_id":"job_test","room_id":"room_test","request_id":"recovery",
                "status":"unknown","error_code":"UPSTREAM_DELIVERY_UNKNOWN","result_ready":False}
        task={"task_id":"scribd-18109","queued_jobs_count":0,"worker_active_jobs_count":0,
              "worker_live_jobs_count":0,"worker_recovery_required_count":0,
              "worker_reset_required":False,"generation":154}
        with tempfile.TemporaryDirectory() as d:
            out=Path(d); parent=out/"supervisor"/"00021-00040"
            runner.save(parent/"scope.json",{"source_ids":ids})
            runner.save(parent/"00021-00040"/"attempt-1.json",st)
            with patch.object(runner,"call",side_effect=[(200,remote),(200,{**task,"queued_jobs_count":1})]):
                self.assertFalse(runner.recover_terminal_unknown_window(rows,out,verified,batch,sleep=lambda _:None))
            with patch.object(runner,"call",side_effect=[(200,remote),(200,task),(200,remote),(200,task)]), \
                 patch.object(runner,"isolated_chat_once") as post:
                self.assertTrue(runner.recover_terminal_unknown_window(rows,out,verified,batch,sleep=lambda _:None))
                post.assert_not_called()
            self.assertEqual(runner.held_numbers(rows,out),set(range(21,41)))
            self.assertEqual(runner.next_eligible_batch(rows,verified,out)[0]["번호"],41)
            self.assertEqual(json.loads((parent/"00021-00040"/"attempt-1.json").read_text("utf-8")),st)

if __name__=="__main__":
    unittest.main()
