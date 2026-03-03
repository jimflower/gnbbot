"""
Configuration — loaded from .env file.
All credentials live here; nothing is hardcoded elsewhere.
"""

import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

# ── Azure App Registration ────────────────────────────────────────────────────
AZURE_TENANT_ID     = os.getenv("AZURE_TENANT_ID", "")
AZURE_CLIENT_ID     = os.getenv("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")

# ── Bot identity ──────────────────────────────────────────────────────────────
BOT_NAME = os.getenv("BOT_NAME", "GNB Assist")
BOT_PORT = int(os.getenv("BOT_PORT", "3978"))
BASE_URL = os.getenv("BASE_URL", "http://localhost:3978")

# ── AI ────────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL      = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

# ── Data directory (token DB, etc.) ──────────────────────────────────────────
DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))

# ── Optional: shared mailbox for absences feature ────────────────────────────
SHARED_MAILBOX = os.getenv("SHARED_MAILBOX", "")

# ── System prompt ─────────────────────────────────────────────────────────────
_default_prompt = (
    "You are GNB Assist, an AI assistant for GNB Energy. "
    "Be professional but approachable. Keep responses concise and practical. "
    "You are running inside Microsoft Teams."
)
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", _default_prompt)
