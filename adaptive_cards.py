"""
GNB Assist — Adaptive Card builders for Microsoft Teams.
"""

import urllib.parse
from datetime import datetime
import zoneinfo
from config import AZURE_TENANT_ID, AZURE_CLIENT_ID, BASE_URL, BOT_NAME
from user_tokens import OAUTH_SCOPES

AEST          = zoneinfo.ZoneInfo("Australia/Brisbane")
OAUTH_REDIRECT = f"{BASE_URL}/auth/callback"


def build_signin_card(teams_user_id: str) -> dict:
    auth_url = (
        f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/oauth2/v2.0/authorize"
        f"?client_id={AZURE_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={urllib.parse.quote(OAUTH_REDIRECT)}"
        f"&scope={urllib.parse.quote(OAUTH_SCOPES)}"
        f"&state={urllib.parse.quote(teams_user_id)}"
        f"&prompt=select_account"
    )
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {
                "type": "TextBlock",
                "text": f"Sign in to {BOT_NAME}",
                "weight": "Bolder",
                "size": "Medium",
            },
            {
                "type": "TextBlock",
                "text": "Connect your Microsoft account to access your emails, calendar, and more.",
                "wrap": True,
            },
        ],
        "actions": [
            {
                "type": "Action.OpenUrl",
                "title": "Sign in with Microsoft",
                "url": auth_url,
            }
        ],
    }


def build_absences_card(absences: list) -> dict:
    today_str = datetime.now(AEST).strftime("%-d %B %Y")

    body = [
        {
            "type": "TextBlock",
            "text": f"Absences — {today_str}",
            "weight": "Bolder",
            "size": "Medium",
            "color": "Accent",
        }
    ]

    if not absences:
        body.append({
            "type": "TextBlock",
            "text": "No absence notifications received today. Everyone should be in.",
            "wrap": True,
            "isSubtle": True,
        })
    else:
        for item in absences:
            body.append({
                "type": "ColumnSet",
                "separator": True,
                "columns": [
                    {
                        "type": "Column",
                        "width": "auto",
                        "items": [{"type": "TextBlock", "text": "🔴", "verticalContentAlignment": "Center"}],
                    },
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {"type": "TextBlock", "text": f"**{item['name']}**", "wrap": True},
                            {"type": "TextBlock", "text": item.get("subject", ""), "wrap": True, "isSubtle": True, "spacing": "None"},
                        ],
                    },
                ],
            })

    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": body,
        "actions": [
            {"type": "Action.Submit", "title": "↻ Refresh", "data": {"gnb_action": "show_absences"}}
        ],
    }
