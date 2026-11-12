# 03: YouTube Shorts

## Format
- **Shorts = vertical (9:16) or square, up to 3 minutes.** Uploads since 2024-10-15 that are ≤3:00 and square or taller are classified as Shorts. A 16:9 upload is long-form at any length.
- 1080×1920 is the recommended size.
- Music caveat: older rules treated over-1-minute videos from channels linked to music content owners as long-form. Content ID claims on Shorts with copyrighted music can still block or restrict them. Use cleared audio. *Verify the current music rules.*
- Since **2026-11-03**, the API's `thumbnails.set` supports **custom Shorts thumbnails** after processing completes, using the new `shortsAspectRatio` field.

## View counting changed on 2026-08-27 (matters for CPM)
- **Public view counts now start the moment a video begins to play**, autoplay included, the same for Shorts, long-form, and Live.
- Monetization (YPP) still uses **"engaged views"**: playback past the first frame, or a click to play.
- CPM campaigns that read *public* view counts now see higher counts than before. Expect campaigns to tighten fraud checks or move to engaged metrics. Log both where you can.

## Policies that decide whether the bot survives
| Policy | What it says | Risk for an automated clipper |
|---|---|---|
| **Reused content** (YPP) | Repurposed content without significant original value can't be monetized, **even with permission from the owner** | Affects YouTube's own ad revenue, not campaign CPM. Still a sign the clips look low-value. |
| **Inauthentic content** (renamed from "repetitious," 2025-07-15) | Mass-produced, templated, or repetitive content can't be monetized. AI use alone isn't a violation. | **High.** A bot posting dozens of near-identical clips is exactly the target. |
| **Spam, deceptive practices & scams** | Bans manipulating the platform, high-volume repetitive content, and **coordinated networks of channels** | **Channel termination.** Covers multi-channel farms. |
| **Circumvention** | When one channel is terminated, YouTube finds and terminates **related** channels | One ban can take out every channel tied to the operator. |
| Synthetic media disclosure | `status.containsSyntheticMedia` is settable on upload | Set it truthfully if you use generated voice or visuals. Plain cuts of real footage usually don't need it. |

Shorts that reuse content also get **less distribution**, even when they stay monetized.

**What makes a clip count as "original" in practice:** a new hook or framing, captions, commentary or a voiceover, context titles, curation across sources, and edits like zooms, B-roll, and cuts. A raw crop of a viral moment that 200 other clippers also posted is what the duplicate detectors are built to catch.

## Publishing via the YouTube Data API v3

**Endpoint:** `POST https://www.googleapis.com/upload/youtube/v3/videos` (`videos.insert`, resumable upload)

**Scopes:** `youtube.upload` (minimum), `youtube`, `youtube.force-ssl`, or `youtubepartner`. Use OAuth 2.0 as the channel owner.

| Item | Current state (verified on official docs 2026-11-12) |
|---|---|
| Quota | Since **2026-06-01**, `videos.insert` has **its own bucket**: **1 unit per call, 100 calls/day by default**. Other methods use the shared 10,000-unit bucket. The old "1,600 units per upload, about 6 uploads/day" figure is **out of date**. |
| Unverified projects | Since **2026-11-02**, uploads from **unverified API projects are no longer locked to private**, reversing the 2020 audit rule. A compliance audit is still recommended for long-term access and quota increases. |
| Default privacy | `public` if omitted. Some accounts default to private through creator settings. |
| Scheduling | `status.publishAt` (requires `privacyStatus=private` until publish) |
| Max file | 256 GB |
| Brand deals | Since **2026-07-07**, the `brandPartner` part (`channelId` or `channelHandle`) can be set on insert or update for creator-initiated brand-partner links. |
| Stats | `videos.batchGetStats` (added 2026-06-03): 1 unit/call in its own 10k/day bucket. Use it for tracking campaign views. |
| Also settable | title, description, tags, `categoryId`, `selfDeclaredMadeForKids`, `notifySubscribers`, `containsSyntheticMedia`, license, `recordingDate` |
| Errors to handle | `uploadLimitExceeded` (per-channel daily cap, separate from API quota), `quotaExceeded`, `forbiddenPrivacySetting`, `invalidPublishAt` |

**There's no Shorts flag:** a 9:16 file of 3:00 or less becomes a Short automatically. Adding `#Shorts` to the title or description is optional.

**YouTube ToS on downloading:** the ToS forbids downloading content except through YouTube-provided features. Pulling source footage with `yt-dlp` breaks the ToS even when the creator approved the clipping campaign. **Prefer campaign-supplied source files** (Drive or Dropbox links in the brief), creator-enabled downloads, or footage the creator sends directly.
