"""
Sales Brain — Configuration
All API keys, calendar IDs, and escalation contacts in one place.
"""

import os
import re

# ── Claude API ──────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# ── Google Calendar IDs (source of truth for date availability) ─────
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

# Downtown venues that need Holidays/Lot R/Titans cross-check
DOWNTOWN_VENUES = {"TBB", "TBT"}

# Venues where entire property is booked (no partial-space logic)
WHOLE_VENUE = {"TBT", "ECD", "SWF"}

# TBB space prefixes for multi-space logic
TBB_SPACES = {
    "BBC": "Cumberland (1st floor)",
    "BBD": "Dyer (3rd floor)",
    "BBO": "Observatory (4th floor)",
    "BBC+D": "Cumberland + Dyer",
    "BBC+O": "Cumberland + Observatory",
    "BBD+O": "Dyer + Observatory",
    "TBB": "Entire Venue",
}

# ── Escalation Recipients ──────────────────────────────────────────
ESCALATION_GROUP = [
    {"name": "Nathaniel Beaver", "email": "nathaniel@infinityhospitality.net", "role": "Owner"},
    {"name": "Mary Topp", "email": "salesadmin@infinityhospitality.net", "role": "Sales Admin"},
    {"name": "Kevin McCarthy", "email": "kevin@infinityhospitality.net", "role": "CEO"},
]

SALES_BRAIN_EMAIL = "salesbrain@infinityhospitality.net"

# ── HubSpot OAuth 2.0 ─────────────────────────────────────────────
HUBSPOT_CLIENT_ID = os.environ.get("HUBSPOT_CLIENT_ID", "")
HUBSPOT_CLIENT_SECRET = os.environ.get("HUBSPOT_CLIENT_SECRET", "")
HUBSPOT_REDIRECT_URI = os.environ.get(
    "HUBSPOT_REDIRECT_URI",
    "https://infinity-sales-brain-production.up.railway.app/hubspot/callback"
)
HUBSPOT_SCOPES = (
    "crm.objects.deals.read crm.objects.contacts.read crm.schemas.contacts.read "
    "crm.objects.notes.read crm.objects.calls.read crm.objects.emails.read oauth"
)

# Token file path — Railway persists /app between deploys
HUBSPOT_TOKEN_FILE = os.path.join(os.path.dirname(__file__), ".hubspot_tokens.json")

# ── Question Log (Google Sheets) ───────────────────────────────────
QUESTION_LOG_SHEET_ID = os.environ.get("QUESTION_LOG_SHEET_ID", "")

# ── Paths ──────────────────────────────────────────────────────────
CONTEXT_FILE = os.path.join(os.path.dirname(__file__), "Sales_Brain_Context.md")
UPDATE_LOG = os.path.join(os.path.dirname(__file__), "Sales_Brain_Update_Log.md")

# ── Confidence thresholds ──────────────────────────────────────────
GREEN_THRESHOLD = 0.90
YELLOW_THRESHOLD = 0.60
STALENESS_DAYS = 90

# ════════════════════════════════════════════════════════════════════
# CALLER ID — SalesMsg Monitored Lines (Phase 2)
# ════════════════════════════════════════════════════════════════════

# Set to False to disable the Caller ID feature entirely
CALLER_ID_ENABLED = True

# Sales lines wired into the Caller ID feature
SALESMSG_LINE_MAP = {
    "+16159815481": {"name": "Annika Owens",                   "type": "individual"},
    "+16158561187": {"name": "Cameron Creasy",                 "type": "individual"},
    "+16153510574": {"name": "Mary Topp",                      "type": "individual"},
    "+16158299263": {"name": "Cassidy Wind",                   "type": "individual"},
    "+16293006080": {"name": "Katie Bradley (Primary)",        "type": "individual"},
    "+16157958110": {"name": "Katie Bradley (Secondary)",      "type": "individual"},
    "+16153696474": {"name": "Infinity Hospitality Main Line", "type": "shared"},
    "+16155585718": {"name": "Infinity Sales",                 "type": "shared"},
}


def normalize_phone(phone: str) -> str:
    """
    Normalize a phone number to E.164 format (+1XXXXXXXXXX).
    Handles: (615) 555-0000, 6155550000, +16155550000, 16155550000
    """
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return f"+{digits}"
