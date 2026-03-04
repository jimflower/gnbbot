"""
Per-user OAuth token storage (SQLite).
Each Teams user authenticates once — tokens are refreshed automatically.
"""

import sqlite3
import os
import time
import requests
from config import DATA_DIR, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID

DB_PATH = os.path.join(DATA_DIR, "user_tokens.db")

# Delegated scopes for new sign-ins (full set, shown on consent screen)
OAUTH_SCOPES = "Mail.Read Calendars.Read Tasks.ReadWrite Files.Read User.Read offline_access"

# Conservative scopes for token refresh — must match what users originally consented to.
# Adding new scopes here causes refresh to fail for existing users; they must sign in fresh.
_REFRESH_SCOPES = "Mail.Read Calendars.Read Tasks.ReadWrite User.Read offline_access"


def _get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_tokens (
                teams_user_id  TEXT PRIMARY KEY,
                tenant_id      TEXT,
                email          TEXT,
                display_name   TEXT,
                access_token   TEXT,
                refresh_token  TEXT,
                expires_at     REAL
            )
        """)


def store_token(teams_user_id, tenant_id, email, display_name,
                access_token, refresh_token, expires_in):
    expires_at = time.time() + int(expires_in) - 60
    with _get_conn() as conn:
        conn.execute("""
            INSERT INTO user_tokens
                (teams_user_id, tenant_id, email, display_name, access_token, refresh_token, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(teams_user_id) DO UPDATE SET
                tenant_id=excluded.tenant_id,
                email=excluded.email,
                display_name=excluded.display_name,
                access_token=excluded.access_token,
                refresh_token=excluded.refresh_token,
                expires_at=excluded.expires_at
        """, (teams_user_id, tenant_id, email, display_name,
              access_token, refresh_token, expires_at))


def get_token(teams_user_id) -> str | None:
    """Return a valid access token, refreshing if expired."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM user_tokens WHERE teams_user_id = ?", (teams_user_id,)
        ).fetchone()

    if not row:
        return None

    if time.time() < row["expires_at"]:
        return row["access_token"]

    return _refresh(teams_user_id, row)


def _refresh(teams_user_id, row) -> str | None:
    import logging
    log = logging.getLogger(__name__)
    try:
        r = requests.post(
            f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/oauth2/v2.0/token",
            data={
                "grant_type":    "refresh_token",
                "client_id":     AZURE_CLIENT_ID,
                "client_secret": AZURE_CLIENT_SECRET,
                "refresh_token": row["refresh_token"],
                "scope":         _REFRESH_SCOPES,
            },
            timeout=15,
        )
        data = r.json()
        if "access_token" not in data:
            # Refresh token is invalid or expired — delete the stale entry so
            # the bot knows to prompt the user to sign in again.
            err = data.get("error", "unknown")
            log.warning(f"Token refresh failed for {teams_user_id} ({err}) — clearing stored token")
            delete_token(teams_user_id)
            return None

        store_token(
            teams_user_id,
            row["tenant_id"],
            row["email"],
            row["display_name"],
            data["access_token"],
            data.get("refresh_token", row["refresh_token"]),
            data.get("expires_in", 3600),
        )
        return data["access_token"]
    except Exception as e:
        log.error(f"Token refresh exception for {teams_user_id}: {e}")
        return None


def get_user_info(teams_user_id) -> dict | None:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT email, display_name FROM user_tokens WHERE teams_user_id = ?",
            (teams_user_id,)
        ).fetchone()
    return dict(row) if row else None


def is_authenticated(teams_user_id) -> bool:
    return get_token(teams_user_id) is not None


def delete_token(teams_user_id):
    with _get_conn() as conn:
        conn.execute("DELETE FROM user_tokens WHERE teams_user_id = ?", (teams_user_id,))


init_db()
