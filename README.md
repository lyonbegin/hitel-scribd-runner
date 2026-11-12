# Scribd public-preview review runner

This public repository contains a read-only public Scribd preview auditing workflow for a Windows self-hosted GitHub Actions runner.

- Queue: 814 unresolved public Scribd document IDs.
- First step: a three-document browser probe.
- Screenshots and status CSV are uploaded as a workflow artifact.
- The workflow does not download PDFs or try to bypass site challenges.
- Jobs run only on a push to `main` or manual workflow dispatch; no pull-request trigger.
- Do not commit browser profiles, login tokens, or personal data.
