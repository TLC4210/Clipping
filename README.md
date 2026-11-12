# Clipping: research for an automated clipper

This repo collects research on running a short-form clipping operation for **YouTube Shorts** and **Instagram Reels** with an AI agent doing the work, and a blueprint for building one.

Research date: **2026-11-12**. Platform rules and campaign rates change often, so re-check anything marked *verify* before you rely on it.

**The pipeline code is in [`PIPELINE.md`](PIPELINE.md)** (setup, daily commands, how it works), with the code in `clipper/`.

## Files

| File | What's in it |
|---|---|
| [`docs/01-clipping-economy.md`](docs/01-clipping-economy.md) | What clipping is, who pays, rates, pay models, marketplaces |
| [`docs/02-whop-content-rewards.md`](docs/02-whop-content-rewards.md) | Content Rewards mechanics, terms, rejection rules, and the Whop Bounties API |
| [`docs/03-youtube.md`](docs/03-youtube.md) | Shorts specs, originality and spam policies, the Data API upload path, quotas, and the Nov 2026 changes |
| [`docs/04-instagram.md`](docs/04-instagram.md) | Reels originality and aggregator rules, the Graph API publishing path, and its limits |
| [`docs/05-automation-stack.md`](docs/05-automation-stack.md) | Pipeline design, open-source building blocks, paid APIs, and the tools connected to this workspace |
| [`docs/06-agent-limits-and-risks.md`](docs/06-agent-limits-and-risks.md) | What an agent can and can't do here, where a human must stay involved, and the ban risks |
| [`docs/07-build-plan.md`](docs/07-build-plan.md) | A phased plan for building the automated clipper |
| [`docs/08-niche-and-accounts-plan.md`](docs/08-niche-and-accounts-plan.md) | **Chosen niches** (GTA, Minecraft, FaZe streams, Shawn Ryan Show), the multi-account layout, rights for each niche, and priority order |
| [`docs/09-clip-allowlist.md`](docs/09-clip-allowlist.md) | **Clip allowlist:** creators who pay for or allow clips (Lacy, CORE, Jason, FaZe Flank, Lysium, Fable SMP…), a blocked list, and a watchlist |
| [`docs/sources.md`](docs/sources.md) | Every source used, with a reliability note |

## Summary

1. **The pay model.** Brands and creators fund campaigns that pay clippers per 1,000 views on clips posted to the clipper's *own* accounts. The typical rate is about **$1 CPM**, with a range of roughly $0.05–$6. Content Rewards (Whop) takes a **10% fee**. A clip at $1 CPM with 50k views earns about $45 net.
2. **The agent can do the production work:** transcribe, find moments, cut, reframe to 9:16, caption, QA, publish through official APIs, and track views. Each of these steps has open-source tools and official APIs.
3. **The agent can't own the identity.** A human must own the social accounts and the Content Rewards/Whop account, complete phone and ID checks, accept the terms, and stay legally responsible. Content Rewards allows **one account per creator** and **bans burner or duplicate accounts**. Some Whop bounties require a **livestream showing a human doing the work**, so an agent can't do those.
4. **Publishing via API got easier in Nov 2026.** Since **2026-11-02**, YouTube no longer locks uploads from unverified API projects as private. Uploads have their own quota bucket of **100 per day**. Instagram allows **100 API-published posts per account per 24 hours** from a professional account.
5. **The main risk is originality enforcement, not the tooling.**
   - YouTube's *inauthentic/reused content* policy and its spam/circumvention rules terminate mass-produced channels.
   - Instagram stops recommending accounts that post **10+ unoriginal reels in 30 days**, and it swaps reposts for the original.
   - The bot needs to make transformative edits (hooks, captions, commentary, framing), not mirror the source.
6. **Recommended first build:** a human-in-the-loop pipeline. The agent drafts and QAs clips, a human approves them, and then the agent publishes, submits, and tracks. See [`docs/07-build-plan.md`](docs/07-build-plan.md).
