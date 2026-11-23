#!/usr/bin/env python3
"""Run the actual manual workflow's preflight Python on synthetic local data.

Does not call GitHub, Railway, Web2API, Chrome or ChatGPT.
"""
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / "workflows" / "hitel-public-ai-corpus.yml"
OLD_JOB = "job_769d8fbcaf034b8ebf5ca4e8d9ef3ce6"
OLD_REQUEST = "scribd18109-05001-05020-f0d6a6c13403b04fa32cf145c2ddc686"
OLD_ROOM = "room_85204c97cf5f4b6bb610e16776f27592"


def actual_preflight_script():
    document = WORKFLOW.read_text("utf-8")
    start = "      - name: Validate preserved checkpoint and exact approved smoke window\n"
    end = "      - name: Resume preserved AI answer or submit one signed scribd-18109 isolated HTTP batch\n"
    assert document.count(start) == document.count(end) == 1
    section = document.split(start, 1)[1].split(end, 1)[0]
    heredoc = "        run: |\n          python3 - <<'PY'\n"
    assert section.count(heredoc) == 1
    lines = section.split(heredoc, 1)[1].split("\n          PY", 1)[0].splitlines()
    assert lines and all(line.startswith("          ") for line in lines)
    script = "\n".join(line[10:] for line in lines) + "\n"
    compile(script, "<exact-workflow-preflight>", "exec")
    return script


class SmokeCheckpointGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = actual_preflight_script()

    def check_case(self, count, mode, state_mode="correct", ok=True):
        with tempfile.TemporaryDirectory(prefix="scribd-guard-") as tmp:
            root = Path(tmp)
            with (root / "Raw_Documents_18109.csv").open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["문서 ID"])
                writer.writeheader()
                writer.writerows({"문서 ID": f"doc{i:05d}"} for i in range(1, 18110))
            out = root / "hitel-ai-batches"
            (out / "completed").mkdir(parents=True)
            (out / "http").mkdir()
            verified = [{"no": n, "id": f"doc{n:05d}"} for n in range(1, count + 1)]
            (out / "completed" / "synthetic.json").write_text(
                json.dumps({"rows": verified}), encoding="utf-8")
            original = {
                "task_id": "scribd-18109",
                "key": "05001-05020",
                "job_id": OLD_JOB,
                "request_id": OLD_REQUEST,
                "room_id": OLD_ROOM,
                "source_ids": [
                    {"no": n, "id": f"doc{n:05d}"} for n in range(5001, 5021)
                ],
            }
            if state_mode != "missing":
                if state_mode == "wrong_job":
                    original["job_id"] = "job_unrelated"
                elif state_mode == "wrong_request":
                    original["request_id"] = "scribd18109-wrong"
                elif state_mode == "wrong_room":
                    original["room_id"] = "room_other"
                elif state_mode == "wrong_source":
                    original["source_ids"][0]["id"] = "not-original"
                elif state_mode == "wrong_task":
                    original["task_id"] = "stock-tv"
                (out / "http" / "05001-05020.json").write_text(
                    json.dumps(original), encoding="utf-8")
            output = root / "github-output.txt"
            env = dict(os.environ, HITEL_SCRIBD_RUN_MODE=mode, GITHUB_OUTPUT=str(output))
            run = subprocess.run(
                [sys.executable, "-c", self.script],
                cwd=root, env=env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
            if ok:
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                self.assertIn(f"verified={count}", output.read_text("utf-8"))
            else:
                self.assertNotEqual(run.returncode, 0, run.stdout + run.stderr)
                self.assertFalse(output.exists(), "Rejected gate wrote a success receipt")

    def test_exact_5000_with_exact_prior_job_is_accepted(self):
        self.check_case(5000, "smoke")

    def test_missing_prior_attempt_is_rejected_before_send(self):
        self.check_case(5000, "smoke", "missing", False)

    def test_mismatched_job_request_room_source_and_task_are_denied(self):
        for bad in ("wrong_job", "wrong_request", "wrong_room",
                    "wrong_source", "wrong_task"):
            with self.subTest(bad=bad):
                self.check_case(5000, "smoke", bad, False)

    def test_any_wrong_checkpoint_size_is_denied_in_smoke(self):
        for count in (4999, 5001, 5020):
            with self.subTest(count=count):
                self.check_case(count, "smoke", ok=False)

    def test_full_refuses_unverified_5020(self):
        self.check_case(5000, "full", ok=False)

    def test_full_accepts_verified_5020(self):
        self.check_case(5020, "full")

    def test_unknown_mode_fails_closed(self):
        self.check_case(5000, "other", ok=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
