# Clipper pipeline (GTA and Minecraft)

```
YouTube Data API ──► rights gate ──► yt-dlp ──┐
 (search CC-BY,       (CC BY or       download │
  verify license)      permission)             ├─► signals ─► Claude picks ─► render 9:16 ─► QA ─► approve ─► YouTube Shorts
data/inbox/<niche>/ (your own gameplay) ───────┘  (audio,     moments +      (hook, captions,           │          (videos.insert)
                                                   cuts,      writes hook/   credit, loudness)          └────────► Instagram Reels
                                                   captions)  title                                                (Graph API)
```

## What each step does

| Step | Module | Notes |
|---|---|---|
| Discover | `clipper/discover.py` | `search.list` with `videoLicense=creativeCommon`, then `videos.list` to re-verify the license, duration, and views. Filters out leaks, spoilers, and re-uploads. |
| Rights gate | `clipper/rights.py` | Allows **only** CC BY sources, channels listed in `rights/permissions.yaml`, or your inbox files. See `rights/README.md`. |
| Fetch | `clipper/fetch.py` | Re-checks the license live, then downloads with yt-dlp (≤1080p, plus YouTube's auto-captions as word timings). |
| Signals | `clipper/media.py` | Audio loudness peaks, scene cuts (ffmpeg `scdet`), and speech density |
| Pick | `clipper/highlights.py` | Builds candidate windows from the signals. **Claude (`claude-opus-5-5`)** looks at 3 frames from each window plus the transcript, picks the best ones, tightens the cuts, and writes the hook, title, and description. It drops GTA clips with gore in the first 7 seconds (YouTube's ad rule). With no API key, it falls back to a loudness heuristic. |
| Render | `clipper/render.py` | 1080×1920 30fps H.264/AAC. Blurred background with zoomed gameplay in the middle, hook text (top), word-by-word captions, a "Footage: X (CC BY)" credit, a GTA 6 "SPOILER-FREE" tag until 2026-12-10, and loudness at −14 LUFS. |
| QA | `clipper/qa.py` | Resolution, length, codecs, audio, size, attribution present, source link in the description, title rules |
| Publish | `publish_youtube.py`, `publish_instagram.py` | **Dry run unless `--live`.** Enforces one account per platform per clip (database constraint) and a daily cap per account. |

## Setup (on your own computer, not a cloud server)

YouTube blocks downloads from datacenter IPs with "Sign in to confirm you're not a bot". This happened when I tested from the cloud environment, so **run the fetch step from a home connection.** Don't feed yt-dlp the cookies of your clip accounts.

```bash
git clone <repo> && cd Clipping
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # needs ffmpeg 6+ on PATH
cp .env.example .env                     # add YOUTUBE_API_KEY and ANTHROPIC_API_KEY
cp config/accounts.example.yaml config/accounts.yaml
```

1. **YouTube API key (for discovery):** Google Cloud Console → create a project → enable "YouTube Data API v3" → Credentials → API key → put it in `.env`.
2. **YouTube upload (per channel):** in the same project, create an OAuth client ID (Desktop app) → download it as `secrets/google_client_secret.json`. In `config/accounts.yaml`, set `enabled: true` and `channel_id` for the niche, then run `python -m clipper auth-youtube --niche gta` and log in **as that channel**. Repeat for `minecraft`.
3. **Instagram (per account):** make the account Professional (Creator) → create a Meta app with the Instagram API (Instagram Login) → add the account as a tester → generate a long-lived token with `instagram_business_basic` + `instagram_business_content_publish` → save it to `secrets/ig_gta_token.txt` → set `ig_user_id` and `enabled: true`.
   - Meta must download the video from a **public URL**. Either sync `data/clips/<niche>/` to a bucket and set `public_base_url`, or switch to Facebook Login (`api_host: graph.facebook.com`) to use resumable upload.
4. **Claude API key** (`ANTHROPIC_API_KEY`) for moment picking and titles. It's optional, but without it the titles are generic.

## Daily use

```bash
python -m clipper run --niche gta --limit 2        # discover → fetch 2 sources → pick + render + QA
python -m clipper run --niche minecraft --limit 2
python -m clipper review                           # clips waiting for approval (paths to the mp4s)
python -m clipper approve 4 7 9                    # or: approve --all-passing --niche gta
python -m clipper publish --niche gta              # dry run: shows what would be posted
python -m clipper publish --niche gta --live       # uploads (YouTube privacy comes from accounts.yaml)
python -m clipper status
```

Your own gameplay goes in `data/inbox/gta/` or `data/inbox/minecraft/`. `run` picks it up automatically. This is the best source: fully original and no rights questions.

When you're ready for full automation, `run --auto-approve --publish --live` does everything. Keep YouTube `privacy: private` for the first batch, then switch it to `public`. Schedule it with cron, for example twice a day:
```
15 10,18 * * *  cd ~/Clipping && .venv/bin/python -m clipper run --niche gta --limit 2 --auto-approve --publish --live
```

## Limits and safety rails built in
- No source without CC BY, written permission, or your own file.
- ≤3 clips per source, spaced ≥60s apart. ≤3 posts/day/account (`config/niches.yaml`).
- A clip can't go to two YouTube accounts or two Instagram accounts.
- YouTube upload quota: 100 uploads/day per Google Cloud project. Instagram: 100 posts/24h per account.

## Tests
`python -m pytest -q`. These tests run on synthetic video with no network or keys needed. They cover the render, rights gate, discovery parsing, captions, the database rule, and the exact Claude request format.

## Not built yet
- Stats tracking (`publish_youtube.stats` exists, but nothing schedules it yet)
- A web review page (review is the CLI for now)
- AI voiceover or commentary layer (the biggest originality boost)
