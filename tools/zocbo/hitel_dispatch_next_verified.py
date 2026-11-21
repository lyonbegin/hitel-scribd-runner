#!/usr/bin/env python3
"""GitHub Actions handoff for already-verified Scribd corpus windows.

The previous job MUST have verified and uploaded its checkpoint before this
script is called. A GitHub 500 is ambiguous: the dispatch may have been
accepted. Inspect the target workflow's actual runs before each retry.
Every dispatch for the same parent carries the same handoff token. Child
runs also reject duplicate handoffs before reading/sending any AI messages.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

WORKFLOW = "hitel-public-ai-corpus.yml"
PREFIX = "HITEL Scribd AI handoff "
API = "https://api.github.com"
MAX_POST_ATTEMPTS = 3
OBSERVATIONS_AFTER_500 = 10
OBSERVATION_INTERVAL = 4


def title_for(token: str) -> str:
    return PREFIX + token


def new_token(parent_run_id: str) -> str:
    if not parent_run_id.isdecimal():
        raise ValueError("INVALID_PARENT_GITHUB_RUN_ID")
    return "from-" + parent_run_id


class GithubClient:
    def __init__(self, repository: str, token: str):
        if repository.count("/") != 1 or not all(repository.split("/")):
            raise ValueError("INVALID_REPOSITORY")
        if not token:
            raise ValueError("MISSING_GITHUB_TOKEN")
        self.repository = repository
        self.token = token

    def request(self, method: str, path: str, payload: dict | None = None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            API + "/repos/" + self.repository + "/" + path,
            data=body, method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + self.token,
                "X-GitHub-Api-Version": "2022-11-28",
                **({"Content-Type": "application/json"} if body else {}),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as res:
                raw = res.read()
                return res.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            # Never print body, Authorization header or other account data.
            return exc.code, None


def find_handoff(client: GithubClient, token: str):
    """Return the actual next run ID, None for a healthy empty listing.

    An API error is raised (not treated as an empty list) to prevent an
    additional POST while whether the previous POST landed is unknown.
    """
    path = ("actions/workflows/" + WORKFLOW
            + "/runs?event=workflow_dispatch&per_page=100")
    status, data = client.request("GET", path)
    if status != 200 or not isinstance(data, dict):
        raise RuntimeError("HANDOFF_RUN_DISCOVERY_HTTP_" + str(status))
    for run in data.get("workflow_runs", []):
        if (run.get("display_title") == title_for(token)
                and run.get("event") == "workflow_dispatch"
                and run.get("head_branch") == "main"):
            return int(run["id"])
    return None


def observe(client: GithubClient, token: str, checks: int, sleep):
    for iteration in range(checks):
        found = find_handoff(client, token)
        if found is not None:
            return found
        if iteration < checks - 1:
            sleep(OBSERVATION_INTERVAL)
    return None


def handoff(client: GithubClient, token: str, sleep=time.sleep) -> tuple[str, int | None]:
    """Never POST again after a definitive 204, even if run visibility lags."""
    path = "actions/workflows/" + WORKFLOW + "/dispatches"
    payload = {"ref": "main", "inputs": {"mode": "full", "handoff_token": token}}
    for attempt in range(1, MAX_POST_ATTEMPTS + 1):
        # A rerun of the parent must not generate a duplicate child.
        found = observe(client, token, 2, sleep)
        if found is not None:
            return ("already_created", found)

        code, _ = client.request("POST", path, payload)
        print("HANDOFF_ATTEMPT", attempt, "HTTP", code, flush=True)

        if code == 204:
            found = observe(client, token, OBSERVATIONS_AFTER_500, sleep)
            if found is not None:
                return ("created", found)
            # Dispatch succeeded, even if GitHub's runs index is delayed.
            # Never POST again after HTTP 204.
            return ("accepted_not_yet_visible", None)

        if code not in (500, 502, 503, 504):
            raise RuntimeError("DISPATCH_NONRETRYABLE_HTTP_" + str(code))

        # 5xx can occur AFTER GitHub accepted the new run. Query the runs
        # repeatedly before considering another dispatch request.
        found = observe(client, token, OBSERVATIONS_AFTER_500, sleep)
        if found is not None:
            return ("created_after_5xx", found)
        if attempt < MAX_POST_ATTEMPTS:
            sleep(OBSERVATION_INTERVAL * attempt)

    raise RuntimeError("DISPATCH_RETRY_EXHAUSTED_NO_CHILD_RUN_OBSERVED")


def main() -> int:
    token = new_token(os.environ.get("GITHUB_RUN_ID", ""))
    client = GithubClient(os.environ.get("GITHUB_REPOSITORY", ""),
                          os.environ.get("GH_TOKEN", ""))
    status, run_id = handoff(client, token)
    print("NEXT_VERIFIED_ONLY_HANDOFF", status,
          "CHILD_RUN_ID", run_id if run_id is not None else "PENDING_INDEX",
          "PARENT_RUN_ID", os.environ["GITHUB_RUN_ID"], flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("Scribd verified-only continuation: " + status
                    + "; child " + str(run_id or "not yet indexed") + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError) as exc:
        print("HANDOFF_NOT_CONFIRMED", str(exc), flush=True)
        sys.exit(1)
