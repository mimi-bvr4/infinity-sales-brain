"""
Sales Brain — SalesMsg Caller ID Feature
Flask Blueprint: listens for inbound SalesMsg calls, looks up the caller
in HubSpot, and surfaces the profile in the Sales Brain UI.

READ-ONLY. Never writes to HubSpot or SalesMsg.
Toggle on/off via CALLER_ID_ENABLED in config.py.

Phase 2 feature — see Sales_Brain_SalesMsg_Caller_ID_Build.md
"""

import json
from flask import Blueprint, request, jsonify
from config import SALESMSG_LINE_MAP, normalize_phone
from hubspot_oauth import hubspot_api, is_connected

# ── Blueprint ──────────────────────────────────────────────────────
caller_id_bp = Blueprint("caller_id", __name__)

# ── In-memory call store ───────────────────────────────────────────
# Keyed by normalized called line number (e.g. "+16159815481")
# Cleared on dismiss or redeploy — intentional, calls are transient
active_calls = {}

# ── Accepted inbound call event names ─────────────────────────────
INBOUND_CALL_EVENTS = {"call.received", "call.inbound_started"}


# ════════════════════════════════════════════════════════════════════
# ROUTES
# ════════════════════════════════════════════════════════════════════

@caller_id_bp.route("/webhook/salesmsg", methods=["POST"])
def salesmsg_webhook():
    """
    Receives inbound call webhook from SalesMsg.
    SalesMsg expects a fast 200 — all HubSpot work happens synchronously
    but is quick enough (single contact lookup) to be fine here.
    """
    data = request.json or {}

    # Debug: log raw payload to confirm field names on first calls
    print(f"[caller_id] SalesMsg webhook received: {json.dumps(data)}")

    event_type = data.get("event") or data.get("type") or data.get("event_type", "")
    called_number = data.get("to_number") or data.get("called_number") or data.get("to", "")
    caller_number = data.get("from_number") or data.get("caller_number") or data.get("from", "")

    # Only handle inbound call events
    if event_type not in INBOUND_CALL_EVENTS:
        return jsonify({"status": "ignored", "reason": f"unhandled event type: {event_type}"}), 200

    # Only handle monitored sales lines
    normalized_called = normalize_phone(called_number)
    line_info = SALESMSG_LINE_MAP.get(normalized_called)
    if not line_info:
        return jsonify({"status": "ignored", "reason": "unmonitored line"}), 200

    # Look up caller in HubSpot
    normalized_caller = normalize_phone(caller_number)
    profile = _get_caller_profile(normalized_caller)
    profile["line"] = line_info["name"]
    profile["line_type"] = line_info["type"]
    profile["called_number"] = normalized_called

    active_calls[normalized_called] = profile
    print(f"[caller_id] Active call stored for {line_info['name']} — caller: {normalized_caller} — found: {profile.get('found')}")

    return jsonify({"status": "ok"}), 200


@caller_id_bp.route("/api/caller-status", methods=["GET"])
def caller_status():
    """
    Polled by the browser every 3 seconds.
    Optional ?line= param for individual lines (normalized E.164).
    Returns active call profile or {"active": false}.
    """
    line = request.args.get("line")
    if line:
        normalized = normalize_phone(line)
        if normalized in active_calls:
            return jsonify({"active": True, "profile": active_calls[normalized]})
    # No line param, or line not active — return any active call (shared line support)
    if active_calls:
        profile = next(iter(active_calls.values()))
        return jsonify({"active": True, "profile": profile})
    return jsonify({"active": False})


@caller_id_bp.route("/api/caller-dismiss", methods=["POST"])
def caller_dismiss():
    """Called when salesperson clicks Clear. Removes entry from active_calls."""
    data = request.json or {}
    line = data.get("line")
    if line:
        normalized = normalize_phone(line)
        active_calls.pop(normalized, None)
    else:
        active_calls.clear()
    return jsonify({"status": "cleared"})


# ════════════════════════════════════════════════════════════════════
# HUBSPOT CALLER PROFILE LOOKUP
# ════════════════════════════════════════════════════════════════════

def _get_caller_profile(phone_number: str) -> dict:
    """
    Look up a phone number in HubSpot and return a full caller profile.
    Returns a dict with contact, deal, notes, last call.
    Never raises — returns found=False with error note on any failure.
    """
    profile = {
        "phone": phone_number,
        "found": False,
        "contact": None,
        "deal": None,
        "notes": [],
        "last_call": None,
        "last_email": None,
        "error": None,
    }

    if not is_connected():
        profile["error"] = "HubSpot not connected"
        return profile

    try:
        # ── Search contact by phone ────────────────────────────
        result = hubspot_api("/crm/v3/objects/contacts/search", method="POST", json_body={
            "filterGroups": [{
                "filters": [{
                    "propertyName": "phone",
                    "operator": "EQ",
                    "value": phone_number
                }]
            }],
            "properties": [
                "firstname", "lastname", "email", "phone",
                "company", "lifecyclestage", "hs_object_id"
            ],
            "limit": 1
        })

        if result.get("total", 0) == 0:
            return profile  # Not in HubSpot — found stays False

        contact = result["results"][0]
        contact_id = contact["id"]
        props = contact["properties"]

        profile["found"] = True
        profile["contact"] = {
            "id": contact_id,
            "name": f"{props.get('firstname', '')} {props.get('lastname', '')}".strip(),
            "email": props.get("email"),
            "phone": props.get("phone"),
            "company": props.get("company"),
            "lifecycle_stage": props.get("lifecyclestage"),
        }

        # ── Associated deal (first) ────────────────────────────
        try:
            deals = hubspot_api(f"/crm/v3/objects/contacts/{contact_id}/associations/deals")
            if deals.get("results"):
                deal_id = deals["results"][0]["id"]
                deal = hubspot_api(
                    f"/crm/v3/objects/deals/{deal_id}",
                    method="GET",
                    params="properties=dealname,dealstage,amount,closedate,pipeline"
                )
                dp = deal.get("properties", {})
                profile["deal"] = {
                    "name": dp.get("dealname"),
                    "stage": dp.get("dealstage"),
                    "amount": dp.get("amount"),
                    "close_date": dp.get("closedate"),
                    "pipeline": dp.get("pipeline"),
                }
        except Exception as e:
            print(f"[caller_id] Deal lookup failed for {contact_id}: {e}")

        # ── Last 3 notes ───────────────────────────────────────
        try:
            notes_assoc = hubspot_api(f"/crm/v3/objects/contacts/{contact_id}/associations/notes")
            if notes_assoc.get("results"):
                for n in notes_assoc["results"][:3]:
                    note = hubspot_api(
                        f"/crm/v3/objects/notes/{n['id']}",
                        params="properties=hs_note_body,hs_timestamp"
                    )
                    np = note.get("properties", {})
                    profile["notes"].append({
                        "body": np.get("hs_note_body"),
                        "timestamp": np.get("hs_timestamp"),
                    })
        except Exception as e:
            print(f"[caller_id] Notes lookup failed for {contact_id}: {e}")

        # ── Last call log ──────────────────────────────────────
        try:
            calls_assoc = hubspot_api(f"/crm/v3/objects/contacts/{contact_id}/associations/calls")
            if calls_assoc.get("results"):
                call_id = calls_assoc["results"][0]["id"]
                call = hubspot_api(
                    f"/crm/v3/objects/calls/{call_id}",
                    params="properties=hs_call_body,hs_timestamp,hs_call_direction,hs_call_duration"
                )
                cp = call.get("properties", {})
                profile["last_call"] = {
                    "notes": cp.get("hs_call_body"),
                    "timestamp": cp.get("hs_timestamp"),
                    "direction": cp.get("hs_call_direction"),
                    "duration": cp.get("hs_call_duration"),
                }
        except Exception as e:
            print(f"[caller_id] Call log lookup failed for {contact_id}: {e}")

    except Exception as e:
        print(f"[caller_id] Profile lookup failed for {phone_number}: {e}")
        profile["error"] = str(e)

    return profile
