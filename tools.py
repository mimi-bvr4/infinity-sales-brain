"""
Sales Brain — Tool Functions
These are the functions Claude calls via tool_use when answering sales team queries.
Each function maps to a real API (Google Calendar, HubSpot, Gmail).
"""

import json
import os
import datetime
import requests
from typing import Optional
from config import (
    VENUE_CALENDARS, DOWNTOWN_VENUES, WHOLE_VENUE, TBB_SPACES,
    ESCALATION_GROUP, SALES_BRAIN_EMAIL, CONTEXT_FILE, UPDATE_LOG,
    HUBSPOT_API_KEY
)

# ════════════════════════════════════════════════════════════════════
# TOOL DEFINITIONS — passed to Claude API as tools[]
# ════════════════════════════════════════════════════════════════════

TOOL_DEFINITIONS = [
    {
        "name": "check_date_availability",
        "description": (
            "Check whether a specific date is available at a specific venue. "
            "Performs the two-fold verification protocol: Check 1 (primary date query) "
            "and Check 2 (±1 day context window for multi-day events, lodging, prep). "
            "Returns all events found on the date and adjacent days, plus an availability assessment. "
            "For TBB, also checks which specific spaces are booked vs. open. "
            "For downtown venues (TBB, TBT), also cross-checks Holidays/Lot R/Titans calendar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "venue": {
                    "type": "string",
                    "enum": ["TBB", "TBT", "ECD", "SWF"],
                    "description": "Venue code to check"
                },
                "date": {
                    "type": "string",
                    "description": "Date to check in YYYY-MM-DD format"
                }
            },
            "required": ["venue", "date"]
        }
    },
    {
        "name": "list_open_dates",
        "description": (
            "List all open dates for a specific day-of-week at a specific venue over a date range. "
            "For example: 'all open Saturdays at ECD in 2027'. "
            "Performs both Check 1 and Check 2 for every date. "
            "Returns two lists: OPEN dates and BOOKED dates (with event names). "
            "Always includes disclaimer: 'Based on calendar data as of [today]. Please verify before presenting to clients.'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "venue": {
                    "type": "string",
                    "enum": ["TBB", "TBT", "ECD", "SWF"],
                    "description": "Venue code to check"
                },
                "day_of_week": {
                    "type": "string",
                    "enum": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                    "description": "Day of week to list"
                },
                "start_date": {
                    "type": "string",
                    "description": "Start of range in YYYY-MM-DD format"
                },
                "end_date": {
                    "type": "string",
                    "description": "End of range in YYYY-MM-DD format"
                }
            },
            "required": ["venue", "day_of_week", "start_date", "end_date"]
        }
    },
    {
        "name": "lookup_contact",
        "description": (
            "Search HubSpot for a contact by name, email, or phone number. "
            "Returns contact properties including associated deals, venue interest, event date, and owner."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Name, email, or phone number to search for"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "lookup_deal",
        "description": (
            "Search HubSpot for a deal by client name, event date, or deal name. "
            "Returns deal stage, associated contacts, venue, event type, and payment status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Client name, event date, or deal name to search for"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "send_escalation",
        "description": (
            "Send an escalation email to the leadership group (Nathaniel, Mary, Kevin). "
            "Used for YELLOW (answer + flag) and RED (no answer, full escalation) scenarios. "
            "The sales team member who asked is automatically CC'd. "
            "Email includes the original question, who asked, context, and the Brain's tentative answer (if YELLOW)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {
                    "type": "string",
                    "enum": ["YELLOW", "RED"],
                    "description": "Escalation level — YELLOW (answer+flag) or RED (full escalation)"
                },
                "question": {
                    "type": "string",
                    "description": "The original question from the sales team member"
                },
                "asker_name": {
                    "type": "string",
                    "description": "Name of the sales team member who asked"
                },
                "asker_email": {
                    "type": "string",
                    "description": "Email of the sales team member (will be CC'd)"
                },
                "tentative_answer": {
                    "type": "string",
                    "description": "The Brain's best answer (for YELLOW) or empty string (for RED)"
                },
                "context": {
                    "type": "string",
                    "description": "Additional context about why the Brain is uncertain or can't answer"
                }
            },
            "required": ["level", "question", "asker_name", "asker_email", "context"]
        }
    },
    {
        "name": "book_date",
        "description": (
            "Create a calendar event to book a date at a specific venue. "
            "Used when the sales team confirms a booking (e.g., 'We just booked 10.26.27 at ECD, Smith.Johnson Wedding'). "
            "Automatically formats the event name using IHG naming conventions: MM.DD.YY VENUE Name Event Type. "
            "Runs a pre-check to verify the date is actually open before booking. "
            "For TBB, specify which space (BBC, BBD, BBO, etc.). "
            "For ECD with lodging, append +M (mansion) or +M+GH (mansion + gatehouses). "
            "Returns confirmation with event details and a link to the calendar event."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "venue": {
                    "type": "string",
                    "enum": ["TBB", "TBT", "ECD", "SWF"],
                    "description": "Venue code"
                },
                "space": {
                    "type": "string",
                    "description": (
                        "For TBB: BBC, BBD, BBO, BBC+D, BBC+O, BBD+O, or TBB (entire venue). "
                        "For ECD: ECD, ECD+M (with mansion lodging), or ECD+M+GH (mansion + gatehouses). "
                        "For TBT/SWF: leave empty."
                    ),
                    "default": ""
                },
                "date": {
                    "type": "string",
                    "description": "Event date in YYYY-MM-DD format"
                },
                "event_name": {
                    "type": "string",
                    "description": (
                        "Client/event name portion. Examples: 'Smith.Johnson Wedding', "
                        "'Amazon Holiday Party', 'Johnson Birthday Party'. "
                        "The tool prepends the MM.DD.YY VENUE prefix automatically."
                    )
                },
                "start_time": {
                    "type": "string",
                    "description": (
                        "Event start time in HH:MM format (24hr). "
                        "Defaults based on venue: TBB/TBT=09:00, ECD Mon-Thu/Sun=14:00, ECD Fri-Sat=09:00, SWF=09:00"
                    ),
                    "default": ""
                },
                "end_time": {
                    "type": "string",
                    "description": (
                        "Event end time in HH:MM format (24hr). "
                        "Defaults based on venue: TBB/TBT=00:00 (midnight), ECD=23:00, SWF=23:00"
                    ),
                    "default": ""
                },
                "all_day": {
                    "type": "boolean",
                    "description": "Create as all-day event instead of timed. Default false.",
                    "default": False
                },
                "notes": {
                    "type": "string",
                    "description": "Optional notes for the event description (e.g., guest count, special requirements)",
                    "default": ""
                }
            },
            "required": ["venue", "date", "event_name"]
        }
    },
    {
        "name": "get_venue_pricing",
        "description": (
            "Look up venue pricing for a specific venue, day-of-week, season, and time slot. "
            "Returns the exact rate from the Pricing Guide. "
            "Peak Season: April-June, September-December. Off-Peak: January-March, July-August."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "venue": {
                    "type": "string",
                    "enum": ["TBB", "TBT", "ECD", "SWF"],
                    "description": "Venue code"
                },
                "space": {
                    "type": "string",
                    "description": "For TBB: BBC, BBD, BBO, BBD+O, or Entire. For others: leave empty.",
                    "default": ""
                },
                "day": {
                    "type": "string",
                    "description": "Day of week or category: Mon-Thu, Friday, Saturday, Sunday"
                },
                "season": {
                    "type": "string",
                    "enum": ["peak", "off-peak"],
                    "description": "Peak (Apr-Jun, Sep-Dec) or Off-Peak (Jan-Mar, Jul-Aug)"
                },
                "time_slot": {
                    "type": "string",
                    "enum": ["morning", "evening", "all_day"],
                    "description": "Morning, Evening, or All Day"
                }
            },
            "required": ["venue", "day", "season", "time_slot"]
        }
    }
]


# ════════════════════════════════════════════════════════════════════
# TOOL IMPLEMENTATIONS
# ════════════════════════════════════════════════════════════════════

import os

# Cache the calendar service so we don't re-auth on every tool call
_calendar_service_cache = None


def get_calendar_service():
    """
    Returns an authenticated Google Calendar API service.
    Checks (in order):
      1. GOOGLE_SERVICE_ACCOUNT_JSON env var (raw JSON — best for Render/Railway)
      2. GOOGLE_SERVICE_ACCOUNT_KEY env var (path to .json file)
      3. token.json file in app directory (OAuth — for local dev)
    """
    global _calendar_service_cache
    if _calendar_service_cache is not None:
        return _calendar_service_cache

    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    try:
        from googleapiclient.discovery import build

        # Option 1: Service account JSON in env var (deployment)
        sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if sa_json:
            from google.oauth2 import service_account
            import json as _json
            info = _json.loads(sa_json)
            creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
            _calendar_service_cache = build("calendar", "v3", credentials=creds)
            return _calendar_service_cache

        # Option 2: Service account key file
        sa_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY", "")
        if sa_path and os.path.exists(sa_path):
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_file(sa_path, scopes=SCOPES)
            _calendar_service_cache = build("calendar", "v3", credentials=creds)
            return _calendar_service_cache

        # Option 3: OAuth token file (local dev)
        from google.oauth2.credentials import Credentials
        token_path = os.environ.get("GOOGLE_TOKEN_PATH",
                                     os.path.join(os.path.dirname(__file__), "token.json"))
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)

            # Auto-refresh expired tokens
            if creds and creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
                with open(token_path, "w") as f:
                    f.write(creds.to_json())

            if creds and creds.valid:
                _calendar_service_cache = build("calendar", "v3", credentials=creds)
                return _calendar_service_cache

        return None
    except Exception as e:
        print(f"Calendar auth error: {e}")
        return None

def _query_calendar_events(calendar_id: str, date_str: str) -> list:
    """Query Google Calendar for all events on a specific date."""
    service = get_calendar_service()
    if not service:
        return [{"error": "Google Calendar not connected. Please set up authentication."}]

    date = datetime.date.fromisoformat(date_str)
    time_min = f"{date}T00:00:00-06:00"  # CT timezone
    time_max = f"{date}T23:59:59-06:00"

    try:
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        events = events_result.get("items", [])
        return [
            {
                "summary": e.get("summary", "Untitled"),
                "start": e.get("start", {}).get("dateTime", e.get("start", {}).get("date", "")),
                "end": e.get("end", {}).get("dateTime", e.get("end", {}).get("date", "")),
                "all_day": "date" in e.get("start", {}),
            }
            for e in events
        ]
    except Exception as e:
        return [{"error": f"Calendar query failed: {str(e)}"}]


def _parse_tbb_space(event_summary: str) -> str:
    """Extract TBB space prefix from event name."""
    summary_upper = event_summary.upper().strip()
    # Check multi-space combos first (longest match)
    for prefix in ["BBC+D", "BBC+O", "BBD+O", "TBB ENTIRE", "TBB"]:
        if summary_upper.startswith(prefix):
            return prefix.replace("TBB ENTIRE", "TBB")
    for prefix in ["BBC", "BBD", "BBO"]:
        if summary_upper.startswith(prefix):
            return prefix
    return "UNKNOWN"


def check_date_availability(venue: str, date: str) -> dict:
    """
    Two-fold date availability check.
    Check 1: Primary date query
    Check 2: ±1 day context window
    """
    venue = venue.upper()
    cal_info = VENUE_CALENDARS.get(venue)
    if not cal_info:
        return {"error": f"Unknown venue: {venue}"}

    target_date = datetime.date.fromisoformat(date)
    prev_date = (target_date - datetime.timedelta(days=1)).isoformat()
    next_date = (target_date + datetime.timedelta(days=1)).isoformat()

    # CHECK 1: Primary date
    primary_events = _query_calendar_events(cal_info["calendar_id"], date)

    # CHECK 2: Context window (±1 day)
    prev_events = _query_calendar_events(cal_info["calendar_id"], prev_date)
    next_events = _query_calendar_events(cal_info["calendar_id"], next_date)

    # Cross-check downtown venues against Holidays/Lot R/Titans
    downtown_events = []
    if venue in DOWNTOWN_VENUES:
        holidays_cal = VENUE_CALENDARS["HOLIDAYS"]["calendar_id"]
        downtown_events = _query_calendar_events(holidays_cal, date)

    # Assess availability
    has_errors = any("error" in e for e in primary_events)
    if has_errors:
        status = "ERROR"
        assessment = "Could not query calendar. " + primary_events[0].get("error", "")
    elif not primary_events:
        # Check if adjacent events span into this date
        spanning = False
        for e in prev_events + next_events:
            if "error" not in e and e.get("all_day"):
                spanning = True
                break
        if spanning:
            status = "REVIEW_NEEDED"
            assessment = (
                f"No events on {date}, but adjacent days have all-day events. "
                "Verify no multi-day bookings span into this date."
            )
        else:
            status = "OPEN"
            assessment = f"No events found on {date} at {venue}. Date appears open."
    else:
        # Events exist — analyze what's booked
        if venue == "TBB":
            booked_spaces = set()
            for e in primary_events:
                if "error" not in e:
                    space = _parse_tbb_space(e.get("summary", ""))
                    booked_spaces.add(space)

            if "TBB" in booked_spaces:
                status = "BOOKED"
                assessment = f"Entire venue booked on {date}."
            else:
                all_spaces = {"BBC", "BBD", "BBO"}
                open_spaces = all_spaces - booked_spaces
                if open_spaces:
                    status = "PARTIALLY_BOOKED"
                    assessment = (
                        f"Spaces booked: {', '.join(sorted(booked_spaces))}. "
                        f"Potentially open: {', '.join(sorted(open_spaces))}. "
                        "Sales team should verify feasibility of split-day booking."
                    )
                else:
                    status = "BOOKED"
                    assessment = f"All TBB spaces booked on {date}."
        else:
            status = "BOOKED"
            event_names = [e.get("summary", "Untitled") for e in primary_events if "error" not in e]
            assessment = f"{venue} is booked on {date}: {', '.join(event_names)}"

    # ECD-specific: check for lodging flags on adjacent days
    ecd_lodging_note = ""
    if venue == "ECD":
        for e in prev_events:
            if "error" not in e and ("+M" in e.get("summary", "") or "+GH" in e.get("summary", "")):
                ecd_lodging_note = (
                    f"⚠️ Previous day ({prev_date}) has lodging event: {e['summary']}. "
                    "Mansion/guesthouses may still be occupied on morning of requested date."
                )
                break

    result = {
        "venue": venue,
        "date": date,
        "day_of_week": target_date.strftime("%A"),
        "status": status,
        "assessment": assessment,
        "primary_events": [e for e in primary_events if "error" not in e],
        "previous_day_events": [e for e in prev_events if "error" not in e],
        "next_day_events": [e for e in next_events if "error" not in e],
        "downtown_flags": downtown_events if downtown_events else [],
        "ecd_lodging_note": ecd_lodging_note,
        "disclaimer": f"Based on calendar data as of {datetime.date.today()}. Sales team should verify before presenting to any client."
    }

    return result


def list_open_dates(venue: str, day_of_week: str, start_date: str, end_date: str) -> dict:
    """List all open instances of a specific day-of-week at a venue over a range."""
    venue = venue.upper()
    cal_info = VENUE_CALENDARS.get(venue)
    if not cal_info:
        return {"error": f"Unknown venue: {venue}"}

    day_map = {
        "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
        "Friday": 4, "Saturday": 5, "Sunday": 6
    }
    target_weekday = day_map.get(day_of_week)
    if target_weekday is None:
        return {"error": f"Invalid day of week: {day_of_week}"}

    start = datetime.date.fromisoformat(start_date)
    end = datetime.date.fromisoformat(end_date)

    # Find all target days in range
    dates_to_check = []
    current = start
    while current <= end:
        if current.weekday() == target_weekday:
            dates_to_check.append(current)
        current += datetime.timedelta(days=1)

    open_dates = []
    booked_dates = []

    for d in dates_to_check:
        result = check_date_availability(venue, d.isoformat())
        if result.get("status") == "OPEN":
            open_dates.append(d.isoformat())
        elif result.get("status") == "PARTIALLY_BOOKED":
            booked_dates.append({
                "date": d.isoformat(),
                "status": "PARTIALLY_BOOKED",
                "details": result.get("assessment", "")
            })
        else:
            event_names = [e.get("summary", "?") for e in result.get("primary_events", [])]
            booked_dates.append({
                "date": d.isoformat(),
                "status": result.get("status", "BOOKED"),
                "details": ", ".join(event_names) if event_names else result.get("assessment", "")
            })

    return {
        "venue": venue,
        "day_of_week": day_of_week,
        "range": f"{start_date} to {end_date}",
        "total_dates_checked": len(dates_to_check),
        "open_count": len(open_dates),
        "open_dates": open_dates,
        "booked_count": len(booked_dates),
        "booked_dates": booked_dates,
        "disclaimer": f"📋 Based on calendar data as of {datetime.date.today()}. Please verify before presenting to clients."
    }


def lookup_contact(query: str) -> dict:
    """Search HubSpot for a contact by name, email, or phone."""
    if not HUBSPOT_API_KEY:
        return {"error": "HubSpot API key not configured. Set HUBSPOT_API_KEY in Railway Variables."}

    HUBSPOT_BASE = "https://api.hubapi.com"
    headers = {
        "Authorization": f"Bearer {HUBSPOT_API_KEY}",
        "Content-Type": "application/json"
    }
    properties = [
        "firstname", "lastname", "email", "phone", "company",
        "lifecyclestage", "hs_lead_status", "hubspot_owner_id",
        "notes_last_updated", "createdate"
    ]

    # Determine if query looks like email, phone, or name
    query_clean = query.strip()
    if "@" in query_clean:
        # Email search — exact match
        filter_groups = [{"filters": [
            {"propertyName": "email", "operator": "EQ", "value": query_clean}
        ]}]
    elif query_clean.replace("-", "").replace("(", "").replace(")", "").replace(" ", "").replace("+", "").isdigit():
        # Phone search
        filter_groups = [{"filters": [
            {"propertyName": "phone", "operator": "CONTAINS_TOKEN", "value": query_clean}
        ]}]
    else:
        # Name search — split into first/last if possible, otherwise search both
        parts = query_clean.split(None, 1)
        if len(parts) == 2:
            filter_groups = [{"filters": [
                {"propertyName": "firstname", "operator": "CONTAINS_TOKEN", "value": f"*{parts[0]}*"},
                {"propertyName": "lastname", "operator": "CONTAINS_TOKEN", "value": f"*{parts[1]}*"}
            ]}]
        else:
            # Single term — search first OR last name
            filter_groups = [
                {"filters": [{"propertyName": "firstname", "operator": "CONTAINS_TOKEN", "value": f"*{query_clean}*"}]},
                {"filters": [{"propertyName": "lastname", "operator": "CONTAINS_TOKEN", "value": f"*{query_clean}*"}]}
            ]

    body = {
        "filterGroups": filter_groups,
        "properties": properties,
        "limit": 5
    }

    try:
        resp = requests.post(f"{HUBSPOT_BASE}/crm/v3/objects/contacts/search", headers=headers, json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.HTTPError as e:
        return {"error": f"HubSpot API error: {e.response.status_code} — {e.response.text[:200]}"}
    except Exception as e:
        return {"error": f"HubSpot connection failed: {str(e)}"}

    results = data.get("results", [])
    if not results:
        return {"query": query, "results": [], "message": f"No contacts found matching '{query}'."}

    contacts = []
    for r in results:
        props = r.get("properties", {})
        contacts.append({
            "id": r.get("id"),
            "name": f"{props.get('firstname', '')} {props.get('lastname', '')}".strip(),
            "email": props.get("email", ""),
            "phone": props.get("phone", ""),
            "company": props.get("company", ""),
            "lifecycle_stage": props.get("lifecyclestage", ""),
            "lead_status": props.get("hs_lead_status", ""),
            "created": props.get("createdate", "")
        })

    return {
        "query": query,
        "total_found": data.get("total", len(results)),
        "results": contacts
    }


def lookup_deal(query: str) -> dict:
    """Search HubSpot for a deal by client name, event date, or deal name."""
    if not HUBSPOT_API_KEY:
        return {"error": "HubSpot API key not configured. Set HUBSPOT_API_KEY in Railway Variables."}

    HUBSPOT_BASE = "https://api.hubapi.com"
    headers = {
        "Authorization": f"Bearer {HUBSPOT_API_KEY}",
        "Content-Type": "application/json"
    }
    properties = [
        "dealname", "dealstage", "amount", "closedate",
        "pipeline", "hubspot_owner_id", "createdate",
        "hs_lastmodifieddate", "notes_last_updated"
    ]

    query_clean = query.strip()

    # Search deal name with CONTAINS_TOKEN
    filter_groups = [
        {"filters": [{"propertyName": "dealname", "operator": "CONTAINS_TOKEN", "value": f"*{query_clean}*"}]}
    ]

    body = {
        "filterGroups": filter_groups,
        "properties": properties,
        "limit": 5
    }

    try:
        resp = requests.post(f"{HUBSPOT_BASE}/crm/v3/objects/deals/search", headers=headers, json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.HTTPError as e:
        return {"error": f"HubSpot API error: {e.response.status_code} — {e.response.text[:200]}"}
    except Exception as e:
        return {"error": f"HubSpot connection failed: {str(e)}"}

    results = data.get("results", [])
    if not results:
        return {"query": query, "results": [], "message": f"No deals found matching '{query}'."}

    deals = []
    for r in results:
        props = r.get("properties", {})
        deals.append({
            "id": r.get("id"),
            "deal_name": props.get("dealname", ""),
            "stage": props.get("dealstage", ""),
            "amount": props.get("amount", ""),
            "close_date": props.get("closedate", ""),
            "pipeline": props.get("pipeline", ""),
            "created": props.get("createdate", ""),
            "last_modified": props.get("hs_lastmodifieddate", "")
        })

    return {
        "query": query,
        "total_found": data.get("total", len(results)),
        "results": deals
    }


def _get_gmail_service():
    """
    Returns an authenticated Gmail API service using domain-wide delegation.
    The service account impersonates salesbrain@infinityhospitality.net to send emails.
    """
    try:
        from googleapiclient.discovery import build
        GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

        # Option 1: Service account JSON in env var (deployment)
        sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if sa_json:
            from google.oauth2 import service_account
            import json as _json
            info = _json.loads(sa_json)
            creds = service_account.Credentials.from_service_account_info(info, scopes=GMAIL_SCOPES)
            delegated = creds.with_subject(SALES_BRAIN_EMAIL)
            return build("gmail", "v1", credentials=delegated)

        # Option 2: Service account key file
        sa_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY", "")
        if sa_path and os.path.exists(sa_path):
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_file(sa_path, scopes=GMAIL_SCOPES)
            delegated = creds.with_subject(SALES_BRAIN_EMAIL)
            return build("gmail", "v1", credentials=delegated)

        return None
    except Exception as e:
        print(f"Gmail auth error: {e}")
        return None


def _build_email(to_list: list, cc_list: list, subject: str, body_html: str, from_email: str) -> str:
    """Build a MIME email message encoded for the Gmail API."""
    import base64
    from email.mime.text import MIMEText

    msg = MIMEText(body_html, "html")
    msg["From"] = f"Sales Brain <{from_email}>"
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    msg["Subject"] = subject
    msg["Reply-To"] = from_email

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    return raw


def send_escalation(
    level: str,
    question: str,
    asker_name: str,
    asker_email: str,
    context: str,
    tentative_answer: str = ""
) -> dict:
    """
    Send an escalation email to the leadership group via Gmail API.
    YELLOW: answer + flag for review
    RED: full escalation, no confident answer
    Falls back to 'prepared but not sent' if Gmail is not connected.
    """
    emoji = "🟡" if level == "YELLOW" else "🔴"
    subject = f"{emoji} Sales Brain Escalation — {question[:60]}"

    to_list = [m["email"] for m in ESCALATION_GROUP]
    cc_list = [asker_email] if asker_email else []

    # Build HTML email body
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M CT")

    if tentative_answer:
        answer_section = f"""
        <div style="background:#fff8e1;border-left:4px solid #ffc107;padding:12px;margin:16px 0;">
            <strong>Brain's Tentative Answer:</strong><br>{tentative_answer}
        </div>
        <p><em>This answer was delivered to the sales team member with a yellow confidence indicator. Please confirm or correct.</em></p>
        """
    else:
        answer_section = """
        <div style="background:#ffebee;border-left:4px solid #f44336;padding:12px;margin:16px 0;">
            <strong>The Brain could not provide a confident answer for this question.</strong>
        </div>
        <p><em>Please reply with the correct answer.</em></p>
        """

    body_html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;">
        <div style="background:{'#fff8e1' if level == 'YELLOW' else '#ffebee'};padding:16px;border-radius:8px 8px 0 0;">
            <h2 style="margin:0;">{emoji} {level} Escalation</h2>
        </div>
        <div style="padding:16px;border:1px solid #ddd;border-top:none;">
            <table style="width:100%;border-collapse:collapse;">
                <tr><td style="padding:4px 8px;color:#666;">Asked by:</td><td style="padding:4px 8px;"><strong>{asker_name}</strong> ({asker_email})</td></tr>
                <tr><td style="padding:4px 8px;color:#666;">Date/Time:</td><td style="padding:4px 8px;">{timestamp}</td></tr>
            </table>

            <div style="background:#f5f5f5;padding:12px;margin:16px 0;border-radius:4px;">
                <strong>Question:</strong><br>{question}
            </div>

            <p><strong>Context:</strong> {context}</p>

            {answer_section}

            <hr style="border:none;border-top:2px solid #1a237e;margin:24px 0;">

            <p><strong>When you reply, please indicate:</strong></p>
            <p>✅ <strong>LEARN</strong> — Add this answer to the Sales Brain's permanent knowledge</p>
            <p>⛔ <strong>DON'T LEARN</strong> — Log this answer but do NOT add to permanent knowledge (one-off exception)</p>
            <p style="color:#666;font-size:12px;">Default: DON'T LEARN. Only mark LEARN if this should become standard knowledge.</p>

            <hr style="border:none;border-top:1px solid #ddd;margin:16px 0;">
            <p style="color:#999;font-size:11px;">Sent by Infinity Hospitality Sales Brain | Powered by Claude</p>
        </div>
    </div>
    """

    # Try to send via Gmail API
    gmail_service = _get_gmail_service()
    if gmail_service:
        try:
            raw_message = _build_email(to_list, cc_list, subject, body_html, SALES_BRAIN_EMAIL)
            sent = gmail_service.users().messages().send(
                userId="me",
                body={"raw": raw_message}
            ).execute()

            return {
                "status": "escalation_sent",
                "level": level,
                "message_id": sent.get("id", ""),
                "from": SALES_BRAIN_EMAIL,
                "to": to_list,
                "cc": cc_list,
                "subject": subject,
                "note": f"Escalation email sent successfully via Gmail API. Message ID: {sent.get('id', '')}"
            }
        except Exception as e:
            # Gmail send failed — return the prepared email so Claude can report the failure
            return {
                "status": "escalation_send_failed",
                "level": level,
                "error": str(e),
                "from": SALES_BRAIN_EMAIL,
                "to": to_list,
                "cc": cc_list,
                "subject": subject,
                "note": f"Gmail API send failed: {str(e)}. Email was prepared but not delivered."
            }
    else:
        # No Gmail connection — return prepared email
        return {
            "status": "escalation_prepared",
            "level": level,
            "from": SALES_BRAIN_EMAIL,
            "to": to_list,
            "cc": cc_list,
            "subject": subject,
            "note": "Gmail API not connected. Email prepared but not sent. Set up domain-wide delegation to enable sending."
        }


def book_date(
    venue: str,
    date: str,
    event_name: str,
    space: str = "",
    start_time: str = "",
    end_time: str = "",
    all_day: bool = False,
    notes: str = ""
) -> dict:
    """
    Create a calendar event to book a date at a venue.
    Pre-checks availability, formats the name per IHG conventions, and creates the event.
    """
    venue = venue.upper()
    cal_info = VENUE_CALENDARS.get(venue)
    if not cal_info:
        return {"error": f"Unknown venue: {venue}"}

    service = get_calendar_service()
    if not service:
        return {"error": "Google Calendar not connected. Cannot create events."}

    target_date = datetime.date.fromisoformat(date)

    # ── Pre-check: Is this date actually open? ──────────────────
    availability = check_date_availability(venue, date)
    status = availability.get("status", "")

    if status == "BOOKED":
        return {
            "status": "BLOCKED",
            "message": f"Cannot book — {venue} is already booked on {date}.",
            "existing_events": availability.get("primary_events", []),
            "suggestion": "Check adjacent dates or another venue."
        }
    elif status == "ERROR":
        return {
            "status": "ERROR",
            "message": "Could not verify availability. Please check the calendar manually before booking.",
            "details": availability.get("assessment", "")
        }

    # If PARTIALLY_BOOKED at TBB, warn but allow (they might be booking an open space)
    partial_warning = ""
    if status == "PARTIALLY_BOOKED":
        partial_warning = (
            f"⚠️ {venue} is partially booked on {date}. "
            f"{availability.get('assessment', '')} "
            "Verify the requested space is actually available."
        )

    # ── Build event name per IHG naming convention ──────────────
    # Format: MM.DD.YY VENUE Name Event Type
    date_prefix = target_date.strftime("%m.%d.%y")

    # Determine the venue/space prefix for the event name
    if venue == "TBB":
        if space and space.upper() == "TBB":
            space_prefix = "TBB ENTIRE VENUE"  # All floors booked — blocks BBC, BBD, BBO
        elif space:
            space_prefix = space.upper()  # Individual space: BBC, BBD, BBO, BBC+D, etc.
        else:
            space_prefix = "TBB ENTIRE VENUE"  # Default to entire venue if no space specified
    elif venue == "ECD" and space:
        space_prefix = space.upper()  # ECD, ECD+M, ECD+M+GH
    else:
        space_prefix = venue

    full_event_name = f"{date_prefix} {space_prefix} {event_name}"

    # ── Determine start/end times ───────────────────────────────
    day_of_week = target_date.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun

    if not start_time:
        if venue == "ECD" and day_of_week in (0, 1, 2, 3, 6):  # Mon-Thu, Sun
            start_time = "14:00"
        else:
            start_time = "09:00"

    if not end_time:
        if venue in ("TBB", "TBT"):
            end_time = "23:59"  # Midnight-ish (midnight = next day)
        elif venue == "ECD":
            end_time = "23:00"
        else:  # SWF
            end_time = "23:00"

    # ── Build calendar event ────────────────────────────────────
    description_lines = [
        f"Booked via Sales Brain on {datetime.date.today().isoformat()}",
    ]
    if notes:
        description_lines.append(f"Notes: {notes}")
    if partial_warning:
        description_lines.append(partial_warning)

    if all_day:
        event_body = {
            "summary": full_event_name,
            "description": "\n".join(description_lines),
            "start": {"date": date},
            "end": {"date": (target_date + datetime.timedelta(days=1)).isoformat()},
        }
    else:
        event_body = {
            "summary": full_event_name,
            "description": "\n".join(description_lines),
            "start": {
                "dateTime": f"{date}T{start_time}:00",
                "timeZone": "America/Chicago",
            },
            "end": {
                "dateTime": f"{date}T{end_time}:00",
                "timeZone": "America/Chicago",
            },
        }

    # ── Create the event ────────────────────────────────────────
    try:
        created_event = service.events().insert(
            calendarId=cal_info["calendar_id"],
            body=event_body,
        ).execute()

        return {
            "status": "BOOKED",
            "message": f"✅ {full_event_name} — booked successfully!",
            "event_id": created_event.get("id", ""),
            "event_link": created_event.get("htmlLink", ""),
            "calendar": cal_info["name"],
            "event_name": full_event_name,
            "date": date,
            "day_of_week": target_date.strftime("%A"),
            "start": start_time if not all_day else "All day",
            "end": end_time if not all_day else "All day",
            "partial_warning": partial_warning,
            "disclaimer": "Event created in Google Calendar. Verify in HubSpot and Bento as part of standard booking workflow."
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"Failed to create calendar event: {str(e)}",
            "attempted_name": full_event_name,
        }


def get_venue_pricing(venue: str, day: str, season: str, time_slot: str, space: str = "") -> dict:
    """
    Look up pricing from the embedded pricing grid.
    This is a pure knowledge lookup — no API call needed.
    The Brain has the full pricing grid in its context, so this tool
    just provides structured access for programmatic queries.
    """
    # The actual pricing data is in Sales_Brain_Context.md which is loaded as system prompt.
    # This tool signals to Claude to look up the specific combination from its context.
    return {
        "tool": "pricing_lookup",
        "venue": venue,
        "space": space,
        "day": day,
        "season": season,
        "time_slot": time_slot,
        "note": "Pricing data is in the Sales Brain context. Look up the exact rate from the pricing grid."
    }


# ════════════════════════════════════════════════════════════════════
# TOOL DISPATCH — maps tool names to functions
# ════════════════════════════════════════════════════════════════════

TOOL_DISPATCH = {
    "check_date_availability": check_date_availability,
    "list_open_dates": list_open_dates,
    "book_date": book_date,
    "lookup_contact": lookup_contact,
    "lookup_deal": lookup_deal,
    "send_escalation": send_escalation,
    "get_venue_pricing": get_venue_pricing,
}


def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool by name and return JSON result."""
    func = TOOL_DISPATCH.get(tool_name)
    if not func:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        result = func(**tool_input)
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": f"Tool execution failed: {str(e)}"})
