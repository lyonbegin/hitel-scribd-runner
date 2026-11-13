# Scribd screenshot inventory and acquisition decision — 2026-11-13

## Decision

**Do not run another broad screenshot crawl at this stage.** Existing screenshot PNGs and document metadata must be consolidated, quality-checked, and filtered for Korean middle/high-school textbooks and workbooks before any targeted recapture.

Each captured PNG is the browser's **visible viewport** (`page.screenshot(full_page=False)`), not the full PDF or all pages.

## Directly verified ZIP archives

| GitHub Actions run | Artifact ID | Parsed CSV distinct document IDs | PNG file count | ZIP CRC | Notes |
|---|---:|---:|---:|---|---|
| [43377032832](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43377032832) | 14018033564 | 1,063 | **1,062** | Passed | Statuses: 929 `preview_visible`, 97 `unexpected_redirect`, 29 `loaded_no_preview`, 7 `http_error`, 1 `error`. CSV parser confirms 1,063 rows; an earlier PowerShell line count of 1,066 was not a reliable record count. |
| [43415200492](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43415200492) | 14032469121 | 953 | **953** | Passed | Statuses: 693 `preview_visible`, 258 `loaded_no_preview`, 1 `unexpected_redirect`, 1 `http_error`. All 953 CSV document IDs have a matching PNG. |
| **Subtotal (these two verified ZIPs)** | | **2,016 records** | **2,015 PNGs** | Passed | These are not counts of full-document downloads. |

Older screenshot archives also exist, but unique image filenames across *all* older archives have not yet been fully reconciled. Do not sum older artifact counts as unique images without checking document IDs and duplicate files:
- [Run 43224551981](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43224551981): 17 batch artifacts, mixed successful/failed jobs.
- [Run 43344449923](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43344449923): 13 batch artifacts plus 3-document probe.
- The original source catalog was reported as 6,137 IDs. This ZIP audit is **not** an exhaustive de-duplicated audit of all 6,137.

## Latest 953-record title and image audit

| Browser result | Records | Metadata title or H1 present | Neither title nor H1 |
|---|---:|---:|---:|
| `preview_visible` | 693 | 650 | 43 |
| `loaded_no_preview` | 258 | 237 | 21 |
| `unexpected_redirect` | 1 | 1 | 0 |
| `http_error` | 1 | 1 | 0 |
| **Total** | **953** | **889** | **64** |

All 953 records contain a screenshot filepath and all 953 matching PNGs are present in the full artifact. The 64 missing-title records may still show their title visually in the screenshot.

### Important quality-control findings

1. The presence of `loaded_no_preview` in the log **does not prove that the screenshot is blank**. A sampled `loaded_no_preview` image showed visible document content despite the automated selector not matching.
2. A sampled image with no title/H1 field visibly showed a Korean workbook title (`1028854462`, "25마더텅윤사4"). This demonstrates that existing PNG review can recover some metadata without another browser visit.
3. Non-target documents also exist in the queue, including French neuroscience/Synapses and Azure Synapse tutorials. Filter target relevance before spending time on screenshot extraction.
4. A preview-visible status proves that a page/canvas element was detected, not that the entire document or every page was captured.
5. Title/H1 fields should be checked against page contents and existing screenshot evidence before treating them as authoritative.

## Required next phase — no new browser crawl

1. Merge all existing CSVs/logs and archived screenshot filenames by Scribd `document_id`; never add counts from multiple runs without de-duplication.
2. Re-evaluate all 260 latest non-preview statuses **against their existing PNGs** before deciding which have unreadable/missing content.
3. Inspect the 64 latest records missing both title and H1 using existing screenshot PNGs and URL/body data.
4. Discard irrelevant/non-Korean-workbook documents from the target catalogue; normalize publisher, book, level, grade, semester, subject, question/solution type, and canonical link.
5. Recapture **only** IDs where after visual assessment title/link evidence is genuinely unavailable or the image is corrupt/unreadable. Do not re-fetch 693 successful screenshots indiscriminately.
6. If the goal changes from book-title/link inventory to full question/page transcription, a viewport image is insufficient and a separate rights-compliant content strategy will be required.

## Evidence source

- [Most recent final checkpoint](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43415200492/artifacts/14033007845)
- [Most recent full screenshot archive](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43415200492/artifacts/14032469121)
- [Previous screenshot archive](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43377032832/artifacts/14018033564)
