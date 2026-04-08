# Google Calendar Setup — Sales Brain

Two options. **Service Account is recommended** for deployment (no login required, just works). OAuth is easier for local testing.

---

## Option A: Service Account (RECOMMENDED for deployment)

This creates a "robot" Google account that can read your calendars 24/7 without anyone being logged in.

### Step 1: Create a Google Cloud Project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Sign in with **your infinityhospitality.net account**
3. Click the project dropdown (top left) → **New Project**
4. Name: `IHG Sales Brain`
5. Click **Create**

### Step 2: Enable the Google Calendar API

1. In your new project, go to **APIs & Services → Library**
2. Search for **Google Calendar API**
3. Click it → click **Enable**

### Step 3: Create a Service Account

1. Go to **APIs & Services → Credentials**
2. Click **+ CREATE CREDENTIALS → Service account**
3. Name: `sales-brain-calendar`
4. Click **Create and Continue**
5. Skip the optional permissions steps → click **Done**

### Step 4: Download the Key File

1. In the Credentials page, click your new service account
2. Go to the **Keys** tab
3. Click **Add Key → Create new key → JSON**
4. Save the downloaded file as `service-account.json` in the Sales_Brain_App folder
5. **IMPORTANT:** Never commit this file to Git. It's like a password.

### Step 5: Share Your Calendars with the Service Account

The service account has its own email (looks like `sales-brain-calendar@ihg-sales-brain.iam.gserviceaccount.com`). You need to share each venue calendar with it.

For EACH of these 6 calendars:

1. Open Google Calendar (calendar.google.com)
2. Find the calendar in the left sidebar
3. Click the three dots → **Settings and sharing**
4. Scroll to **Share with specific people or groups**
5. Click **+ Add people and groups**
6. Paste the service account email
7. Set permission to **See all event details**
8. Click **Send**

Calendars to share:
- The Bridge Building Events
- The Bell Tower Events
- Cherokee Dock Events
- Saddle Woods Farm Events
- Off Site Events
- Holidays/Lot R/Titans Events/Etc

### Step 6: Configure the App

Set the environment variable pointing to your key file:

```bash
export GOOGLE_SERVICE_ACCOUNT_KEY="/path/to/Sales_Brain_App/service-account.json"
```

For deployment (Render/Railway), add this as an environment variable and upload the key file, or paste the JSON content into an env var and adjust the code to parse it.

### Step 7: Verify

```bash
cd Sales_Brain_App
python3 setup_google_auth.py --verify
```

You should see green checkmarks for all 6 calendars.

---

## Option B: OAuth (for local testing)

This uses YOUR Google login to read calendars. Simpler to set up, but requires a logged-in user.

### Step 1-2: Same as above

Create project and enable Calendar API.

### Step 3: Create OAuth Credentials

1. Go to **APIs & Services → Credentials**
2. Click **+ CREATE CREDENTIALS → OAuth client ID**
3. If prompted, configure the **OAuth consent screen** first:
   - User type: **Internal** (if using Google Workspace) or **External**
   - App name: `IHG Sales Brain`
   - User support email: your email
   - Add scope: `https://www.googleapis.com/auth/calendar.readonly`
   - Save
4. Back in Credentials → **OAuth client ID**
5. Application type: **Desktop app**
6. Name: `Sales Brain Desktop`
7. Click **Create**
8. Click **Download JSON**
9. Save as `credentials.json` in the Sales_Brain_App folder

### Step 4: Run the Setup Script

```bash
cd Sales_Brain_App
python3 setup_google_auth.py
```

A browser window opens. Sign in with the infinityhospitality.net account that has access to the venue calendars. Authorize the app. The script saves a `token.json` file.

### Step 5: Verify

```bash
python3 setup_google_auth.py --verify
```

---

## Environment Variables Summary

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_SERVICE_ACCOUNT_KEY` | For Option A | Path to service-account.json |
| `ANTHROPIC_API_KEY` | Always | Your Anthropic API key |
| `HUBSPOT_API_KEY` | For HubSpot tools | Your HubSpot private app token |
| `FLASK_SECRET_KEY` | Production | Random string for session security |

---

## Troubleshooting

**"Calendar not found or not shared"**
→ Share the calendar with the service account email (Option A) or sign in with the correct Google account (Option B).

**"403 Forbidden"**
→ The Calendar API isn't enabled, or the calendar isn't shared with the right account. Double-check both.

**"Token expired"**
→ For OAuth: run `python3 setup_google_auth.py --test` — it auto-refreshes. For service accounts: tokens don't expire.

**"credentials.json not found"**
→ Download the OAuth client JSON from Google Cloud Console and save it in the Sales_Brain_App folder.

---

## For Deployment (Render / Railway)

Service account is the way to go. Two approaches:

**File-based:** Upload `service-account.json` and set `GOOGLE_SERVICE_ACCOUNT_KEY` to the path.

**Environment variable (more secure):** Paste the entire JSON content into an env var called `GOOGLE_SERVICE_ACCOUNT_JSON`, then modify `get_calendar_service()` in tools.py to read from the env var:

```python
import json, tempfile
json_content = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
if json_content:
    info = json.loads(json_content)
    creds = service_account.Credentials.from_service_account_info(info, scopes=[...])
```

This is already noted in tools.py as a TODO for deployment.
