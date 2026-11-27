import unittest,json,hashlib
from unittest.mock import patch
import engine as e
def sample(provider="mock"):
    return {"project_id":"demo-test","task_id":"new-test-task","command":"start","provider":provider,"batch_size":2,"prompt":"Classify items","fields":{"category":"string"},"records":[{"record_id":str(i),"text":"sample"} for i in range(3)]}
def state(p):return {"definition_sha":e.sha(e.definition(p)),"results":[],"batches":{}}
class Tests(unittest.TestCase):
    def test_two_batches_and_resume(self):
        p=e.validate(sample());s=state(p)
        self.assertEqual(e.batch(p,s,lambda:None),"running")
        s=json.loads(e.canon(s))
        self.assertEqual(e.batch(p,s,lambda:None),"complete")
        self.assertEqual([x["record_id"] for x in s["results"]],["0","1","2"])
        self.assertEqual(e.batch(p,s,lambda:None),"complete")
    def test_duplicate_id(self):
        p=sample();p["records"].append(p["records"][0])
        with self.assertRaises(ValueError):e.validate(p)
    def test_bad_reply(self):
        p=sample()
        with self.assertRaises(ValueError):e.check('{"rows":[{"key":"A02","category":"wrong"}]}',p["records"][:1],p["fields"])
    def test_lost_post_never_resend(self):
        p=sample("hitel");s=state(p);commits=[]
        with patch.object(e,"get",return_value=None),patch.object(e,"submit",side_effect=TimeoutError) as send:
            with self.assertRaises(TimeoutError):e.batch(p,s,lambda:commits.append(e.canon(s)))
            self.assertTrue(json.loads(commits[0])["batches"])
            with self.assertRaises(e.Blocked):e.batch(p,s,lambda:None)
            self.assertEqual(send.call_count,1)
    def test_hash(self):
        r={"result_text":"abc","result_length_bytes":3,"result_sha256":hashlib.sha256(b"abc").hexdigest()}
        self.assertEqual(e.result("job_test",r),"abc")
        r["result_sha256"]="0"*64
        with self.assertRaises(e.Blocked):e.result("job_test",r)
    def test_explicit_pilot_live_approval_is_scoped(self):
        p=sample("hitel")
        with patch.dict(e.os.environ,{"HITEL_ALLOW_LIVE":""}):
            self.assertFalse(e.live_allowed(p))
            p.update(project_id="stocktv-cases-20261127-0001-p01-v2",task_id="stocktv-universal-20261127")
            self.assertTrue(e.live_allowed(p))
            p["command"]="pause"
            self.assertFalse(e.live_allowed(p))
            p["command"]="start";p["task_id"]="other-task"
            self.assertFalse(e.live_allowed(p))
    def test_closed_task(self):
        p=sample("hitel");p["task_id"]="scribd-18109"
        with self.assertRaises(ValueError):e.validate(p)
    def test_pause_does_not_change_definition(self):
        p=sample();h=e.sha(e.definition(p));p["command"]="pause"
        self.assertEqual(h,e.sha(e.definition(p)))
if __name__=="__main__":unittest.main()
