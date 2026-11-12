# 01: The clipping economy

## What a "clipper" is

A clipper cuts long-form content (podcasts, streams, interviews, specials, product demos) into short vertical clips. The clipper posts them to **their own** TikTok, Instagram Reels, YouTube Shorts, or X accounts, and the content owner or a brand pays for the views. The arrangement gives the content owner a performance-paid distribution network instead of paid ads.

Scale signals reported in 2026:
- Whop reported **3.5B+ clipped views in one month** and a $1.6B valuation (Trends.vc).
- Content Rewards was reportedly paying **>$40k/day** across about 1M videos/month as of April 2026 (via Forbes, quoted second-hand).
- NPR (May 2026) covered one network of **40,000 freelance clippers**, mostly aged 16–24. One 19-year-old reported earning about **$4,000/month**. Hasan Piker's streams average about 33k live viewers, while his clips average more than 700k views.
- Cluely says it hired **700+ clippers**. Polymarket ran a **$0.50 CPM, $70k-budget** campaign.

## Pay models

| Model | How it pays | Notes |
|---|---|---|
| **CPM (pay-per-view)** | (views ÷ 1000) × rate, capped per clip | The dominant model. Views are counted on *your* post. Usually there's a minimum payout threshold and a per-clip cap (about $200 is common). |
| **Per post** | A fixed $ per approved clip that hits a view minimum | On Content Rewards, it's paid about 15 min after approval. |
| **Retainer** | A fixed $ per week or month for an agreed number of posts | Closer to a freelance contract. |
| **Flat bounty** | A fixed $ per accepted deliverable (e.g. "5 clips for $10") | Whop Workforce Bounties. Often doesn't require posting. See doc 02. |
| **Affiliate** | A commission on sales from your link | How many clippers started (NPR). |
| **UGC on brand accounts** | About $2–8 CPM for posting on the *brand's* accounts | An adjacent model (Trends.vc). |

## Rates (late 2026)

- Content Rewards markets an **average of about $1/1k views**.
- A sample of 50 Whop campaigns in Sep 2026 had a **median of $1.00**, with a range of **$0.05–$3.00** (builtbyfoundry).
- Other reported ranges: $0.50–$1.50 (ClipAffiliates) and $0.20–$6 (OpenClip). Clipping.net runs $0.40–$3.
- **Vyro** (MrBeast-backed) pays about $1–3 CPM and requires no audience.
- Outliers: an AI startup paid **$25 CPM**. Music campaigns can drop to about $0.30.
- Some campaigns require **10k–100k views** before a clip qualifies for any pay.
- Trends.vc expects per-view rates to fall as AI lowers the barrier to entry.

### Worked example (Content Rewards CPM, current terms)

- $1.00 CPM × 50,000 views = $50.00 gross. The 10% fee is $5.00, so **$45.00 net**.
- A $2 minimum payout at a $1 rate means a clip earns nothing until it reaches 2,000 views.
- Earning stops when the per-clip cap is hit or the 30-day earning window ends.

**Implication for automation:** income ≈ Σ(views per clip) × CPM × 0.9. Clips that never reach the threshold earn $0. The bot is valuable only if it consistently produces clips that **break out**. Raw volume doesn't pay, and volume is also what platforms penalize (docs 03 and 04).

## Marketplaces and players

| Player | Type | Notes |
|---|---|---|
| **Content Rewards** (Whop) | CPM marketplace | The largest. contentrewards.com, with Whop balance payouts. See doc 02. |
| **Whop Workforce / Bounties** | Flat-fee task marketplace | Has a public API with `business_goal_type=clipping`. See doc 02. |
| **Vyro** | CPM marketplace | MrBeast-backed. |
| **Clipping.io / Clipping.net** | Performance network | Skews toward creator and crypto brands. |
| **ClipFarm, ClipAffiliates** | Marketplaces / networks | Smaller. |
| **Clipping Culture, Clipping Agency** | Managed agencies | Recruit and pay clippers, taking about 15–20%. |
| **OpusClip, Vizard, Klap, Submagic** | AI clipping SaaS | Tools, not marketplaces. See doc 05. |

## Industry view on automation (Trends.vc, Jun 2026)

- AI auto-clipping is making editing cheap, so value shifts to **distribution and hook selection** ("taste over tooling").
- Top human clippers reportedly post **up to 18 near-identical uploads/day across many accounts**, and platforms are now targeting that pattern.
- YouTube reportedly terminated **16 channels with 4.7B combined views** in one month under the inauthentic-content policy.
- The biggest business risk is losing accounts: a clipper's accounts *are* the business.
