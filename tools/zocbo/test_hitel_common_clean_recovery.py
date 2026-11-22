import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import hitel_scribd_http_continue as m

class CleanRecovery(unittest.TestCase):
    def test_pending_and_fresh_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"state.json"
            state={"task_id":"scribd-18109","key":"04841-04860","request_id":"original",
                   "room_id":"room_old","job_id":"job_old"}
            job={"request_id":"original","room_id":"room_old","job_id":"job_old",
                 "status":"unknown","error_code":"WORKER_CONNECTION_LOST","result_ready":False}
            with patch.object(m,"isolated_chat_once",side_effect=[
                (202,{"accepted":False,"pending":True,"task_id":"scribd-18109","previous_job_id":"job_old"}),
                (202,{"accepted":True,"task_id":"scribd-18109","job_id":"job_new",
                      "room_id":"room_new","request_id":"hitel-clean-scribd-18109-test"})]) as post:
                self.assertTrue(m.recover_common_worker(path,state,job))
                self.assertEqual(state["job_id"],"job_old")
                self.assertTrue(m.recover_common_worker(path,state,job))
                self.assertEqual(state["job_id"],"job_new")
                self.assertEqual(state["request_id"],"original")
                self.assertEqual(state["key"],"04841-04860")
                self.assertEqual(post.call_args_list[0].kwargs,post.call_args_list[1].kwargs)
    def test_wrong_scope_and_rate_limit_not_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            state={"task_id":"scribd-18109","key":"04841-04860","request_id":"original",
                   "room_id":"room_old","job_id":"job_old"}
            job={"request_id":"original","room_id":"room_old","job_id":"job_old",
                 "status":"unknown","error_code":"WORKER_CONNECTION_LOST","result_ready":False}
            with patch.object(m,"isolated_chat_once") as post:
                for change in ({"room_id":"wrong"},{"error_code":"UPSTREAM_RATE_LIMITED"},
                               {"status":"completed"},{"result_ready":True}):
                    self.assertFalse(m.recover_common_worker(Path(folder)/"state.json",state,{**job,**change}))
                post.assert_not_called()

if __name__=="__main__":
    unittest.main()
