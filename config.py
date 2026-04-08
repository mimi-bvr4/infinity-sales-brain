"""
Sales Brain — Configuration
All API keys, calendar IDs, and escalation contacts in one place.
"""

import os

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

# ── HubSpot ────────────────────────────────────────────────────────
HUBSPOT_API_KEY = os.environ.get("HUBSPOT_API_KEY", "")

# ── Paths ──────────────────────────────────────────────────────────
CONTEXT_FILE = os.path.join(os.path.dirname(__file__), "..", "Sales_Brain_Context.md")
UPDATE_LOG = os.path.join(os.path.dirname(__file__), "..", "Sales_Brain_Update_Log.md")

# ── Confidence thresholds ──────────────────────────────────────────
GREEN_THRESHOLD = 0.90
YELLOW_THRESHOLD = 0.60
STALENESS_DAYS = 90
