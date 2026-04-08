#!/usr/bin/env python3
"""
Sales Brain — Google Calendar OAuth Setup
==========================================
Run this ONE TIME to authorize the Sales Brain to read your Google Calendars.
After running, it creates a token.json file that the app uses automatically.

Two modes:
  1. SERVICE ACCOUNT (recommended for deployment)
     → Just set GOOGLE_SERVICE_ACCOUNT_KEY env var and share calendars with the
       service account email. No need to run this script.

  2. OAUTH (run this script for user-based auth)
     → Downloads a token.json that the app uses to read calendars.
     → Requires a credentials.json file from Google Cloud Console.

Usage:
  python3 setup_google_auth.py              # Interactive OAuth flow
  python3 setup_google_auth.py --test       # Test existing credentials
  python3 setup_google_auth.py --verify     # Verify calendar access for all venues
"""

import os
import sys
import json
import datetime

# ── Paths ──────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(SCRIPT_DIR, "token.json")
CREDENTIALS_PATH = os.path.join(SCRIPT_DIR, "credentials.json")

# Calendar IDs from config.py
VENUE_CALENDARS = {
    "TBB": {
        "name": "The Bridge Building Events",
        "calendar_id": "c_bk28n5pjt7f4to5npi3osh9r18@group.calendar.google.com",
    },
    "TBT": {
        "name": "The Bell Tower Events",
        "calendar_id": "c_rc231j980ifpjrcdin908bhp6o@group.calendar.google.com",
    },
    "ECD": {
        "name": "Cherokee Dock Events",
        "calendar_id": "c_01r5gcd872kciqp3cddb24dh1o@group.calendar.google.com",
    },
    "SWF": {
        "name": "Saddle Woods Farm Events",
        "calendar_id": "c_6d92ce8c1ff49ceb9243be6386ff28138385568bcca4bb9c2fd3ebcdb5585202@group.calendar.google.com",
    },
    "OFFSITE": {
        "name": "Off Site Events",
        "calendar_id": "c_pvh4bm5uatl73450u4agoe115s@group.calendar.google.com",
    },
    "HOLIDAYS": {
        "name": "Holidays/Lot R/Titans Events/Etc",
        "calendar_id": "c_c680tvchvlgemj67ahhdctsgkg@group.calendar.google.com",
    },
}

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def setup_oauth():
    """Run the interactive OAuth flow to create token.json."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("\n❌ Missing dependency. Run:")
        print("   pip install google-auth-oauthlib google-api-python-client")
        sys.exit(1)

    if not os.path.exists(CREDENTIALS_PATH):
        print("\n❌ credentials.json not found!")
        print(f"   Expected at: {CREDENTIALS_PATH}")
        print("\n   To get this file:")
        print("   1. Go to https://console.cloud.google.com")
        print("   2. Select or create a project")
        print("   3. Enable the Google Calendar API")
        print("   4. Go to Credentials → Create Credentials → OAuth client ID")
        print("   5. Application type: Desktop app")
        print("   6. Download the JSON and save it as credentials.json")
        print(f"      in: {SCRIPT_DIR}")
        sys.exit(1)

    print("\n🔐 Starting Google OAuth flow...")
    print("   A browser window will open. Sign in with the Google account")
    print("   that has access to the IHG venue calendars.")
    print("   (Use the infinityhospitality.net account)\n")

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)

    # Try localhost first, fall back to manual copy/paste
    try:
        creds = flow.run_local_server(port=8090, prompt="consent")
    except Exception:
        print("   (Couldn't start local server — using manual mode)")
        creds = flow.run_console()

    # Save token
    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())

    print(f"\n✅ Token saved to: {TOKEN_PATH}")
    print("   The Sales Brain can now read your Google Calendars.")

    return creds


def get_credentials():
    """Load credentials from token.json or service account."""
    # Option 1: Service account
    sa_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY", "")
    if sa_path and os.path.exists(sa_path):
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(sa_path, scopes=SCOPES)
        print(f"✅ Using service account: {sa_path}")
        return creds

    # Option 2: OAuth token
    if os.path.exists(TOKEN_PATH):
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

        # Refresh if expired
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Token expired — refreshing...")
            creds.refresh(Request())
            with open(TOKEN_PATH, "w") as f:
                f.write(creds.to_json())
            print("✅ Token refreshed and saved.")

        if creds and creds.valid:
            print(f"✅ Using OAuth token: {TOKEN_PATH}")
            return creds
        else:
            print("❌ Token is invalid. Re-run setup.")
            return None

    print("❌ No credentials found.")
    return None


def test_credentials():
    """Test that credentials work by making a simple API call."""
    creds = get_credentials()
    if not creds:
        print("\n   Run: python3 setup_google_auth.py")
        return False

    from googleapiclient.discovery import build
    try:
        service = build("calendar", "v3", credentials=creds)
        # Try listing calendar list (minimal API call)
        result = service.calendarList.list(maxResults=1).execute()
        print("✅ Google Calendar API connection verified!")
        return True
    except Exception as e:
        print(f"❌ API call failed: {e}")
        return False


def verify_venue_calendars():
    """Verify the Sales Brain can read each venue calendar."""
    creds = get_credentials()
    if not creds:
        print("\n   Run: python3 setup_google_auth.py")
        return

    from googleapiclient.discovery import build
    service = build("calendar", "v3", credentials=creds)

    # Check a date range (next 30 days) for each venue
    today = datetime.date.today()
    time_min = f"{today}T00:00:00Z"
    time_max = f"{today + datetime.timedelta(days=30)}T23:59:59Z"

    print(f"\n📅 Checking venue calendars (next 30 days from {today}):")
    print("   " + "─" * 55)

    all_ok = True
    for venue_code, cal_info in VENUE_CALENDARS.items():
        try:
            events_result = service.events().list(
                calendarId=cal_info["calendar_id"],
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                maxResults=5,
            ).execute()

            events = events_result.get("items", [])
            event_count = len(events)
            total = events_result.get("nextPageToken", None)
            count_str = f"{event_count}+" if total else str(event_count)

            print(f"   ✅ {venue_code:8s} │ {cal_info['name'][:35]:35s} │ {count_str} events")

            # Show first few events as sample
            for e in events[:2]:
                summary = e.get("summary", "Untitled")[:45]
                start = e.get("start", {}).get("dateTime", e.get("start", {}).get("date", ""))
                if "T" in start:
                    start = start[:10]
                print(f"            │ {'':35s} │   {start} {summary}")

        except Exception as e:
            error_msg = str(e)
            if "404" in error_msg or "notFound" in error_msg:
                print(f"   ❌ {venue_code:8s} │ {cal_info['name'][:35]:35s} │ Calendar not found or not shared")
            elif "403" in error_msg or "forbidden" in error_msg:
                print(f"   ❌ {venue_code:8s} │ {cal_info['name'][:35]:35s} │ No access — share calendar with service account")
            else:
                print(f"   ❌ {venue_code:8s} │ {cal_info['name'][:35]:35s} │ Error: {error_msg[:50]}")
            all_ok = False

    print("   " + "─" * 55)

    if all_ok:
        print("\n🎉 All venue calendars accessible! Sales Brain date availability is LIVE.")
    else:
        print("\n⚠️  Some calendars couldn't be accessed.")
        print("   Fix: Share those Google Calendars with your service account email")
        print("   or with the Google account you used for OAuth.")

    return all_ok


# ── CLI ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  SALES BRAIN — Google Calendar Setup")
    print("=" * 60)

    if "--test" in sys.argv:
        test_credentials()
    elif "--verify" in sys.argv:
        verify_venue_calendars()
    else:
        # Check if already set up
        if os.path.exists(TOKEN_PATH) or os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY"):
            print("\n   Credentials already exist. Testing...")
            if test_credentials():
                print("\n   Want to verify all venue calendars?")
                choice = input("   Run full verification? [y/N]: ").strip().lower()
                if choice == "y":
                    verify_venue_calendars()
                else:
                    print("   Done! Your Sales Brain calendar integration is ready.")
            else:
                print("\n   Existing credentials failed. Starting new OAuth setup...")
                setup_oauth()
                verify_venue_calendars()
        else:
            setup_oauth()
            print("\n   Running calendar verification...")
            verify_venue_calendars()
