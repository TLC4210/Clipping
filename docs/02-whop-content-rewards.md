# 02: Whop: Content Rewards (CPM) and Bounties (flat fee)

Whop runs two separate clipping products, and they need different automation paths.

## A. Content Rewards (contentrewards.com): CPM campaigns

### Flow for a clipper
1. Create a Content Rewards account. The terms allow **one account per creator** (§13.3).
2. **Link and verify your social accounts** under *Profile → Linked Accounts*. Verification is per platform, through official OAuth or a CR-issued code. Accounts linked only in Whop settings **don't count**.
3. Pick a campaign and read the brief: the source content, hooks, required tags and handles, length, banned elements, and disclosure.
4. Make the clip and post it on your linked account.
5. **Submit the post link while the post is under 30 minutes old.** Views count from posting. A post can go to only **one** campaign, and a post sent to the wrong campaign can't be resubmitted.
6. The brand approves or rejects the clip, and approval locks in what it has earned so far.
7. Earnings accrue, settle, and move to your Whop balance, then to your bank or PayPal.

> For the bot, the **30-minute submission window** is the key constraint: publishing and submission must happen together.

### Payout mechanics (current terms)
- Earnings = views/1000 × rate, capped per clip, with a minimum payout floor.
- **Clips submitted since 2026-09-25** earn CPM for **30 days from the day the clip crosses the payout threshold**, within a 30-day tracking window. Older clips earned for 7 days after approval, followed by a 3-day hold.
- Views are read from public counts on a schedule, so they lag behind the platforms.
- **Fees:** 10% on CPM. Per-post and retainer campaigns pay 10% when the campaign budget is under $5k and 0% at $5k or more. Older campaigns may show 7%.
- **Withdraw:** CR balance → Whop balance (free, $1 minimum) → bank or PayPal (provider fees apply, up to 5 business days).
- Unsettled payouts are reversed if a clip is rejected after approval (including for fake views) or the account is banned.

### Why clips get rejected
- The posting account isn't linked or verified.
- The post was over 30 minutes old, reused across campaigns, or reused with a logo swapped.
- It missed the brief: wrong hook, missing tag or handle, misplaced brand mention, wrong length, or a banned element. The brand must cite a **written** rule from the campaign page.
- **FTC disclosure missing.** For video, the disclosure **must appear at the beginning** (§12.9).
- **Instagram Collab** or co-posting was used without permission, which splits views.
- Required proof is missing, such as an analytics screen recording or demographics. The clip stays Pending until it's supplied.
- **Fake views** or suspicious engagement: plays with no likes or saves behind them, or an audience mostly outside the paying country.
- Uncleared music or other third-party material (the creator's responsibility).
- You get one appeal per clip. Fake-view appeals take 2–7 days.

### Terms that matter for an agent-run clipper (contentrewards.com/terms)
| § | Rule | Effect on automation |
|---|---|---|
| 2.4 | You're responsible for **all activity under your account** | The human owner is liable for whatever the bot does. |
| 7.1, 9.1–9.3 | CR uses automated review and a **0–100 Bot Score** from a third party. A high score pauses payout until a human reviews it. | Bot-like *posting* patterns can trigger flags. |
| 9.4, 13.3 | Related accounts are evaluated together. **One account per creator.** Bans carry over to new emails, detected through device and browser signals. | **No account farms.** One human, one CR account. |
| 12.1, 12.2 | No botting, view farms, engagement pods, or bought engagement. Clips must follow **the rules of the platform where they're posted**. | Platform ToS violations become CR violations too. |
| 12.4 | You need releases for identifiable people (publicity rights) | Mostly covered when a brand supplies the footage. |
| 12.9 | FTC disclosure at the **start** of the video | The pipeline needs an automatic disclosure overlay. |
| 13.2 | Botting or cheating = **permanent ban** | |
| 14.2 | The OAuth connection is **read-only. "We do not post on your behalf."** | The bot must post through platform APIs itself. |
| 17.2 | You warrant the clip infringes nothing, music included | Use only campaign-supplied source footage and cleared audio. |
| 17.3, 17.6 | The brand gets a broad license, and owns the edit when it supplied the footage | |
| 32 | **You indemnify CR** | |

The terms **don't ban AI tools or AI-edited clips**, and they say nothing specific about agent-run posting. They do ban fake engagement, duplicate accounts, and platform-rule violations.

**Content Rewards submission API:** I found none (*verify*). The documented path is the web or app UI. If there's no API, submission is either a browser-automation step or a human clicking "submit" on links the agent prepared. Browser automation against a site whose terms include bot scoring is risky, so ask CR support first.

## B. Whop Workforce Bounties: flat-fee tasks with a real API

Whop exposes **Bounties** through its public API, and they're also reachable through the Whop MCP connector in this workspace.

| Endpoint | Use |
|---|---|
| `GET /bounties?business_goal_type=clipping&status=open&country=XX` | Find clipping work. You can sort by `gross_reward_amount`. |
| `GET /bounties/{id}` | Brief, reward, deliverable types, and country allowlist. |
| `POST /bounty_submissions` | Submit `deliverable.urls` (posted links, up to 10), `file_ids` (uploaded clips, up to 10), and a `caption`. **Requires a user credential. Account API keys can't submit.** Supports `Idempotency-Key`. |
| `GET /bounty_submissions?status=…` | Track `in_progress` / `submitted` / `approved` / `denied`. |

### Live sample (pulled 2026-11-12 with `business_goal_type=clipping, status=open`)
- **"Clip 5 Shane Gillis moments for Whop AI's entertainment tab"** pays $10 gross ($7 net) for 5 clips of 30–60s, with a $1,000 budget and 83 of 100 spots left. It's limited to a country allowlist that **doesn't include the US**.
  - **It requires a 5-minute screen-share livestream of you browsing footage and cutting a clip.** That's a proof-of-human requirement, so an agent can't do this task.
- A template or test bounty ($1) whose brief tells clippers to "post to your own account … warm up a new account if you have to" and to submit a screen recording showing the clips live.
- Only 2 open clipping bounties came back. Bounty volume is small next to Content Rewards.

**Takeaways:**
- Bounty fields like `accepted_deliverable_types` include `data_capture`, and `active_proof_livestream_feeds` exists. Whop is building **proof-of-human verification** into its work products.
- The agent should filter out any bounty that needs a livestream or capture proof.
- Fees: in the sample, net was 70% of gross. A $1.40 affiliate share came out of the $10.
