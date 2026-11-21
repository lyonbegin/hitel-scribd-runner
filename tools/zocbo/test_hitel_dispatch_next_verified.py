#!/usr/bin/env python3
"""No-network, no-dispatch regression for the verified Scribd handoff."""
from __future__ import annotations
import unittest
from hitel_dispatch_next_verified import (
    PREFIX, GithubClient, handoff, new_token, title_for)


class Fake:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
    def request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        return next(self.responses)


def run_data(token, id=45):
    return (200, {"workflow_runs": [{
        "id": id, "event": "workflow_dispatch", "head_branch": "main",
        "display_title": PREFIX + token
    }]})


def empty():
    return (200, {"workflow_runs": []})


def noop(_):
    pass


class DispatchSafety(unittest.TestCase):
    def setUp(self):
        self.token = new_token("44862714679")
    def test_token_is_stable(self):
        self.assertEqual(self.token, "from-44862714679")
        self.assertEqual(title_for(self.token), PREFIX + self.token)
        with self.assertRaises(ValueError):
            new_token("bad")
    def test_known_child_prevents_post(self):
        api = Fake([run_data(self.token)])
        result = handoff(api, self.token, sleep=noop)
        self.assertEqual(result, ("already_created", 45))
        self.assertEqual([x[0] for x in api.calls], ["GET"])
    def test_http_500_may_have_already_created_child(self):
        api = Fake([empty(), empty(), (500, None), run_data(self.token)])
        self.assertEqual(handoff(api, self.token, sleep=noop),
                         ("created_after_5xx", 45))
        self.assertEqual(sum(x[0] == "POST" for x in api.calls), 1)
    def test_http_500_not_created_then_retry_once(self):
        api = Fake([empty(), empty(), (500, None)]
                   + [empty()] * 10
                   + [empty(), empty(), (204, None), run_data(self.token, 99)])
        self.assertEqual(handoff(api, self.token, sleep=noop), ("created", 99))
        self.assertEqual(sum(x[0] == "POST" for x in api.calls), 2)
        posts = [x for x in api.calls if x[0] == "POST"]
        self.assertEqual(posts[0][2], posts[1][2])
        self.assertEqual(posts[0][2]["inputs"]["handoff_token"], self.token)
    def test_204_accepted_but_not_indexed_never_post_again(self):
        api = Fake([empty(), empty(), (204, None)] + [empty()] * 10)
        self.assertEqual(handoff(api, self.token, sleep=noop),
                         ("accepted_not_yet_visible", None))
        self.assertEqual(sum(x[0] == "POST" for x in api.calls), 1)
    def test_failed_discovery_never_posts(self):
        api = Fake([(503, None)])
        with self.assertRaisesRegex(RuntimeError, "DISCOVERY_HTTP_503"):
            handoff(api, self.token, sleep=noop)
        self.assertEqual(sum(x[0] == "POST" for x in api.calls), 0)
    def test_http_500_then_run_discovery_failure_never_reposts(self):
        api = Fake([empty(), empty(), (500, None), (500, None)])
        with self.assertRaisesRegex(RuntimeError, "DISCOVERY_HTTP_500"):
            handoff(api, self.token, sleep=noop)
        self.assertEqual(sum(x[0] == "POST" for x in api.calls), 1)
    def test_http_403_fails_without_retry(self):
        api = Fake([empty(), empty(), (403, None)])
        with self.assertRaisesRegex(RuntimeError, "NONRETRYABLE_HTTP_403"):
            handoff(api, self.token, sleep=noop)
        self.assertEqual(sum(x[0] == "POST" for x in api.calls), 1)
    def test_three_ambiguous_failures_are_bounded(self):
        api = Fake(([empty(), empty(), (500, None)] + [empty()] * 10) * 3)
        with self.assertRaisesRegex(RuntimeError, "RETRY_EXHAUSTED"):
            handoff(api, self.token, sleep=noop)
        self.assertEqual(sum(x[0] == "POST" for x in api.calls), 3)
    def test_other_run_titles_do_not_count(self):
        api=Fake([(200, {"workflow_runs": [{
            "id": 123,"display_title":PREFIX+"from-OTHER",
            "head_branch":"main","event":"workflow_dispatch"
        }]}) for _ in range(2)]
                 + [(204,None), run_data(self.token)])
        self.assertEqual(handoff(api,self.token,sleep=noop),("created",45))


if __name__ == "__main__":
    unittest.main()
