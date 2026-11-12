# 09: Clip allowlist (creators who allow or pay for clips)

Researched 2026-11-12. The machine-readable version the bot uses is [`rights/creators.yaml`](../rights/creators.yaml). Run `python -m clipper creators` to see what the bot will use today and why.

**How permission works:** a paid campaign is the permission, but **only for clippers who joined it**, and only for the footage and rules the campaign names. Every entry starts at `joined: false`. After you join on Content Rewards, set `joined: true` and copy any rules that unlock after joining into the entry.

## Active: our niches

| Creator | Niche | Campaign | Pay | Window / source | Key rules | Bot auto-posts? |
|---|---|---|---|---|---|---|
| **Lacy** | streams | Reach: $30k Lacy 30-day campaign | Pool share: $25k (TikTok/Reels/Shorts) + $5k (X). **1M approved views minimum** to get paid. | Any Lacy video or stream. Campaign ends about Nov 20–22. | Lacy as main focus, "Lacy" + #Lacy in caption, ≥50% audience in US/UK/CA/AU/NZ, no logos, submit within 30 min. AI-content rule is contradictory, so ask Reach. | Yes |
| **JasonTheWeen** | streams | Reach: $9k Jason pool | Pool share | Any. Rules locked until you join. | Copy rules in after joining | No (until rules are added) |
| **CORE** (Silky, Stable Ronaldo, Adapt, Marlon, Lacy, Jason) | streams | Reach: CORE pools, $20k + $5k (YouTube) | $20k pool: 2+ CORE members, 2M view minimum. $5k: CORE YouTube footage only, 750k minimum. | Nov 10–30 | #CORE, CORE/Silky named, **2+ members on screen** | Yes |
| **FaZe Flank Invitational** (FaZe / ZooMaa, CoD) | streams | ClippedIn: $8.5k FaZe tournament | $1 CPM, $10–$350/clip | Nov 10–12 event, on twitch.tv/faze, twitch.tv/zoomaa, and player POVs | FaZe Flank logo on screen the whole clip, @FaZeClan @ZooMaa @TheFlank #FaZeFlankInvitational, ≥60% US audience, keep public 3 months | No (needs logo overlay, and the sources are on Twitch) |
| **Lysium** (Benji Ramos, NoPixel V) | gta | Lysium on CR | $1.50 CPM, $150 max, about $654 left | NoPixel V streams | Context, no drama bait, Lysium handle shown, twitch.tv/Lysium in your bio. **Drafts need pre-approval**, and joining requires a sample video. | No (pre-approval) |
| **Fable SMP / HardcoreSMP** | minecraft | FableSMP on CR | $2 CPM, $4–$100, about $806 left | Brief locked until you join | Copy the brief in after joining | No (until rules are added) |

## Watch: GTA 6 week
| Creator | Why |
|---|---|
| **Kai Cenat** | Says he'll marathon GTA 6 to 100%. His last Reach pool ($10k) only allowed Oct 21–31 footage, and its rules page is now gone. Watch for a GTA 6 campaign. The entry is ready with `status: watch`. |
| **IShowSpeed** | Expedia campaign ($1 CPM, up to $500/clip, about $7.8k left), but **only the Nov 6 stream from 2:56:29**, and AI-generated videos are banned. Not GTA. |

**GTA 6 campaigns:** as of Nov 4–11, no streamer, brand, or Kick had announced a GTA 6 launch clipping campaign. Check Content Rewards daily around Nov 19.

## Blocked: the bot never clips these
| Creator | Why |
|---|---|
| **The Shawn Ryan Show** | No program or public permission found. You need written permission first. |
| **xQc** | No program, and he has threatened DMCA over clips of his own shows |
| **Stable Ronaldo, Adapt** | No program of their own. Usable only inside the CORE pool (2+ members). |
| CaseOh, Sidemen, Fanum | No program found |

## Minecraft: honest assessment
I couldn't find any big Minecraft creator (Philza, Tubbo, Hermitcraft, Dream SMP, etc.) with a public clipping program or a written "clips allowed" statement. Mojang allows Minecraft *gameplay* videos, but a creator's *footage* still belongs to them. For Minecraft, the realistic sources are:
1. Server campaigns like Fable SMP
2. CC BY videos (already built in)
3. Your own gameplay
4. Outreach: the doc 08 email template, with replies saved in `rights/permissions.yaml`

## Watchlist: programs without a public listing
- N3on (about $40–50 per 100k views)
- Adin Ross
- Clavicular (Kick-funded)
- The official Kick Clipping Program (via Kick Discord)
- Sketch and Jynxzi (past campaigns)

None of these are in our niches yet.

## Things to know before joining
- **Reach pool campaigns split a fixed pot by view share and have high minimums** (Lacy 1M views, CORE 2M, Kai 350k). New accounts will likely miss those minimums. **CPM campaigns** (Lysium, FableSMP, FaZe Flank, Speed) pay from the first qualifying clip.
- Most require **≥50–60% of your audience in English-speaking countries**. Check your accounts' analytics.
- **Submit within 30 minutes of posting.** After each post, the bot prints a `SUBMIT_NOW` line with the campaign link.
- Reach recommends a **dedicated account per streamer**. Our plan uses one "streams" account across Lacy, Jason, and CORE. That's allowed, but CR pools judge each clip on its own.

## Sources
- [Reach: Lacy rules](https://reachclipping.com/Lacy)
- [Clyper: Lacy](https://www.clyper.io/clipping-programs/lacy)
- [Lacy on X (2024)](https://x.com/LacyHimself/status/1758167310999671133)
- CR listings: [Lacy $25k](https://contentrewards.com/c/campaigns/4479e5e2-9a00-489e-8b0c-345834f37cc7), [Jason $9k](https://contentrewards.com/c/campaigns/0b178e3c-fbd3-4294-8ded-394e3da9c62f), [FaZe Flank](https://contentrewards.com/c/campaigns/200ea21b-be80-4db8-b552-8e32b148604e), [Lysium](https://contentrewards.com/c/campaigns/6d896f33-152f-42a9-92f4-662199228349), [HardcoreSMP](https://contentrewards.com/c/campaigns/5354eab8-c428-483f-9d34-09c8db7fc324), [Kai Cenat](https://contentrewards.com/c/campaigns/44a3ffcb-d4a1-492b-94a4-704919950246), [IShowSpeed](https://contentrewards.com/c/campaigns/afeca1a0-f44c-46ad-8194-09d62b56589e)
- Clyper: [streamers who pay clippers](https://www.clyper.io/clipping-programs), [Silky/CORE](https://www.clyper.io/clipping-programs/silky), [Kai Cenat](https://www.clyper.io/clipping-programs/kai-cenat), [IShowSpeed](https://www.clyper.io/clipping-programs/ishowspeed)
- [Content Rewards on X: Kai Cenat pool](https://x.com/contentrewards/status/2114411445991694569)
- [Storycut: GTA 6 clipping](https://www.storycut.com/blog/gta-6-clipping)
- [win.gg: Kick Clipping Program](https://win.gg/kick-clipping-program/)
- [Tubefilter: N3on's clippers](https://www.tubefilter.com/2026/04/29/n3on-spending-millions-stream-clippers-tiktok-kick/amp/)
- YouTube channel IDs were read from each creator's youtube.com/@handle page on 2026-11-12. `@Lysium` → "Lysium" still needs confirming as the same person as twitch.tv/Lysium.
