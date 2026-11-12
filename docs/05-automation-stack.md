# 05: Automation stack

## End-to-end pipeline

```
 ┌────────────┐   ┌───────────┐   ┌────────────┐   ┌─────────────┐   ┌──────────┐
 │ 1 Campaign │──▶│ 2 Source  │──▶│ 3 Transcr. │──▶│ 4 Moment    │──▶│ 5 Edit   │
 │   intake   │   │   ingest  │   │  + signals │   │   mining    │   │  render  │
 └────────────┘   └───────────┘   └────────────┘   └─────────────┘   └────┬─────┘
                                                                          ▼
 ┌────────────┐   ┌───────────┐   ┌────────────┐   ┌─────────────┐   ┌──────────┐
 │10 Learn    │◀──│ 9 Track   │◀──│ 8 Submit   │◀──│ 7 Publish   │◀──│ 6 QA +   │
 │  (feedback)│   │   views $ │   │  (<30 min) │   │  (APIs)     │   │  approve │
 └────────────┘   └───────────┘   └────────────┘   └─────────────┘   └──────────┘
```

| # | Stage | What the agent does | Tools |
|---|---|---|---|
| 1 | **Campaign intake** | Pull open campaigns, then have an LLM parse each brief into a structured rule set: source links, required tags and handles, hook rules, length, banned items, disclosure text, allowed platforms and countries, CPM, cap, threshold. Skip anything needing livestream or human proof. | Whop Bounties API, CR dashboard (manual or export), Claude API for parsing |
| 2 | **Source ingest** | Download **campaign-supplied** files (Drive, Dropbox, direct). Normalize with ffmpeg. Hash them for dedupe. | `rclone`, `gdown`, ffmpeg. Avoid `yt-dlp` on YouTube unless the creator explicitly provided or allowed downloads (ToS). |
| 3 | **Transcribe + signals** | Word-level transcript, speaker diarization, audio energy/laughter peaks, scene cuts | **WhisperX** or **faster-whisper**, pyannote (diarization), PySceneDetect, librosa |
| 4 | **Moment mining** | Score candidate 15–60s windows with an LLM over the transcript plus signals: standalone? hook in the first 1–2s? payoff? on-brief? Output start/end, hook text, title. | Claude API, ideally with structured output. Optional: Higgsfield `virality_predictor` as a second opinion. |
| 5 | **Edit/render** | Cut, **9:16 reframe with face or active-speaker tracking** (split-screen for 2 people), **burned-in word-level captions**, **FTC disclosure overlay at 0s**, required handle/tag overlays, loudness to about −14 LUFS, safe-zone checks for the UI overlays | ffmpeg, MediaPipe/YOLOv8 face tracking, TalkNet/Columbia ASD, ASS subtitles, `ffmpeg-normalize` |
| 6 | **QA + approval** | Automatic checklist against the brief (length, tags, disclosure, no foreign watermarks, resolution, audio rights), plus a **human approve/reject** in phase 1 | LLM judge plus a Slack/Discord/web review queue |
| 7 | **Publish** | YouTube `videos.insert` (resumable) and IG Graph `media` → poll → `media_publish`. Captions and titles vary per platform. | Google API client, Graph API (see docs 03 and 04) |
| 8 | **Submit** | Submit the post URL to the campaign **within 30 min** (CR) or through `POST /bounty_submissions` (Whop Bounties) | Whop API (user token), CR UI |
| 9 | **Track** | Poll views, likes, and audience country, and reconcile against campaign earnings. Alert on fraud-looking patterns (views without engagement). | YouTube `videos.batchGetStats`, IG Insights, Whop `bounty_submissions_list` |
| 10 | **Learn** | Store each clip's features (hook type, length, topic, caption style, post time) and outcomes, then feed the winners back into the stage-4 prompt | Postgres/SQLite plus periodic analysis |

## Open-source building blocks (seen 2026-11; check licenses and maintenance before use)

| Repo | What it gives you |
|---|---|
| **ClipsAI** (`ClipsAI/clipsai`) | Python library: WhisperX transcription, clip finding, 16:9→9:16 resize. The best base library. |
| **FynCut** (`iyashjayesh/FynCut`) | Gemini moment detection, WhisperX, active-speaker detection (Columbia ASD) |
| **AutoClip** (`artbyjazi/autoclip`) | Local-first: LLM moment finding, speaker-tracked reframe, animated captions, Whisper + Ollama offline |
| **OpenShorts** (`mutonby/openshorts`) | MediaPipe face tracking with YOLOv8 fallback, stabilized crop, faster-whisper captions |
| **AI-Youtube-Shorts-Generator** (`Anil-matcha/…`) | ffmpeg + OpenCV face crop, OpenAI/Gemini highlight step |
| **opensource-clipping** (`NaufalRizqullah/…`) | Active-speaker detection with scene-aware switching, YOLOv8 option |
| **OpenClipper** (`GrepCut/OpenClipper`) | Tauri desktop app. Split view when two faces won't fit in one crop. |

Recommendation: build our own pipeline with **ClipsAI or OpenShorts as reference code**, plus **Claude for moment mining and brief compliance**. Moment selection and hook writing are what decide earnings, so that's the part to own.

## Paid clipping APIs (alternatives to building stages 3–5)

| Vendor | API | Notes (third-party-reported, *verify*) |
|---|---|---|
| OpusClip | Limited API on Pro ($29/mo) or Business | Sources conflict on which tier |
| Vizard | REST API from the Creator tier (about $14.50–29/mo) | |
| Klap | REST API (clips, captions, reframe, transcripts), about $0.32–0.48/op, plans from $14/mo | |

## Tools already connected to this workspace

These connectors show up in this Claude workspace and could cover parts of the pipeline. I listed them by name and haven't tested them end to end.

| Connector | Relevant tools | Possible use |
|---|---|---|
| **Whop** | `bounties_list`, `bounty-submissions_create/list`, `docs_search` | Stage 1 intake and stage 8 submission for Bounties. Already used read-only for this research. |
| **vidIQ** | `vidiq_video_transcript`, `vidiq_generate_clips`, `vidiq_generate_titles`, `vidiq_score_title`, `vidiq_video_upload`, `vidiq_instagram_publish_reel`, `vidiq_social_post_publish`, `vidiq_video_stats`, `vidiq_outliers`, `vidiq_trending_videos` | Transcripts, clip generation, title scoring, publishing to YT and IG, stats, trend discovery |
| **Higgsfield** | `reframe`, `upscale_video`, `virality_predictor`, `video_analysis_create` | 9:16 reframe, upscaling low-res sources, hook and retention scoring |

## Why build a custom pipeline when SaaS exists
1. **Brief compliance:** every campaign has different tags, hooks, and disclosures, and generic SaaS tools don't read briefs.
2. **The 30-minute submission window** needs publish and submit to be one atomic step.
3. **Originality:** we control the transformation layer (hooks, commentary, captions) that keeps accounts out of the aggregator and inauthentic buckets.
4. **The feedback loop:** our own performance data trains our own moment selector.
