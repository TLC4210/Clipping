# Setup guide (Windows)

This sets up the same clipping bot we run, on your own Windows PC and your own accounts. When it's done:

- **3:00 AM**: the bot studies which clips of your campaign creators went viral for other channels, and writes a music report saying which tracks to download.
- **4:00 AM**: it downloads sources and cuts clips. Claude picks the moments and plans the edit: facecam on top, jump cuts, punch-in zooms, emoji, sound effects, music and captions.
- **8:00 AM**: it checks your channels' stats.
- **Each morning (you, about 10 minutes)**: watch the clips, approve the good ones, publish, and submit the links to Content Rewards.

Nothing is posted without your approval.

**Time to set up:** about 2 hours, mostly clicking through Google and Meta screens. Do the parts in order.

**Running cost:** Claude API usage is a few cents per source video. Google Cloud Storage for Instagram uploads costs pennies a month. Everything else is free.

**You need:**
- A Windows 10/11 PC that's on, or asleep, overnight, with about 30 GB of free disk.
- A phone for 2-step verification.
- Your own YouTube channels and Instagram accounts. Every account must belong to you. Content Rewards bans shared or duplicate accounts.

> **Run `python -m clipper doctor` at any point.** It checks everything below and tells you what's missing and which Part fixes it.

---

## Part 1: Install the tools (10 min)

Open **PowerShell** (Start → type "PowerShell") and run:

```powershell
winget install -e --id Python.Python.3.12
winget install -e --id Gyan.FFmpeg
winget install -e --id Git.Git
```

Close PowerShell and open a new one so Windows finds the new tools. Check them:

```powershell
python --version      # 3.12.x
ffmpeg -version       # first line prints a version
git --version
```

**Caption font:** install **Inter** (fonts.google.com/specimen/Inter → *Get font* → *Download all* → unzip → select the .ttf files → right-click → *Install*). Without it, captions use Arial.

## Part 2: Get the code (10 min)

```powershell
cd $HOME\Documents
git clone https://github.com/TLC4210/Clipping.git
cd Clipping
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install torch --index-url https://download.pytorch.org/whl/cpu   # for Whisper captions
python -m pytest -q          # every test should pass
copy .env.example .env
copy config\accounts.example.yaml config\accounts.yaml
copy rights\joined.example.yaml rights\joined.yaml
mkdir secrets
```

From now on, every time you open a new PowerShell, run `cd $HOME\Documents\Clipping` then `.venv\Scripts\activate`.

> If `pip install` or the tests fail with **"An Application Control policy has blocked this file"**, see Troubleshooting at the end.

**Files that are yours only** (git-ignored, never committed): `.env`, `secrets\`, `config\accounts.yaml`, `rights\joined.yaml`, `data\`.

## Part 3: Create your accounts (30 min)

The bot runs up to three niches, each with its own YouTube channel and Instagram account:

| Niche | What it posts | Where sources come from |
|---|---|---|
| `gta` | GTA moments | CC BY-licensed YouTube videos and your own gameplay |
| `minecraft` | Minecraft moments | CC BY-licensed YouTube videos and your own gameplay |
| `streams` | Streamer clips (Lacy, Jason, CORE…) | Campaigns you join (Part 7), from YouTube and Twitch |

Start with whichever you want. `streams` is the one that pays through campaigns.

1. **YouTube channel for each niche:** youtube.com → profile picture → *Settings* → *Add or manage your channels* → *Create a channel*. Pick your own name. One Google login can own several channels. Copy each channel's ID from YouTube Studio → *Settings* → *Channel* → *Advanced settings* (it starts with `UC`).
2. **Instagram account for each niche:** create it, then *Settings* → *Account type and tools* → *Switch to professional account* → **Business** (Content Rewards only connects Business accounts) → category *Gaming video creator*.
3. **Content Rewards** (contentrewards.com, 18+): one account for you. *Settings* → *Connected accounts* → connect **every** channel and Instagram account. More detail is in [`rights/SIGNUP.md`](rights/SIGNUP.md).

## Part 4: Google Cloud: API key and upload permission (20 min)

1. Go to **console.cloud.google.com** → project picker in the top bar → **New project** → name it `clipper` → Create → select it.
2. **APIs & Services → Library** → search **YouTube Data API v3** → **Enable**.
3. **API key (for finding videos):** *APIs & Services → Credentials → Create credentials → API key*. Click the key → *Restrict key* → API restrictions → YouTube Data API v3 → Save. Paste it into `.env` after `YOUTUBE_API_KEY=`.
4. **OAuth consent screen:** *Google Auth Platform* → Get started. App name `Clipper`, your email, **External**, then finish. Under **Audience**, click **Publish app** (*In production*). If you leave it in Testing, your login expires every 7 days. Google warns that the app is unverified; that's fine because only you use it.
5. **OAuth client (for uploading):** *Credentials → Create credentials → OAuth client ID → **Desktop app*** → Create → **Download JSON**. Save it as `secrets\google_client_secret.json`.
6. In `config\accounts.yaml` (open it in Notepad), for each niche you're using: under `youtube:` set `enabled: true` and paste the `channel_id`. Leave `privacy: private`.
7. Log each channel in:
   ```powershell
   python -m clipper auth-youtube --niche gta
   ```
   A browser opens. Pick the Google account, then **pick that niche's channel**. If you see "Google hasn't verified this app", click *Advanced → Go to Clipper* → Allow. Repeat for each niche.

**Keep `privacy: private` until you've checked a few uploads** in YouTube Studio, then change it to `public`. Campaigns only count public posts.

## Part 5: Instagram API (30 min, optional at first)

YouTube works on its own, so you can come back to this part later.

1. **developers.facebook.com** → *My Apps → Create App* → use case **"Manage messaging & content on Instagram"** → type Business.
2. In the app: **Instagram → API setup with Instagram login**.
3. *App roles → Roles → Add people → Instagram Tester* → enter each IG username. Then, in each IG account: *Settings → Website permissions → Tester invites* → Accept.
4. **API setup with Instagram login** → *Generate access tokens* → **Add account** → log in as the IG account → allow.
   - Save the **token** in Notepad as `secrets\ig_<niche>_token.txt` (just the token).
   - Paste the **Instagram user ID** as `ig_user_id` under that niche's `instagram:` in accounts.yaml, and set `enabled: true`.
5. The app can stay in **Development mode**. App Review isn't needed for accounts that have a role on your app.
6. **Tokens last 60 days.** The bot renews them automatically when it publishes. To renew by hand: `python -m clipper refresh-instagram`.
7. **Video hosting:** Instagram downloads each video from a public link. In your Google Cloud project:
   - **Cloud Storage → Buckets → Create**: name it like `clipper-clips-<random>`, pick a US region, **untick "Enforce public access prevention"**. This needs billing on, but it costs pennies.
   - Open the bucket → *Permissions → Grant access* → `allUsers` → **Storage Object Viewer**.
   - *IAM & Admin → Service Accounts → Create* (`clipper-uploader`). In the bucket's *Permissions*, grant its email **Storage Object Admin**. On the service account, go to *Keys → Add key → JSON* and save it as `secrets\gcs_key.json`.
   - In accounts.yaml, set `gcs_bucket: <your-bucket-name>` under each `instagram:`.

## Part 6: Claude API key (5 min)

1. **console.anthropic.com** → sign up → **Billing** → add credits ($10 is plenty to start).
2. **API Keys → Create key** → paste it into `.env` after `ANTHROPIC_API_KEY=`.

Claude picks the moments, writes hooks and titles, finds the facecam, plans the edits and checks each clip. Without a key the bot still runs, but its picks are basic and it makes no edits.

## Part 7: Join campaigns (for stream clips)

The bot only clips a streamer when **you** have joined that creator's campaign. Joining is what gives you permission.

1. Open [`rights/SIGNUP.md`](rights/SIGNUP.md) for the current campaigns and links. Join one on Content Rewards and read its rules (some only appear after you join).
2. Add its key to **`rights\joined.yaml`**. The keys are in `rights/creators.yaml`: `lacy`, `jasontheween`, `core`, `clix`, `fablesmp`, and so on.
   ```yaml
   joined:
     lacy: 2026-11-20
     core: 2026-11-20
   ```
3. Run `python -m clipper creators` and confirm `bot_will_use: true` for it.

`creators.yaml` itself is shared: every entry there stays `joined: false`, and your joins live only in your `joined.yaml`.

## Part 8: Music and sound effects (20 min)

The bot can put a quiet music bed and sound effects under clips, but only from files you download. It never uses commercial songs or AI-generated audio, and the campaigns ban AI content.

1. YouTube Studio → **Audio library** → *Music*. Filter **Attribution not required**, then the genre and mood that the daily music report suggests (`data\reports\music-<date>.md`). Click *Download* on each track you want.
2. Move the files into the right folder:

   | Folder | What goes there |
   |---|---|
   | `data\assets\music\youtube\gta\` | Audio Library tracks for GTA. The standard licence covers **YouTube only**. |
   | `data\assets\music\youtube\minecraft\` | Audio Library tracks for Minecraft |
   | `data\assets\music\anywhere\<niche>\` | Tracks licensed for every platform (also used on Instagram) |
   | `data\assets\sfx\youtube\<name>.mp3` | Audio Library sound effects (*Sound effects* tab). The file name is how Claude refers to it, e.g. `whoosh.mp3`, `boom.mp3`. |

   We started with 10 GTA tracks (dark/angry/funky Hip-Hop & Rap and Dance & Electronic), 7 Minecraft tracks (happy/funky Children's and Dance & Electronic, plus calm Ambient) and 3 effects (whoosh, boom, cowbell).
3. Music is turned on per niche in `config\niches.yaml` with `music: true` (on for gta and minecraft, off for streams).

When a clip uses YouTube-only music or effects, the bot also renders an Instagram version without them, and publishes that one to Instagram.

## Part 9: Schedule the daily jobs (2 min)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-schedule.ps1
```

This creates three jobs in Task Scheduler under **Clipper**: 3:00 research, 4:00 clips and 8:00 analytics. They run while you're logged in, wake the PC from sleep, and catch up if the PC was off. Logs go to `data\logs\`. To remove them: `scripts\install-schedule.ps1 -Remove`.

Which niches the 4 AM job makes, and how many, is set in `scripts\daily-clips.cmd`.

Then run `python -m clipper doctor` one more time. It should end with **Ready to run.**

## Part 10: Your daily routine (about 10 min)

```powershell
python -m clipper review                     # clips waiting for you, with file paths
python -m clipper approve 17 18              # the clip numbers you liked
python -m clipper reject 19                  # and the ones you didn't
python -m clipper publish --niche streams          # dry run: shows what would post
python -m clipper publish --niche streams --live   # posts for real
```

1. Watch each clip in `data\clips\<niche>\` before approving it.
2. After a campaign clip goes live, **submit its link on Content Rewards within 30 minutes**. Campaign clips must be public. `publish` prints a `SUBMIT_NOW` block with the campaign's submit page. If you run the bot through Claude Code, Claude can do the submission in your Chrome right after posting. Content Rewards has no submission API, and an unattended script logging in would risk its bot score, so a person (or Claude, in your session) does this step. On the submit form, make sure **only** the campaign clip is ticked; it pre-selects every recent post.
3. Reports to skim:
   - `data\reports\analytics-<date>.md`: views and anything that needs a look, like region blocks or failed uploads.
   - `data\reports\music-<date>.md`: what music to download next.
4. Changed a style setting? `python -m clipper rerender <ids>` re-renders clips from their saved edit plans without picking again.

Your own gameplay can go in `data\inbox\<niche>\`. It's picked up automatically.

## Settings worth knowing (`config\niches.yaml`)

| Setting | What it does |
|---|---|
| `layout` | `facecam_stack` (cam on top; streams), `blur_stack` (blurred background), `full_crop` |
| `jump_cuts` | cut quiet dead air inside clips |
| `music`, `music_volume` | music bed on/off per niche, and its level (0.25 = clearly there) |
| `burn_credit` | `false`: the source credit goes only in the description |
| `clip_min_s`, `clip_max_s` | clip length range |
| `daily_cap_per_account` | the most posts per account per day |

## Rules to keep (or lose the account)

- **No AI-generated content** on campaign clips: no AI voices, images or video. One strike bans you from every Reach campaign.
- **Paid-promotion disclosure** (Content Rewards terms §12.9, FTC): the bot does this for every campaign clip. It shows "#AD · PAID CLIP" for the first 4 seconds, starts the caption with "#ad", and ticks YouTube's "includes paid promotion" box. Don't remove them.
- **Campaign audience:** most campaigns need at least 50% of your viewers in the US, Canada, UK, Australia or New Zealand. Check it in YouTube Studio → *Analytics* → *Audience*.
- **One person, one Content Rewards account.** Don't share accounts or logins.
- **Only clip campaigns you've joined** (Part 7) and CC BY or your own footage. The bot enforces this from `rights\`.

## Troubleshooting

- **"An Application Control policy has blocked this file"** (Windows Smart App Control): Windows refused a package's DLL. Don't turn Smart App Control off. Install a different release of the blocked package instead; for example, `jiter` is pinned to 0.10.0 because 0.19.0 was blocked. Run `pip install <package>==<older version>`, then `python -m clipper doctor`.
- **YouTube "Sign in to confirm you're not a bot"** during downloads: YouTube is temporarily blocking your connection, usually after a very large download. Wait a few hours. The bot keeps those sources queued and uses Twitch clips meanwhile. **Don't** log the downloader into your channel accounts.
- **YouTube upload says the token is invalid or expired:** rerun `python -m clipper auth-youtube --niche <niche>`. If this keeps happening every 7 days, your consent screen is still in Testing (Part 4, step 4).
- **A scheduled job didn't run:** open Task Scheduler → *Clipper* → check *Last Run Result*, and read `data\logs\`. The jobs only run while you're logged in.
- **Anything else:** `python -m clipper doctor`.
