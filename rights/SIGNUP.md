# How to sign up for the clip campaigns

Checked 2026-11-13. Every campaign in `creators.yaml` runs through **Content Rewards** (contentrewards.com, run by Whop). One account covers all of them.

## One-time setup (about 15 minutes, on your phone or PC)

1. **Make an account** at https://contentrewards.com and press *Create Account*. Signing in with Google works.
2. **Connect the channels you'll post from:** Settings → Connected accounts → Connect account → YouTube. Sign in and pick the **channel** (Clipped Live, GTA Moments Daily, Blocky Moments), keeping every box ticked. Repeat for each channel.
   - Accounts you linked in Whop **don't count**. They have to be connected in Content Rewards itself.
   - Instagram only connects if it's a **Business** account (Settings → Account type and tools → Switch to professional → Business).
3. **Payouts:** earnings go to your Content Rewards balance, then to your Whop balance, then out to your bank, PayPal or a wallet. The minimum is $1. Content Rewards takes a creator fee of about 10% on most campaigns.

## Then, for each campaign

Open the link and press **Join Campaign**. Open campaigns let you in straight away. Some ask questions first or need you to send a sample. The full rules and reference files only show **after you join**, so copy them into `creators.yaml`, then add the creator's key to `rights/joined.yaml`.

| Creator | Channel | Status | Join | Notes |
|---|---|---|---|---|
| Lacy ($25k + $5k for X) | Clipped Live | Open, ends about Nov 22 | [Shorts/Reels/TikTok](https://contentrewards.com/c/campaigns/4479e5e2-9a00-489e-8b0c-345834f37cc7), [X](https://contentrewards.com/c/campaigns/20b7c977-8d0c-4bd0-b9b0-2db9200f405b) | Pool needs 1M approved views before anything pays. Rules at reachclipping.com/Lacy |
| JasonTheWeen ($9k pool) | Clipped Live | Open | [Join](https://contentrewards.com/c/campaigns/0b178e3c-fbd3-4294-8ded-394e3da9c62f) | Rules hidden until you join |
| CORE ($20k + $5k YouTube) | Clipped Live | Open, ends Nov 30 | [Reach on Whop](https://whop.com/reachclipping/products/clipping-campaigns-1f/), [Reach Discord](https://discord.com/invite/reachclipping) | 2+ CORE members on screen; #CORE plus a hashtag per member; 2M-view minimum. One clip can also count for Lacy or Jason |
| FaZe Flank Invitational ($1/1K, max $350) | Clipped Live | Open, but the event ended Nov 12 | [Join](https://contentrewards.com/c/campaigns/200ea21b-be80-4db8-b552-8e32b148604e) | Needs the logo overlay and Twitch footage; the bot can't do either yet |
| Lysium / Benji Ramos ($1.50/1K) | GTA Moments Daily | Open | [Join](https://contentrewards.com/c/campaigns/6d896f33-152f-42a9-92f4-662199228349) | Needs a sample video to join; every draft needs approval first |
| HardcoreSMP / Fable SMP ($2/1K) | Blocky Moments | Open | [Join](https://contentrewards.com/c/campaigns/5354eab8-c428-483f-9d34-09c8db7fc324) | Brief is a Google Doc, unlocked after joining |
| IShowSpeed x Expedia ($1/1K) | Clipped Live | Open | [Join](https://contentrewards.com/c/campaigns/afeca1a0-f44c-46ad-8194-09d62b56589e) | Only the Nov 6 stream from 2:56:29; account must be in a streamer or travel niche |
| Kai Cenat | — | **Closed** (page no longer loads) | — | Watch for a GTA 6 campaign |
| *New:* GTA 6 x "Tokyo Girl" ($0.70/1K) | GTA Moments Daily | Open | [Join](https://contentrewards.com/c/campaigns/40046522-56d9-45ad-9198-faea8eca90c6) | Music promo: GTA 6-themed clips set to the song. The bot would need to add the song, and the GTA footage still needs its own rights |

## Rules that apply to every campaign

- **Submit within 30 minutes of posting.** Paste the live link on the campaign's *Submit clip* button. After 30 minutes it's refused. Nothing can submit for you, so post when you can act on it.
- **Posts must be public.** The channels are currently set to `privacy: private`; switch a channel to `public` before any run you plan to submit.
- **Audience:** Reach campaigns need at least 50% of your audience in the US, Canada, UK, Australia or New Zealand, and the account's niche has to match. Reach suggests a dedicated page per creator or crew (for example "COREClips") if you don't have a relevant page with 100+ followers.
- **No AI-generated content on Reach.** It's one strike and you're banned from every Reach campaign. The bot cuts real footage and adds plain captions, which should be fine. But no AI voices or AI visuals, and ask in the Reach Discord if you're unsure.
- No logos (unless the campaign asks for one), no reposts or collab posts, no botting, no negative "hate farm" edits.
