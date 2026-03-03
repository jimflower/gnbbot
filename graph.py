"""
Microsoft Graph API helpers — email, calendar, shared mailbox.
All calls use a delegated user access token (per-user OAuth).
"""

import logging
import requests
from datetime import datetime
import zoneinfo

log = logging.getLogger(__name__)

AEST  = zoneinfo.ZoneInfo("Australia/Brisbane")
GRAPH = "https://graph.microsoft.com/v1.0"


def get_recent_emails(token: str, count: int = 15) -> list[dict]:
    """Fetch the user's most recent inbox messages."""
    try:
        r = requests.get(
            f"{GRAPH}/me/messages",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "$top":      count,
                "$select":   "subject,from,receivedDateTime,bodyPreview,isRead",
                "$orderby":  "receivedDateTime desc",
                "$filter":   "isDraft eq false",
            },
            timeout=15,
        )
        return r.json().get("value", []) if r.ok else []
    except Exception as e:
        log.error(f"Graph emails error: {e}")
        return []


def get_calendar_today(token: str) -> list[dict]:
    """Fetch the user's calendar events for today (AEST)."""
    try:
        now   = datetime.now(AEST)
        start = now.strftime("%Y-%m-%dT00:00:00+10:00")
        end   = now.strftime("%Y-%m-%dT23:59:59+10:00")

        r = requests.get(
            f"{GRAPH}/me/calendarView",
            headers={
                "Authorization": f"Bearer {token}",
                "Prefer":        'outlook.timezone="Australia/Brisbane"',
            },
            params={
                "startDateTime": start,
                "endDateTime":   end,
                "$select":       "subject,start,end,location,organizer,isAllDay",
                "$orderby":      "start/dateTime",
            },
            timeout=15,
        )
        return r.json().get("value", []) if r.ok else []
    except Exception as e:
        log.error(f"Graph calendar error: {e}")
        return []


def get_shared_mailbox_emails(token: str, mailbox: str, count: int = 25) -> list[dict]:
    """Fetch emails from a shared mailbox (user must have access)."""
    try:
        r = requests.get(
            f"{GRAPH}/users/{mailbox}/messages",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "$top":     count,
                "$select":  "subject,from,receivedDateTime,bodyPreview",
                "$orderby": "receivedDateTime desc",
            },
            timeout=15,
        )
        return r.json().get("value", []) if r.ok else []
    except Exception as e:
        log.error(f"Graph shared mailbox error: {e}")
        return []
