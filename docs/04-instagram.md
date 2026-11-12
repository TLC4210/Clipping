# 04: Instagram Reels

## Originality and aggregator rules (the biggest risk on IG)
- **2024 (Reels):** when Instagram finds identical content, it **replaces the repost with the original** in recommendations and labels the repost with the original creator.
- **Aggregator penalty:** accounts that post **unoriginal content 10+ times in the past 30 days** get **no recommendations at all** (Explore, Reels tab, suggested posts). Followers still see their posts.
- **2026-04-30 expansion:** the same rules now cover **photos and carousels**, not just Reels (TechCrunch, Engadget, PetaPixel).
- Unverified third-party claims you'll see online, such as a "duplicate hash database" or a "one-third" threshold, aren't confirmed by Meta.

**Implication:** an IG clipper account must be **mostly transformative**: new edit, captions, framing, and commentary. A bot that mirrors the same raw clip other clippers post will be classed as an aggregator within weeks. Content Rewards also **forbids Instagram Collab** posting unless the brand allows it.

## Format
- 9:16, 1080×1920 recommended. MP4 or MOV, H.264 (or HEVC) video, AAC audio (48 kHz max, mono or stereo), 23–60 fps.
- Max length and file size through the API: third-party sources conflict (90s vs 3 min vs 15 min; 100 MB–4 GB). *Verify against Meta's Reels spec* and test with the container status endpoint. Keep clips 15–90s anyway, since that's where clipping campaigns sit.

## Publishing via the Instagram Graph API (Content Publishing)

### Requirements
- An **Instagram professional account** (Business or Creator).
- One of three login setups:

| Setup | Permissions | Host |
|---|---|---|
| **Instagram Login** (no FB Page needed) | `instagram_business_basic`, `instagram_business_content_publish` | `graph.instagram.com` |
| Facebook Login | `instagram_basic`, `instagram_content_publish`, `pages_read_engagement` (+ `ads_management`/`ads_read` if Business Manager role) | `graph.facebook.com`, `rupload.facebook.com` |
| Unified / Business system user | `instagram_basic`, `instagram_content_publish` | `graph.facebook.com` |

- A Meta app with Standard or Advanced access. **App Review** is needed to publish for accounts that aren't app roles. For your own accounts, adding them as app testers or roles avoids review.
- Pages that require Page Publishing Authorization (PPA) must complete it first.

### Flow
1. `POST /<IG_ID>/media` with `media_type=REELS`, `video_url=<public URL>` (Meta fetches it), `caption`, and optional `share_to_feed`, `cover_url`, `thumb_offset`, `trial_params`.
   - Or use `upload_type=resumable`, then `POST https://rupload.facebook.com/ig-api-upload/<ver>/<container_id>` with local-file bytes.
2. Poll `GET /<container_id>?fields=status_code` until `FINISHED`. Other statuses are `IN_PROGRESS`, `ERROR`, `EXPIRED` (24h), and `PUBLISHED`. Poll about once a minute for at most 5 minutes.
3. `POST /<IG_ID>/media_publish?creation_id=<container_id>` returns the media ID, so you get the permalink right away for the Content Rewards 30-minute submission.

### Limits
- **100 API-published posts per account per rolling 24h.** The carousel section of the same page says 50, so read the live value from `GET /<IG_ID>/content_publishing_limit`.
- No filters, no shopping tags. **There's no access to Instagram's in-app music library through the API**, so audio must be baked into the file and cleared.
- **Trial reels** (shown to non-followers first) can be published via `trial_params.graduation_strategy` = `MANUAL` or `SS_PERFORMANCE`. This is useful for A/B testing hooks without hurting the main grid.

### Insights
Per-media insights (plays/views, reach, saves, shares) through the Insights endpoints. You need these for proof-of-performance and fraud self-checks (an audience-country mismatch gets clips rejected on CR).

## Automation ToS note
Meta's terms ban unauthorized automated access (scraping, unofficial private-API posting tools). **Official Graph API publishing is the sanctioned path.** Avoid unofficial "instagrapi"-style libraries: they lead to account locks.
