# Mohaned Reel Review Packs

Permanent read-only processor for [Mohaned Reel Reference Lab](https://mohaned-reel-reference-lab.blsi.chatgpt.site). The original Site remains the library and retains all owner-only write and admin controls.

## Automatic operation

The public GitHub Actions workflow polls the Site every 15 minutes (minutes 7, 22, 37 and 52). GitHub schedules are best effort and may be delayed. A manual run is available under Actions. Only standard `ubuntu-24.04` runners are used; the workflow refuses to run when this repository is private.

The processor checks video ETags and exact transcript content, downloads changed sources, and uses ffprobe, ffmpeg and ReportLab to build timestamped JPEG frames, `review.pdf`, `analysis.json` and `ai.txt`. Existing unchanged packs are reused. The two initial local packs were backfilled without regenerating their PDFs or frames.

No AI analysis runs, and review state is never updated. Untimed transcripts remain untimed: frame-to-speech alignment is explicitly unavailable. Captions and transcripts are preserved in each generated pack.

## Stable public URLs

For a Reference Lab UUID, use:

`https://tuffgroup.github.io/mohaned-reel-review-packs/references/{id}/review.pdf`

Replace `review.pdf` with `analysis.json`, `ai.txt` or a frame path listed in the JSON. [packs.json](https://tuffgroup.github.io/mohaned-reel-review-packs/packs.json) reports pack status. The Site derives these URLs without public write access or a GitHub credential.

## Free capacity and failure behavior

No card, billing account, cloud deployment, paid API, larger runner, Actions cache, uploaded Actions artifact, or Git LFS is required by this processor. GitHub Pages publishes `main:/docs`. The workflow uses only GitHub's ephemeral token. The account's existing $0 budgets with Stop usage enabled were retained.

Published files are capped at 850 MiB, below GitHub Pages' 1 GB limit. Source downloads are capped at 100 MiB; four changed records are processed per run. Failures are retried on later polls, with older failures ordered fairly. A generation failure preserves the previous published pack. Capacity exhaustion stops generation; it never purchases an upgrade. GitHub Pages has additional service and bandwidth limits. Pages publication/caching can add a delay after generation.

A factual daily polling status update provides health information and repository activity. If GitHub disables the workflow or changes its free-service policies, owner intervention may be required. There is no guarantee of uninterrupted service from a free host. Existing Scrape Creators ingestion uses the Site's separate, existing credits; this processor makes no Scrape Creators or AI API calls.

## Verification

On code-triggered/manual runs, `processor-tests.py` exercises real synthetic-video generation, unchanged skips, transcript/video changes, timing honesty and last-pack preservation. `browser-qa.py` checks the two backfilled Reel pages in a fresh anonymous Chromium context, including original video playback, JSON access and public asset links. If those sample records are intentionally removed, update the browser-test IDs. Scheduled processing does not depend on the sample-record test.

Inspect Actions logs and `packs.json` for failures. Never upload Site secrets, source configuration, or private records to this public repository.
