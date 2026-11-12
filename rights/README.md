# Rights gate: where source footage may come from

**The YouTube Data API can't download videos.** It only returns metadata (search, stats, license). The media itself is fetched with `yt-dlp`. To keep the clip accounts safe from copyright strikes, the pipeline downloads a video **only if one of these is true:**

1. **The video is licensed Creative Commons Attribution (CC BY).** This is checked live with `videos.list` → `status.license == "creativeCommon"`. CC BY allows reuse, including commercial use, **with attribution**. Every clip burns in `Footage: <channel> (CC BY)` and puts the source link in the description or caption.
2. **The channel is listed in `permissions.yaml`** with written permission saved in `rights/evidence/`.
3. **The file was placed in `data/inbox/<niche>/`** by you: your own gameplay, or files a creator sent you.

Everything else is skipped, even if it's popular. Clipping random creators' videos without permission gets Content ID claims, strikes (3 = channel terminated), and Instagram aggregator demotion.

## Remaining caveats (read these)
- **YouTube ToS on downloading:** YouTube's Terms forbid downloading except through features YouTube provides, or with permission. The CC license covers *copyright*, not YouTube's ToS. The download machine's IP or cookies are the exposure, not your posting accounts, but it's still a ToS issue. The cleanest sources are (2) and (3).
- **Game publishers:**
  - Mojang allows monetized Minecraft videos.
  - Rockstar allows *non-commercial* fan footage, bans leaked or pre-release footage, and asks fans to avoid spoilers. The GTA niche config filters "leak/spoiler" titles and adds a spoiler-free card until a set date.
- **Mislabeled CC:** some uploaders mark re-uploads of other people's content as CC. The QA step rejects sources whose title or description says "reupload", "not my video", "credit to", etc., and caps clips per source.
- **Originality:** CC footage is still *reused content* for YouTube Partner Program purposes. Each clip adds a hook, captions, and framing. Add your own voiceover or commentary for the best results.
