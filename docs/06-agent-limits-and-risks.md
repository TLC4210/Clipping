# 06: What an agent can and can't do, and the risks

## Who has to do what

| Task | Agent | Human | Why |
|---|---|---|---|
| Create social accounts, pass phone, SMS, or ID checks | ✗ | ✓ | Identity verification. The platforms and CR require real accounts held by real people. |
| Create the Content Rewards / Whop account, accept terms, set up payouts and tax info | ✗ | ✓ | It's a legal agreement. CR §2.4 makes the account holder liable for all activity. |
| Link and verify social accounts to CR (OAuth or code) | ✗ | ✓ | One-time, owner consent |
| Grant OAuth tokens to our app (YouTube `youtube.upload`, IG `instagram_business_content_publish`) | ✗ | ✓ | One-time, owner consent. After that the agent uses refresh tokens. |
| Find and parse campaigns | ✓ | review | |
| Download campaign source footage | ✓ | | |
| Transcribe, pick moments, edit, caption, reframe | ✓ | | |
| QA against the brief | ✓ | spot-check | |
| Approve a clip for posting (phase 1) | assist | ✓ | Protects the accounts while the moment selector is unproven |
| Publish through official APIs | ✓ | | Sanctioned automation |
| Submit to campaign (Whop Bounties API) | ✓ | | Uses the human's **user** token. Account API keys can't submit. |
| Submit to Content Rewards CPM campaigns | ? | ✓ (likely) | No public submission API found. Ask CR before browser-automating it. |
| Bounties that need a **livestream or screen-share proof** | ✗ | — | Proof-of-human by design. Skip these. |
| Appeals, brand comms, disputes | draft | ✓ | |

## Hard "don'ts" (bannable, and some are fraud)
1. **Account farms, burner accounts, multiple CR accounts.** CR §13.3 allows one account per creator and detects linked devices. YouTube's spam and circumvention policies terminate coordinated channel networks.
2. **"Warming" fake accounts** with bot engagement. Some briefs casually say "warm up a new account". Do it only with genuine, human-owned accounts and real posting, never with automated engagement.
3. **Bought or botted views, engagement pods, view farms.** Permanent ban (CR §12.1–12.2, §13.2). Clawback of balances (§13.4). Could be fraud against the brand.
4. **Unofficial posting APIs or private-API libraries** for IG or YT. These break the ToS and get accounts locked.
5. **Posting the same raw clip across many accounts.** Instagram's aggregator penalty (10+ unoriginal posts in 30 days) and YouTube's inauthentic-content enforcement are built for exactly this.
6. **Clipping content you have no rights to** outside a campaign that grants them. Copyright strikes (3 = channel termination), DMCA, and CR §17.2 warranty plus §32 indemnity all apply.
7. **Skipping FTC disclosure.** It must be at the **start** of the video for CR campaigns.

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Channel or account flagged as inauthentic or aggregator | High if volume-first | Loses distribution or the account | Volume caps (start ≤3 posts/day/platform), a strong transformation layer, varied formats, human review in phase 1 |
| CR Bot Score flags our clips | Medium | Payout paused | Organic posting cadence, real engagement, no view buying, keep analytics proof ready |
| Missed the 30-min submission window | Medium | $0 for that clip | Publish and submit as one job, and alert a human immediately if submission is manual |
| Brief non-compliance | Medium | Rejection | LLM brief parser + automatic QA checklist + required-element overlays |
| Copyright / Content ID on music | Medium | Blocked or demonetized clip, strike | Source and campaign-supplied audio only, no added trending music via API (IG gives no access anyway) |
| Rate compression (AI floods supply) | High (long-term) | Lower $/view | Compete on hook quality and niche taste, prefer high-CPM niche campaigns |
| Platform API or policy changes | Ongoing | Pipeline breaks | Re-verify docs 03 and 04 monthly, and wrap the APIs behind adapters |
| Public view-count definition change (YT 2026-08-27) | Done | Campaigns may change how they verify | Track engaged and public metrics separately |

## Answer to "can *you* (the agent) become a clipper?"
**Not as the account holder.** The marketplaces and platforms require a real person who owns the accounts, accepts the terms, gets paid, and is liable. The agent **can be the whole production crew and operator** behind that person's accounts: finding campaigns, making clips, publishing through official APIs, submitting where an API exists, tracking, and learning. The human keeps ownership, approvals (at first), and anything that needs proof of identity or of human work.
