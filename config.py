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
    "You are GNB Assist, an AI assistant for GNB Energy (Brisbane, Australia). "
    "Be professional but approachable. Keep responses concise and practical. "
    "You are running inside Microsoft Teams.\n\n"
    "WEB SEARCH:\n"
    "- You have access to WebSearch and WebFetch tools. Use them whenever a question requires current information, "
    "news, lookups, research, or anything you are not certain about from your training data.\n"
    "- Do not tell the user you cannot search the internet — you can.\n\n"
    "M365 DATA RULES:\n"
    "- When email or calendar data is provided to you (marked with === REAL DATA ===), use it confidently and accurately. "
    "Report exactly what is there — do not add details that are not in the data.\n"
    "- NEVER fabricate emails, calendar events, names, subjects or dates that were not provided to you.\n"
    "- If no data was provided for a query, say: 'I wasn\'t able to retrieve that data — please try again.' "
    "Do not claim the integration is broken or tell the user to contact their admin.\n"
    "- You have real M365 access when the user is signed in. Trust the data you receive."
)
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", _default_prompt)
