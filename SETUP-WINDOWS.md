# Setup on your Windows PC (step by step)

Total time is about 1.5–2 hours, mostly clicking through Google and Meta screens. Do the parts in order.

---

## Part 1: Install the tools (10 min)

Open **PowerShell** (Start → type "PowerShell") and run:

```powershell
winget install -e --id Python.Python.3.12
winget install -e --id Gyan.FFmpeg
winget install -e --id Git.Git
```

Close PowerShell and open a new one so the tools are found. Then check:

```powershell
python --version      # 3.12.x
ffmpeg -version       # first line prints a version
git --version
```

Optional but recommended: install the **Inter** font (fonts.google.com/specimen/Inter → Download → open the .ttf files → Install). Captions fall back to Arial without it.

## Part 2: Get the code (5 min)

```powershell
cd $HOME\Documents
git clone https://github.com/TLC4210/Clipping.git
cd Clipping
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q          # should say "8 passed"
copy .env.example .env
copy config\accounts.example.yaml config\accounts.yaml
mkdir secrets
```

From now on, every time you open a new PowerShell: `cd $HOME\Documents\Clipping` then `.venv\Scripts\activate`.

## Part 3: Create the accounts (you, 30 min)

For each niche you want to start with (GTA and Minecraft first, Streams later):

1. **YouTube channel:**
   - youtube.com → profile picture → *Settings* → *Add or manage your channels* → *Create a channel*. One Google login can own several channels.
   - Get each channel's ID from YouTube Studio → *Settings* → *Channel* → *Advanced settings* → copy the **Channel ID** (starts with `UC`).
2. **Instagram account:**
   - Create it, then *Settings* → *Account type and tools* → *Switch to professional account* → **Creator** → category *Gaming video creator*.
3. **Content Rewards:**
   - Sign up at contentrewards.com (18+).
   - *Profile* → *Linked Accounts* → *Add Account*. Link and verify **every** YouTube and Instagram account. All accounts go under the one Content Rewards profile.

## Part 4: Google Cloud: API key + upload permission (20 min)

1. Go to **console.cloud.google.com** → top bar project picker → **New project** → name it `clipper` → Create → select it.
2. **APIs & Services → Library** → search **YouTube Data API v3** → **Enable**.
3. **API key (for finding videos):**
   - *APIs & Services → Credentials → Create credentials → API key*.
   - Click the key → *Restrict key* → API restrictions → YouTube Data API v3 → Save.
   - Open `.env` in Notepad and paste it after `YOUTUBE_API_KEY=`.
4. **OAuth consent screen:**
   - *Google Auth Platform* (or *APIs & Services → OAuth consent screen*) → Get started.
   - App name `Clipper`, your email, **External**, then finish.
   - Under **Audience**, click **Publish app** (set it to *In production*). If you leave it in "Testing", your login expires every 7 days.
   - Google will warn that the app is unverified. That's fine because only you use it.
5. **OAuth client (for uploading):**
   - *Credentials → Create credentials → OAuth client ID → Application type: **Desktop app*** → Create → **Download JSON**.
   - Save it as `Clipping\secrets\google_client_secret.json`.
6. In `config\accounts.yaml` (Notepad), under `gta:` → `youtube:`, set `enabled: true` and paste the `channel_id`. Do the same for `minecraft`.
7. Log each channel in:
   ```powershell
   python -m clipper auth-youtube --niche gta
   ```
   A browser opens. Pick the Google account, then **pick the GTA channel**. If you see "Google hasn't verified this app", click *Advanced → Go to Clipper* → Allow. Repeat with `--niche minecraft`.

Keep `privacy: private` in accounts.yaml for the first few uploads. Check them in YouTube Studio, then change it to `public`.

## Part 5: Instagram API (30 min)

1. Go to **developers.facebook.com** → log in → *My Apps → Create App*. Pick the use case **"Manage messaging & content on Instagram"** (Instagram API). App type: Business.
2. In the app: **Instagram → API setup with Instagram login**.
3. *App roles → Roles → Add people → Instagram Tester* → enter each IG account username.
   - Then **in each IG account**: *Settings → Website permissions / Apps and websites → Tester invites* → Accept.
4. Back in **API setup with Instagram login** → *Generate access tokens* → **Add account** → log in as the IG account → allow.
   - Copy the **token** and save it in Notepad as `Clipping\secrets\ig_gta_token.txt` (just the token, nothing else).
   - Copy the **Instagram user ID** shown next to it and paste it as `ig_user_id` under `gta:` → `instagram:` in accounts.yaml. Set `enabled: true`.
   - Repeat for the Minecraft account (`ig_minecraft_token.txt`).
5. Your app can stay in **Development mode**. App Review isn't needed for accounts that have a role on your app.
6. **Tokens last 60 days.** The bot renews them automatically (once a week, on any `--live` run). To renew by hand: `python -m clipper refresh-instagram`.
7. **Video hosting:** Instagram downloads the video from a public web link, so you need a public storage bucket. In the same Google Cloud project:
   - **Cloud Storage → Buckets → Create**. Name it something like `clipper-clips-<random>`, pick a US region, and **untick "Enforce public access prevention"** → Create. This needs billing turned on, but it costs pennies.
   - Open the bucket → *Permissions → Grant access* → principal `allUsers`, role **Storage Object Viewer** → Save.
   - Let the bot upload to it: *IAM & Admin → Service Accounts → Create service account* (name `clipper-uploader`) → Done. Back in the bucket → *Permissions → Grant access* → paste the service account's email → role **Storage Object Admin** → Save.
   - Open the service account → *Keys → Add key → Create new key → JSON*. Save the downloaded file as `Clipping\secrets\gcs_key.json`.
   - In accounts.yaml, under each `instagram:` block set `gcs_bucket: <your-bucket-name>`. Leave `gcs_credentials: secrets/gcs_key.json` as it is.
   - The bot now uploads each clip, hands Instagram the link, and deletes the file after posting.

## Part 6: Claude API key (5 min)

1. Go to **console.anthropic.com** (Claude Console) → sign up → **Billing** → add credits ($10 is plenty to start).
2. **API Keys → Create key** → copy it into `.env` after `ANTHROPIC_API_KEY=`.

Cost: roughly a few cents per source video analysed. Without a key the bot still works, but its moment picks and titles are basic.

## Part 7: Join campaigns (when you want stream clips)

1. On Content Rewards, join a campaign from `docs/09-clip-allowlist.md` (for example the Lacy or CORE pool) and read its rules.
2. In `rights\creators.yaml`, set that creator's `joined: true`. Paste in any rules that unlocked after joining.
3. Run `python -m clipper creators` and confirm `bot_will_use: true` for it.

## Part 8: First run

```powershell
python -m clipper run --niche gta --limit 1
python -m clipper review            # lists clips with file paths → open them in File Explorer and watch
python -m clipper approve 1 2       # the clip numbers you liked
python -m clipper publish --niche gta           # dry run: shows what would post
python -m clipper publish --niche gta --live    # posts for real
```

Your own gameplay goes in `Clipping\data\inbox\gta\` and is used automatically.

If YouTube says "Sign in to confirm you're not a bot" during fetch, wait a few hours and try again. **Don't** log yt-dlp into your clip accounts.

## Part 9: Run it automatically (Task Scheduler)

Once you trust the output, schedule it twice a day. Run this in PowerShell, with `<YOU>` replaced by your Windows username:

```powershell
schtasks /Create /SC DAILY /ST 10:15 /TN "Clipper GTA AM" /TR "cmd /c cd /d C:\Users\<YOU>\Documents\Clipping && .venv\Scripts\python -m clipper run --niche gta --limit 2 --auto-approve --publish --live >> data\run.log 2>&1"
schtasks /Create /SC DAILY /ST 18:15 /TN "Clipper GTA PM" /TR "cmd /c cd /d C:\Users\<YOU>\Documents\Clipping && .venv\Scripts\python -m clipper run --niche gta --limit 2 --auto-approve --publish --live >> data\run.log 2>&1"
```

The PC has to be on and awake at those times.
