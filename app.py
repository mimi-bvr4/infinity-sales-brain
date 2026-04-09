"""
Sales Brain — Main Application
Flask server with Claude API conversation loop, tool use, and escalation system.
"""

import os
import json
import datetime
import anthropic
from flask import Flask, request, jsonify, render_template, session, redirect
from config import (
    ANTHROPIC_API_KEY, CLAUDE_MODEL, CONTEXT_FILE,
    GREEN_THRESHOLD, YELLOW_THRESHOLD, ESCALATION_GROUP, SALES_BRAIN_EMAIL,
    HUBSPOT_CLIENT_ID,
)
from tools import TOOL_DEFINITIONS, execute_tool, log_question
from hubspot_oauth import (
    get_authorize_url, exchange_code, store_tokens, clear_tokens,
    get_access_token, is_connected,
)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(32))

# ── Load Sales Brain Context (system prompt) ───────────────────────

def load_system_prompt():
    """Load Sales_Brain_Context.md as the system prompt."""
    try:
        with open(CONTEXT_FILE, "r") as f:
            context = f.read()
    except FileNotFoundError:
        context = "(Sales Brain Context file not found. Operating with limited knowledge.)"

    today = datetime.date.today().isoformat()

    return f"""You are the **Infinity Hospitality Sales Brain** — the AI-powered knowledge and decision system for the IHG sales department.

## YOUR ROLE
- You answer questions from the sales team instantly and accurately.
- You have the complete IHG knowledge base loaded below.
- You can check live venue date availability via Google Calendar.
- You can look up contacts and deals in HubSpot.
- You can escalate questions you're uncertain about to leadership.

## CONFIDENCE PROTOCOL
For every answer, internally assess your confidence:
- **GREEN (>90%):** Answer immediately. You have this in your knowledge base and it's current.
- **YELLOW (60-90%):** Give your best answer but flag it. Then ASK the team member: "I'm not 100% sure about this. Would you like me to escalate to leadership for confirmation?"
- **RED (<60%):** Do NOT guess. Tell the team member you don't have a confident answer. ASK: "I'd need to escalate this to leadership. Want me to send it to them?"

**CRITICAL: NEVER auto-escalate.** Always ask the team member for permission BEFORE calling the send_escalation tool. Wait for them to say "yes", "escalate", "send it", or similar confirmation. If they say "no" or "it's fine", do NOT escalate.

If a tool call fails (e.g., HubSpot returns an error), tell the team member what happened and ask if they want to escalate — do NOT automatically escalate tool errors.

## RESPONSE FORMAT
- Start every answer with a confidence indicator: 🟢 🟡 or 🔴
- Be concise and direct — the sales team needs quick answers
- For pricing questions, always cite the source (Pricing Guide)
- For availability questions, always include the disclaimer about verifying with clients
- NEVER tell a client directly that a date is available — you provide data to the sales team only

## DATE AVAILABILITY
- Use the check_date_availability and list_open_dates tools for any date-related query
- Always run the two-fold check (primary + ±1 day context)
- For TBB, identify which specific spaces are booked vs. available
- For downtown venues, cross-check the Holidays/Lot R/Titans calendar

## ESCALATION
- ALWAYS ask the team member before escalating — never send automatically
- When they confirm, use send_escalation with level "YELLOW" or "RED"
- The team member is automatically CC'd on the escalation email
- Escalation group responds within ~2 business hours (Tues-Sat 9am-5pm CT)

## KNOWLEDGE CURRENCY
- Check the Confidence Check dates in your knowledge base
- If any data category is >90 days old, add a caveat: "⚠️ This information was last verified on [date]. Please confirm with Sales Director."

## IMPORTANT RULES
- All dates are first come, first served — NO holds, NO reservations
- Social Experiences phased out for new clients as of 12.16.25 (reference only for existing contracts)
- The Pricing Guide is the authoritative source for rates (not the 2026 Venue Guide)
- Never reveal internal pricing strategies or discount approval processes to clients
- You serve the SALES TEAM, not clients directly

---

## COMPLETE KNOWLEDGE BASE
(Last loaded: {today})

{context}
"""


# ── In-memory conversation store ───────────────────────────────────
# In production, use Redis or a database
conversations = {}


def get_or_create_conversation(session_id: str) -> list:
    """Get existing conversation history or create new one."""
    if session_id not in conversations:
        conversations[session_id] = []
    return conversations[session_id]


# ── Claude API conversation with tool use ──────────────────────────

def chat_with_brain(user_message: str, session_id: str, user_name: str = "Sales Team", user_email: str = "") -> dict:
    """
    Send a message to the Sales Brain and get a response.
    Handles multi-turn tool use automatically.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    messages = get_or_create_conversation(session_id)
    messages.append({"role": "user", "content": user_message})

    system_prompt = load_system_prompt()

    # Add user context to system prompt
    if user_name or user_email:
        system_prompt += f"\n\n## CURRENT USER\nName: {user_name}\nEmail: {user_email}\n"

    # Conversation loop — keeps going until Claude gives a final text response
    max_turns = 10  # safety limit
    turn = 0
    escalation_data = None

    while turn < max_turns:
        turn += 1

        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=system_prompt,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        # Process response content blocks
        assistant_content = response.content
        messages.append({"role": "assistant", "content": assistant_content})

        # Check if Claude wants to use tools
        tool_uses = [block for block in assistant_content if block.type == "tool_use"]

        if not tool_uses:
            # No tool calls — final response
            text_blocks = [block.text for block in assistant_content if block.type == "text"]
            final_text = "\n".join(text_blocks)

            # Detect confidence level from response
            confidence = "GREEN"
            if "🔴" in final_text:
                confidence = "RED"
            elif "🟡" in final_text:
                confidence = "YELLOW"

            # If an escalation was sent, use its level for the chat color
            # (Claude's wrap-up text after escalation may not always contain the emoji)
            if escalation_data and confidence == "GREEN":
                confidence = escalation_data.get("level", "RED")

            return {
                "response": final_text,
                "confidence": confidence,
                "escalation": escalation_data,
                "session_id": session_id,
            }

        # Execute each tool call
        tool_results = []
        for tool_use in tool_uses:
            tool_name = tool_use.name
            tool_input = tool_use.input

            # Inject user info for escalation calls
            if tool_name == "send_escalation":
                if not tool_input.get("asker_email") and user_email:
                    tool_input["asker_email"] = user_email
                if not tool_input.get("asker_name") and user_name:
                    tool_input["asker_name"] = user_name

            result = execute_tool(tool_name, tool_input)

            # Track escalation data
            if tool_name == "send_escalation":
                escalation_data = json.loads(result)

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})

    # If we hit max turns, return what we have
    return {
        "response": "I'm still processing your question. The tool loop exceeded the maximum turns. Please try again or simplify your question.",
        "confidence": "RED",
        "escalation": None,
        "session_id": session_id,
    }


# ════════════════════════════════════════════════════════════════════
# FLASK ROUTES
# ════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    """Serve the Sales Brain chat interface."""
    return render_template("chat.html")


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Handle chat messages from the frontend."""
    data = request.json
    user_message = data.get("message", "").strip()
    session_id = data.get("session_id", "default")
    user_name = data.get("user_name", "Sales Team")
    user_email = data.get("user_email", "")

    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    if not ANTHROPIC_API_KEY:
        return jsonify({
            "error": "Anthropic API key not configured. Set ANTHROPIC_API_KEY environment variable."
        }), 500

    try:
        result = chat_with_brain(user_message, session_id, user_name, user_email)
        # Log every question to Google Sheet (fails silently if not configured)
        log_question(
            user_name=user_name,
            user_email=user_email,
            question=user_message,
            response=result.get("response", ""),
            confidence=result.get("confidence", "GREEN"),
            escalated=bool(result.get("escalation")),
        )
        return jsonify(result)
    except anthropic.AuthenticationError:
        return jsonify({"error": "Invalid Anthropic API key. Check your ANTHROPIC_API_KEY."}), 401
    except anthropic.RateLimitError:
        return jsonify({"error": "Rate limit reached. Please wait a moment and try again."}), 429
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


@app.route("/api/clear", methods=["POST"])
def api_clear():
    """Clear conversation history for a session."""
    data = request.json
    session_id = data.get("session_id", "default")
    if session_id in conversations:
        del conversations[session_id]
    return jsonify({"status": "cleared"})


# ════════════════════════════════════════════════════════════════════
# HUBSPOT OAUTH ROUTES
# ════════════════════════════════════════════════════════════════════

@app.route("/hubspot/authorize")
def hubspot_authorize():
    """Start the HubSpot OAuth flow — redirects to HubSpot login."""
    if not HUBSPOT_CLIENT_ID:
        return "<h2>HubSpot not configured</h2><p>Set HUBSPOT_CLIENT_ID, HUBSPOT_CLIENT_SECRET, and HUBSPOT_REDIRECT_URI in Railway Variables.</p>", 500
    return redirect(get_authorize_url())


@app.route("/hubspot/callback")
def hubspot_callback():
    """Handle OAuth callback from HubSpot after user authorizes."""
    code = request.args.get("code")
    if not code:
        return "<h2>Error</h2><p>Missing authorization code from HubSpot.</p>", 400

    try:
        exchange_code(code)
        return """
        <html>
        <body style="font-family: Inter, sans-serif; display:flex; align-items:center; justify-content:center; height:100vh; background:#f5f0ea;">
            <div style="text-align:center; background:white; padding:40px; border-radius:12px; box-shadow:0 2px 8px rgba(0,0,0,0.1);">
                <h2 style="color:#1B3A5C;">HubSpot Connected!</h2>
                <p>The Sales Brain can now look up contacts and deals.</p>
                <a href="/" style="display:inline-block; margin-top:16px; padding:10px 24px; background:#1B3A5C; color:white; text-decoration:none; border-radius:6px;">Return to Sales Brain</a>
            </div>
        </body>
        </html>
        """
    except Exception as e:
        return f"<h2>OAuth Failed</h2><p>{str(e)}</p><p><a href='/hubspot/authorize'>Try again</a></p>", 400


@app.route("/hubspot/status")
def hubspot_status():
    """Check if HubSpot is connected and tokens are valid."""
    connected = is_connected()
    if connected:
        try:
            token = get_access_token()
            # Verify token by hitting the token info endpoint
            import requests as req
            info = req.get(f"https://api.hubapi.com/oauth/v1/access-tokens/{token}", timeout=5)
            if info.ok:
                data = info.json()
                return jsonify({
                    "connected": True,
                    "hub_id": data.get("hub_id"),
                    "user": data.get("user"),
                    "scopes": data.get("scopes"),
                })
        except Exception:
            pass
    return jsonify({"connected": connected})


@app.route("/hubspot/disconnect")
def hubspot_disconnect():
    """Remove HubSpot OAuth tokens."""
    clear_tokens()
    return jsonify({"disconnected": True, "message": "HubSpot connection removed. Visit /hubspot/authorize to reconnect."})


@app.route("/api/health", methods=["GET"])
def api_health():
    """Health check endpoint."""
    from tools import get_calendar_service
    cal_ok = get_calendar_service() is not None
    return jsonify({
        "status": "ok",
        "model": CLAUDE_MODEL,
        "api_key_set": bool(ANTHROPIC_API_KEY),
        "context_loaded": os.path.exists(CONTEXT_FILE),
        "google_calendar_connected": cal_ok,
        "hubspot_connected": is_connected(),
        "timestamp": datetime.datetime.now().isoformat(),
    })


# ════════════════════════════════════════════════════════════════════
# RUN
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from tools import get_calendar_service

    print("=" * 60)
    print("  INFINITY HOSPITALITY — SALES BRAIN")
    print("  Powered by Claude API + Google Calendar + HubSpot")
    print("=" * 60)
    print(f"  Model:     {CLAUDE_MODEL}")
    print(f"  API Key:   {'✅ Set' if ANTHROPIC_API_KEY else '❌ Not set — export ANTHROPIC_API_KEY'}")
    print(f"  Context:   {'✅ Loaded' if os.path.exists(CONTEXT_FILE) else '❌ Not found'}")

    # Check Google Calendar auth
    cal_service = get_calendar_service()
    if cal_service:
        print("  Calendar:  ✅ Connected")
    else:
        gcal_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        gcal_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY", "")
        token_file = os.path.join(os.path.dirname(__file__), "token.json")
        if gcal_json:
            print("  Calendar:  ❌ GOOGLE_SERVICE_ACCOUNT_JSON set but auth failed")
        elif gcal_file:
            print(f"  Calendar:  ❌ Key file not found: {gcal_file}")
        elif os.path.exists(token_file):
            print("  Calendar:  ❌ token.json found but invalid — run setup_google_auth.py")
        else:
            print("  Calendar:  ⚠️  Not configured — run setup_google_auth.py or set env vars")
            print("             (Date availability will return 'not connected' until configured)")

    # Check HubSpot OAuth
    if is_connected():
        print("  HubSpot:   ✅ Connected (OAuth)")
    elif HUBSPOT_CLIENT_ID:
        print("  HubSpot:   ⚠️  OAuth configured but not connected — visit /hubspot/authorize")
    else:
        print("  HubSpot:   ❌ Not configured — set HUBSPOT_CLIENT_ID + HUBSPOT_CLIENT_SECRET on Railway")

    print(f"  URL:       http://localhost:5000")
    print("=" * 60)

    app.run(host="0.0.0.0", port=5000, debug=True)
