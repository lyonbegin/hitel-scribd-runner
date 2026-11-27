import unittest,json,os,hmac,hashlib
from unittest.mock import patch
import notifications as n
import engine as e
from test_engine import sample
class Tests(unittest.TestCase):
    def initial(self):
        p=sample()
        p["notifications"]={"channel":"webhook","heartbeat_seconds":30}
        s={"definition_sha":e.sha(e.definition(p)),"status":"ready","total":3,"results":[],"batches":{}}
        return p,s
    def test_event_lifecycle(self):
        p,s=self.initial()
        n.observe(p,s);n.observe(p,s)
        s["status"]="running";s["results"]=[{}];n.observe(p,s)
        s["status"]="complete";s["results"]=[{},{},{}];n.observe(p,s)
        got=[i["payload"]["event"] for i in s["notification_events"]]
        self.assertEqual(got,["project.started","batch.verified","batch.verified","project.completed"])
        self.assertEqual(s["notification_events"][-1]["payload"]["verified_ai_completed"],0)
        self.assertEqual(len({i["payload"]["event_id"] for i in s["notification_events"]}),4)
    def test_heartbeat(self):
        p,s=self.initial()
        with patch.object(n.time,"time",return_value=100):n.observe(p,s)
        with patch.object(n.time,"time",return_value=129):n.observe(p,s,True)
        with patch.object(n.time,"time",return_value=130):n.observe(p,s,True)
        with patch.object(n.time,"time",return_value=131):n.observe(p,s,True)
        self.assertEqual([i["payload"]["event"] for i in s["notification_events"]],["project.started","heartbeat"])
    def test_persist_before_send_and_no_replay(self):
        p,s=self.initial();n.observe(p,s);seen=[]
        with patch.object(n,"deliver",return_value="accepted") as d:
            n.flush(s,lambda:seen.append(s["notification_events"][0]["delivery"]))
            n.flush(s,lambda:None)
            self.assertEqual(d.call_count,1)
        self.assertEqual(seen,["attempted","accepted"])
    def test_webhook_signature(self):
        p,s=self.initial();n.observe(p,s)
        with patch.dict(os.environ,{"HITEL_EVENT_WEBHOOK_URL":"https://example.invalid/hook","HITEL_EVENT_WEBHOOK_SECRET":"test-only"}),patch.object(n,"post",return_value=204) as send:
            self.assertEqual(n.deliver(s["notification_events"][0]),"accepted")
        url,body,headers=send.call_args.args
        sig=hmac.new(b"test-only",headers["X-HITEL-Timestamp"].encode()+b"."+body,hashlib.sha256).hexdigest()
        self.assertEqual(headers["X-HITEL-Signature"],"sha256="+sig)
        self.assertNotIn(b"test-only",body)
    def test_no_url_in_project(self):
        p,s=self.initial();p["notifications"]["url"]="https://example.invalid"
        with self.assertRaises(ValueError):e.validate(p)
    def test_notification_setting_not_definition(self):
        p,s=self.initial();self.assertEqual(e.sha(e.definition(p)),e.sha(e.definition(sample())))
    def test_pr_allowlist(self):
        p,s=self.initial();p["notifications"]={"channel":"github_pr","pr_number":99}
        n.observe(p,s)
        with patch.dict(os.environ,{"GH_TOKEN":"mock-token","HITEL_NOTIFY_PR_ALLOWLIST":"1,2"}),patch.object(n,"post") as send:
            self.assertEqual(n.deliver(s["notification_events"][0]),"not_configured")
            send.assert_not_called()
if __name__=="__main__":unittest.main()
