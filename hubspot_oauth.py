"""
Sales Brain — HubSpot OAuth 2.0 Token Management
Handles token storage, auto-refresh, and authenticated API calls.
Mirrors the pattern used in the Infinity Dispatch platform.
"""

import json
import os
import time
import requests
from config import (
    HUBSPOT_CLIENT_ID,
    HUBSPOT_CLIENT_SECRET,
    HUBSPOT_REDIRECT_URI,
    HUBSPOT_SCOPES,
    HUBSPOT_TOKEN_FILE,
)

HUBSPOT_TOKEN_URL = "https://api.hubapi.com/oauth/v1/token"
HUBSPOT_BASE_URL = "https://api.hubapi.com"


# ════════════════════════════════════════════════════════════════════
# TOKEN STORAGE — file-based (no database required)
# ════════════════════════════════════════════════════════════════════

def _load_tokens() -> dict:
    """Load stored OAuth tokens from disk."""
    if not os.path.exists(HUBSPOT_TOKEN_FILE):
        return {}
    try:
        with open(HUBSPOT_TOKEN_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_tokens(tokens: dict):
    """Persist OAuth tokens to disk."""
    with open(HUBSPOT_TOKEN_FILE, "w") as f:
        json.dump(tokens, f)


def store_tokens(access_token: str, refresh_token: str, expires_in: int):
    """Store a fresh token set after initial auth or refresh."""
    _save_tokens({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": time.time() + expires_in,
    })


def clear_tokens():
    """Remove stored tokens (disconnect)."""
    if os.path.exists(HUBSPOT_TOKEN_FILE):
        os.remove(HUBSPOT_TOKEN_FILE)


# ════════════════════════════════════════════════════════════════════
# TOKEN RETRIEVAL WITH AUTO-REFRESH
# ════════════════════════════════════════════════════════════════════

def get_access_token() -> str | None:
    """
    Return a valid access token, refreshing automatically if expired.
    Returns None if not connected or refresh fails.
    """
    tokens = _load_tokens()
    if not tokens.get("access_token"):
        return None

    # Check if token expires within 5 minutes
    expires_at = tokens.get("expires_at", 0)
    if time.time() > expires_at - 300:
        # Token expired or about to expire — refresh it
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            return None

        try:
            resp = requests.post(HUBSPOT_TOKEN_URL, data={
                "grant_type": "refresh_token",
                "client_id": HUBSPOT_CLIENT_ID,
                "client_secret": HUBSPOT_CLIENT_SECRET,
                "refresh_token": refresh_token,
            }, timeout=10)

            if not resp.ok:
                print(f"HubSpot token refresh failed: {resp.status_code} — {resp.text[:200]}")
                return None

            data = resp.json()
            store_tokens(
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                expires_in=data["expires_in"],
            )
            print("HubSpot: Token refreshed successfully")
            return data["access_token"]

        except Exception as e:
            print(f"HubSpot token refresh error: {e}")
            return None

    return tokens["access_token"]


# ════════════════════════════════════════════════════════════════════
# OAUTH FLOW HELPERS (called by Flask routes in app.py)
# ════════════════════════════════════════════════════════════════════

def get_authorize_url() -> str:
    """Build the HubSpot OAuth authorization URL."""
    return (
        f"https://app.hubspot.com/oauth/authorize"
        f"?client_id={HUBSPOT_CLIENT_ID}"
        f"&redirect_uri={requests.utils.quote(HUBSPOT_REDIRECT_URI, safe='')}"
        f"&scope={requests.utils.quote(HUBSPOT_SCOPES, safe='')}"
    )


def exchange_code(code: str) -> dict:
    """
    Exchange an authorization code for tokens.
    Returns the token data dict on success, raises on failure.
    """
    resp = requests.post(HUBSPOT_TOKEN_URL, data={
        "grant_type": "authorization_code",
        "client_id": HUBSPOT_CLIENT_ID,
        "client_secret": HUBSPOT_CLIENT_SECRET,
        "redirect_uri": HUBSPOT_REDIRECT_URI,
        "code": code,
    }, timeout=10)

    if not resp.ok:
        raise Exception(f"HubSpot OAuth error: {resp.status_code} — {resp.text[:200]}")

    data = resp.json()
    store_tokens(
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_in=data["expires_in"],
    )
    return data


# ════════════════════════════════════════════════════════════════════
# AUTHENTICATED API HELPER
# ════════════════════════════════════════════════════════════════════

def hubspot_api(endpoint: str, method: str = "GET", json_body: dict = None) -> dict:
    """
    Make an authenticated HubSpot API call.
    Handles token retrieval and Bearer auth automatically.
    Raises Exception if not connected or API returns an error.
    """
    token = get_access_token()
    if not token:
        raise Exception("HubSpot not connected. Visit /hubspot/authorize to connect.")

    url = endpoint if endpoint.startswith("http") else f"{HUBSPOT_BASE_URL}{endpoint}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    if method.upper() == "POST":
        resp = requests.post(url, headers=headers, json=json_body, timeout=10)
    else:
        resp = requests.get(url, headers=headers, timeout=10)

    if not resp.ok:
        raise Exception(f"HubSpot API error ({resp.status_code}): {resp.text[:200]}")

    return resp.json()


def is_connected() -> bool:
    """Check if we have a valid (or refreshable) HubSpot connection."""
    return get_access_token() is not None
