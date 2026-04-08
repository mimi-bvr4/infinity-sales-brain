#!/bin/bash
# ═══════════════════════════════════════════════════════
#   INFINITY HOSPITALITY — SALES BRAIN
#   Start script
# ═══════════════════════════════════════════════════════

echo ""
echo "  🧠 SALES BRAIN — Infinity Hospitality Group"
echo "  ─────────────────────────────────────────────"
echo ""

# Check for API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "  ⚠️  ANTHROPIC_API_KEY not set."
    echo "  Run: export ANTHROPIC_API_KEY='your-key-here'"
    echo ""
    read -p "  Enter your Anthropic API key (or press Enter to skip): " api_key
    if [ -n "$api_key" ]; then
        export ANTHROPIC_API_KEY="$api_key"
        echo "  ✅ API key set for this session."
    fi
fi

# Check for Google credentials
if [ -z "$GOOGLE_SERVICE_ACCOUNT_KEY" ] && [ ! -f "token.json" ]; then
    echo "  ⚠️  Google Calendar not configured."
    echo "  For live date availability, set up one of:"
    echo "    • GOOGLE_SERVICE_ACCOUNT_KEY=/path/to/service-account.json"
    echo "    • Place token.json in this directory (OAuth)"
    echo ""
fi

# Install dependencies if needed
if ! python3 -c "import flask" 2>/dev/null; then
    echo "  📦 Installing dependencies..."
    pip install -r requirements.txt --break-system-packages -q
fi

echo "  🚀 Starting Sales Brain on http://localhost:5000"
echo ""

cd "$(dirname "$0")"
python3 app.py
