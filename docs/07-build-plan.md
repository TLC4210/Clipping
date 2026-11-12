# 07: Build plan for the automated clipper

## Phase 0: Human setup (one-time, about 1 day)
- [ ] One human owner creates or uses **real** YouTube and Instagram (Professional: Creator or Business) accounts in a chosen niche.
- [ ] Create a Content Rewards account. Link and verify YT and IG under Profile → Linked Accounts. Set up payouts.
- [ ] Google Cloud project: enable YouTube Data API v3 and create an OAuth client (Desktop or Web). Grant `youtube.upload` + `youtube.readonly`. Store the refresh token.
- [ ] Meta app with Instagram Login: add the IG account as a tester/role and grant `instagram_business_basic` + `instagram_business_content_publish`. Store a long-lived token and refresh it before 60 days.
- [ ] Whop user token for Bounties API submission.
- [ ] A secrets store (`.env`, never committed).

## Phase 1: Human-in-the-loop MVP (about 1–2 weeks)
Goal: the agent produces ready-to-post clips, and a human approves each one.

1. `intake/`: Whop Bounties fetcher plus a **brief parser** (Claude, structured JSON output). Content Rewards briefs get pasted in manually for now.
2. `ingest/`: downloader for campaign-supplied links, ffmpeg normalize, sha256 dedupe.
3. `transcribe/`: faster-whisper or WhisperX, word timestamps, diarization.
4. `mine/`: Claude ranks candidate windows and returns `{start, end, hook_text, title, why}` × N.
5. `render/`: ffmpeg cut, face-tracked 9:16 crop (MediaPipe), word-level captions (ASS), disclosure card at 0s, handle overlay, loudness normalization.
6. `qa/`: checklist against the parsed brief, plus an LLM judge.
7. `review/`: simple web page or Discord bot with Approve/Reject buttons, showing the clip, brief, and QA result.
8. `publish/`: on approve, run YT `videos.insert` + IG Reels container → publish → get permalinks.
9. `submit/`: Whop `POST /bounty_submissions`, or a phone push to the human with the link and a CR submit deep-link before the 30-minute deadline.
10. `track/`: hourly stats poller into SQLite.

Volume cap: **≤3 clips/day/platform**. Watch reach and any warnings.

## Phase 2: Autonomy with guardrails (after about 50 clips of data)
- Auto-approve clips whose QA score is above a threshold. A human sees a daily digest and keeps veto rights.
- Feedback loop: retrain or re-prompt the moment-miner on winning features.
- IG **trial reels** for hook A/B tests.
- Multi-campaign scheduler that respects per-platform caps and posting-time windows.

## Phase 3: Scale (only on genuine accounts)
- More niches means **more humans who each own their own accounts** (each with a CR account) using the same pipeline as a tool. **Not** one person operating an account farm. See doc 06.
- Or pivot to **selling the pipeline** (B2B clipping-as-a-service for creators who own their content). That avoids the marketplace account rules entirely.

## Suggested stack
- Python 3.11+, ffmpeg 6+, faster-whisper/WhisperX (GPU optional), MediaPipe, OpenCV, pyannote
- Claude API for brief parsing, moment mining, titles, and QA judging
- `google-api-python-client` (YouTube), `requests` (Graph API, Whop)
- SQLite → Postgres. A job queue (RQ or Celery). A scheduler (cron, or Claude Code scheduled tasks).

## Open questions to resolve before Phase 1
1. Does Content Rewards have, or plan, a clipper submission API? (Ask support.)
2. Which niche or campaigns first? Filter for clear briefs, brand-supplied footage, CPM ≥ $1, and no proof-of-human requirement.
3. The live IG Reels API max duration and size for our account (test with the container status endpoint).
4. Who's the human account owner, and which country? Many Whop bounties are geo-restricted, and the Shane Gillis sample excluded the US.
