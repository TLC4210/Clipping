# 08: Niche and multi-account plan

Decided 2026-11-12. **Owner:** the user (a real person who holds every account). **Niches:** FaZe Clan streams, GTA, Minecraft, The Shawn Ryan Show. **Platforms:** YouTube Shorts and Instagram Reels, with multiple accounts.

## 1. Multiple accounts: what's allowed

| Layer | Rule | Source |
|---|---|---|
| **Content Rewards** | **One CR profile per person.** That profile **can link several social accounts, including several on the same platform**. Each social account can be linked to **only one** CR profile. All accounts must be **public**. | CR Help Center (link & verify accounts), CR FAQ, Terms §13.3 |
| **YouTube** | One Google login can own multiple channels (Brand Accounts). This is allowed **as long as the channels aren't a coordinated network posting duplicate or repetitive content** (spam policy). A ban on one can spread to related channels (circumvention policy). | YT spam & circumvention policies |
| **Instagram** | About **5 accounts per device** in the app (third-party figure, *verify*). Each account needs its own email or phone. Each must be a **professional** account for API publishing, with its own token. | Third-party guides; Meta Content Publishing docs |

### Account layout: one niche per account per platform

| # | Niche | YouTube channel | Instagram account |
|---|---|---|---|
| 1 | GTA | `<brand> GTA` | `<brand>.gta` |
| 2 | Minecraft | `<brand> Minecraft` | `<brand>.mc` |
| 3 | FaZe / streamer clips | `<brand> Stream Clips` | `<brand>.streams` |
| 4 | Shawn Ryan Show | `<brand> Podcast Clips` | `<brand>.pod` |

That's 8 accounts, all owned by the user and all linked to the user's single CR profile.

### Rules the pipeline must enforce
1. **A clip goes to exactly one account per platform.** The same edit can go to that niche's YT channel *and* its IG account, but never to two YT channels or two IG accounts. This is the pattern that gets networks banned.
2. **No cross-niche reposting.** Each account has its own content, so it reads as a real niche page.
3. **Per-account caps:** start at **≤3 posts/day/account** and keep posting times varied.
4. **Unique edits per account:** a different hook, captions style, and title template per account brand.
5. **Never name or brand an account as the official creator.** Don't use "FaZe Clan", "Shawn Ryan Show", "Rockstar", or "Minecraft" as the account name or logo. That's impersonation or trademark trouble, and CR and platform ToS ban it. Use your own brand, and add "fan clips / not affiliated" in the bio.
6. Separate OAuth tokens per account, stored in a secrets vault keyed by `account_id`.

## 2. Niche-by-niche assessment

### GTA: the highest priority, because of timing
- **GTA 6 launches 2026-11-19 (one week from now)** on PS5 and Xbox Series X|S. It's single-player only, with no PC version announced. The launch window will have the biggest gaming search and feed demand of the year.
- **Rights.** Rockstar lets fans upload gameplay footage. Its policy covers *non-commercial* fan use. Spoilers should be avoided, and **footage from leaked or pre-release copies gets taken down**. Monetized or brand-paid use is a gray zone, so ask Rockstar for big commercial use. (Rockstar's support page returned 503 during research. *Verify the wording.*)
- **Best footage source: the owner's own gameplay** (PS5/Xbox capture → upload to a folder the agent watches).
  - It's fully original, so it avoids the reused-content and aggregator penalties.
  - It needs no permission from other creators.
  - The agent can't play the game, so the human records and the agent does everything after that.
- Second source: clips of GTA streamers (GTA RP streams are classic clip material). This **needs the streamer's permission or a paid campaign** (see FaZe below).
- **YouTube rule (Sep 2026):** **graphic violence in the first 7 seconds makes a video ineligible for ads.** NPC-slaughter compilations can be fully demonetized. Some realistic gaming content has been age-restricted since Nov 2025.
  - So the hook in the first 7 seconds should be a funny or surprising moment, not gore.
  - This affects YouTube's own ads more than CR CPM, but age restrictions also cut reach.
- **Spoilers:** for the first 2–3 weeks, add a spoiler warning or avoid story beats. Rockstar asks for this, and spoiler clips get reported.

### Minecraft: the safest rights position
- **Mojang explicitly allows monetized Minecraft videos on YouTube.** You can't charge for access to Minecraft content or sell Minecraft items. The permission isn't a formal license and can be revoked. Minecraft music has its own guidance.
- **Best footage source: the owner's own gameplay**, as with GTA. Second: Minecraft streamers, **with permission**.
- An evergreen niche with a very large, young audience and high Shorts volume. It's competitive, so hooks and edits matter.

### FaZe Clan streams: permission required, and the roster is unstable
- **The roster churned:** the main creators (Adapt, Jason, Ronaldo, Lacy, Rage, Silky) announced exits on 2025-12-25.
  - An Apr 2026 "reboot" reportedly kept about 14 "core" members: Banks, Adapt, Apex, Jev, Kaysan, Nickmercs, Replays, Ronaldo, Rug, Scope, Swagg, Temperrr, YourRage, and Zooma. Sources differ, so *verify*.
  - Several ex-members started a separate group house, **CORE** (May 2026).
  - Recommendation: build the account around **specific streamers**, not the "FaZe" brand.
- **Rights:**
  - Stream VODs belong to the streamers. Without permission you'll get Content ID claims, DMCA takedowns, and strikes (3 strikes = channel terminated).
  - Downloading Twitch or Kick VODs with scrapers can break those sites' ToS.
- **Where the money is:** streamers often **pay their own clippers**. N3on reportedly paid $1.4M to 303 clippers in five weeks at about **$40–50 per 100k views**. Search CR's discover page for each streamer's name, and check the streamers' Discords for clip programs.
- **No FaZe or FaZe-member campaign was found** in web search or the open Whop Bounties (checked 2026-11-12). CR campaigns aren't exposed in the Bounties API, so check the CR app manually.

### The Shawn Ryan Show: permission required, plus content-policy care
- Long-form interviews (military, intelligence, true crime) are very clippable.
- **No public clipping program was found.** Clip channels already exist, at least one using "Official" in its name, and **Instagram swaps reposts for the original**. So raw reposts compete with the show's own clips and lose.
- **Rights:** this is the show's copyright, so expect Content ID. **Get written permission or a paid campaign before you monetize.** See the outreach template below.
- **Content-policy flags:**
  - Graphic war stories can hit YouTube's advertiser-friendly limits.
  - **Political clips need disclosure on CR, and CR bars them on TikTok and X** (Terms §12.11).
  - Conspiracy-adjacent claims can trip misinformation policies.
  - The agent's QA stage needs a "sensitive topic" classifier for this niche.

## 3. Expected earnings (CR market data, 719 campaigns, 2026-10-17)

| Category | Median rate / 1k views | Median views per approved clip | Implied gross per approved clip |
|---|---|---|---|
| Gaming | $1.25 | 2,938 | about $3.67 |
| Entertainment | $1.00 | 7,637 | about $7.64 |
| Personal brand | $1.00 | 7,775 | about $7.78 |

- Subtract the 10% CR fee. The median min/max payout per clip is $2 / $200.
- On platform split, CR campaigns accepting YouTube (415/710) are fewer than those accepting TikTok (645) or Instagram (561). Consider adding **TikTok** later, since it has the most campaigns.
- **Without a campaign or deal, a clip earns $0 in CPM.** The only other income is YouTube's Partner Program (YPP) Shorts revenue. That needs YPP eligibility, and reused clips of other people's content are usually ineligible. Own-gameplay GTA and Minecraft clips *can* qualify.

## 4. Priority order

1. **GTA: start this week.** The owner records GTA 6 gameplay from launch (11-19). The agent pipeline edits, captions, and posts to the GTA YT and IG accounts. Meanwhile, warm the accounts with GTA V and GTA 6 trailer/news content made from **own** commentary, not reposts.
2. **Minecraft:** the same own-gameplay pipeline. Add streamer clips once permissions or campaigns are secured.
3. **FaZe/streamers and Shawn Ryan:** the agent checks for CR campaigns daily (manually for now) and sends permission outreach. Turn on monetized clipping only once permission exists. Until then, keep these accounts to a low volume of permitted content, or hold off.

## 5. Permission outreach template (agent drafts, owner sends)

> **Subject:** Clipping partnership request for <Show/Streamer>
>
> Hi <name/team>,
>
> I run <brand>, a short-form clip page on YouTube Shorts and Instagram Reels focused on <niche>. I'd like permission to post edited, captioned clips from <show/streams>. Each clip will credit and link <official channel> in the caption and on screen, won't use your name or logo as our branding, and we'll remove anything on request.
>
> If you run a paid clipping program (Content Rewards, Vyro, or direct), I'd like to join. Otherwise, written permission to post clips would be enough.
>
> Thanks,
> <name> · <email> · <links to accounts>

Keep every permission email in `rights/` so you can prove it in a Content ID dispute.

## 6. Pipeline changes for these niches
- **Ingest:** add a "gameplay drop folder" (cloud storage) watched by the agent. Detect GTA vs Minecraft automatically from the frames.
- **Mine:** a gaming-specific highlight detector: kill-feed or event audio spikes, chat-style reactions, scene cuts. Podcasts keep the transcript-first approach.
- **Render:** gameplay layouts (facecam on top with gameplay below, or full-frame gameplay with a center-crop and zoom), plus spoiler-warning cards for GTA 6.
- **QA:**
  - No graphic violence in the first 7s (YT).
  - Sensitive-topic and political check (SRS).
  - No official logos in branding.
  - Permission record present for any third-party footage.
- **Routing:** `niche → (yt_channel_id, ig_user_id)`, with a hard rule of one clip per platform account.

## Open items
- [ ] Owner creates the 8 accounts (or chooses fewer to start: GTA and Minecraft first).
- [ ] Check the CR discover page for campaigns from FaZe members, GTA, Minecraft, or podcast creators.
- [ ] Send permission emails (SRS and target streamers).
- [ ] Confirm Rockstar's current video policy wording (the page was down during research).
- [ ] Capture setup for GTA 6 gameplay before 11-19.
