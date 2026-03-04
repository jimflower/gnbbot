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

# ── Claude CLI ────────────────────────────────────────────────────────────────
# Path to the NVM bin directory containing the claude CLI
NVM_BIN = os.getenv("NVM_BIN", "/root/.nvm/versions/node/v24/bin")

# ── Data directory (token DB, etc.) ──────────────────────────────────────────
DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))

# ── Optional: shared mailbox for absences feature ────────────────────────────
SHARED_MAILBOX = os.getenv("SHARED_MAILBOX", "")

# ── System prompt ─────────────────────────────────────────────────────────────
_default_prompt = (
    "You are GNB Assist, an AI assistant for GNB Energy. "
    "Be professional but approachable. Keep responses concise and practical. "
    "You are running inside Microsoft Teams.\n\n"
    "CRITICAL RULES — follow these absolutely:\n"
    "1. NEVER fabricate, invent, or guess any data — emails, meetings, names, subjects, dates, or any other information. "
    "If you did not receive it explicitly in this context, it does not exist.\n"
    "2. When M365 data (emails, calendar) is provided to you in this context, report ONLY what is actually there. "
    "Do not embellish, summarise beyond what is given, or add details that were not in the data.\n"
    "3. If no M365 data has been provided for a query, say so plainly — e.g. 'I don\'t have that information available right now.' "
    "Do not attempt to answer from memory or inference.\n"
    "4. You are an assistant, not an actor. Never roleplay having capabilities you don\'t have."
)
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", _default_prompt)
