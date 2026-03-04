"""
GNB Assist — Microsoft Teams Bot
Claude-powered AI assistant with Microsoft 365 integration.
Each user authenticates with their own Microsoft account.

OpenClaw-inspired improvements:
  - Persistent conversation history (survives restarts)
  - Chat commands: /help, /status, /clear
  - Group chat activation mode (respond only when @mentioned)
  - Microsoft Tasks integration
  - Week-ahead calendar view
"""

import asyncio
import logging
import os
import re
import urllib.parse

import requests as http_requests
from aiohttp import web
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
from botbuilder.schema import Activity, ActivityTypes, Attachment

from adaptive_cards import build_absences_card, build_signin_card
from ai_client import call_ai
from config import (
    AZURE_CLIENT_ID,
    AZURE_CLIENT_SECRET,
    AZURE_TENANT_ID,
    BASE_URL,
    BOT_NAME,
    BOT_PORT,
    SHARED_MAILBOX,
    SYSTEM_PROMPT,
)
from conversations import clear_history, get_stats, load_history, save_history
from graph import (
    get_calendar_today,
    get_calendar_tomorrow,
    get_calendar_week,
    get_recent_emails,
    get_shared_mailbox_emails,
    get_tasks,
)
from user_tokens import OAUTH_SCOPES, delete_token, get_token, get_user_info, store_token

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

OAUTH_REDIRECT = f"{BASE_URL}/auth/callback"

settings = BotFrameworkAdapterSettings(
    app_id=AZURE_CLIENT_ID,
    app_password=AZURE_CLIENT_SECRET,
    channel_auth_tenant=AZURE_TENANT_ID,
)
adapter = BotFrameworkAdapter(settings)

# ── Intent patterns ────────────────────────────────────────────────────────────
SIGNIN_INTENTS = re.compile(
    r"^\s*(sign\s*in|connect|login|link\s+account|authenticate)\s*$", re.IGNORECASE
)
SIGNOUT_INTENTS = re.compile(
    r"^\s*(sign\s*out|disconnect|logout|unlink\s+account)\s*$", re.IGNORECASE
)
EMAIL_INTENTS = re.compile(
    r"(email|inbox|unread|message|mail|planning@|@gnbenergy)",
    re.IGNORECASE,
)
CALENDAR_TODAY_INTENTS = re.compile(
    r"(calendar|schedule|meeting|agenda|today|what.s\s+on\s+today|what\s+do\s+i\s+have\s+today|my\s+day)",
    re.IGNORECASE,
)
CALENDAR_TOMORROW_INTENTS = re.compile(
    r"(tomorrow.?s?\s+(meetings?|events?|schedule|calendar|agenda)"
    r"|what.s\s+on\s+tomorrow|what\s+do\s+i\s+have\s+tomorrow"
    r"|my\s+agenda\s+tomorrow|tomorrow.s\s+agenda|tomorrow)",
    re.IGNORECASE,
)
CALENDAR_WEEK_INTENTS = re.compile(
    r"(this\s+week|next\s+week|upcoming\s+meetings?|upcoming\s+events?"
    r"|week.s?\s+(meetings?|schedule|calendar)|meetings?\s+(this|next)\s+week"
    r"|what.s\s+coming\s+up|rest\s+of\s+(the\s+)?week)",
    re.IGNORECASE,
)
SHARED_MAILBOX_INTENTS = re.compile(
    r"(planning|planning@|shared\s+mail)",
    re.IGNORECASE,
)
ABSENCE_INTENTS = re.compile(
    r"^\s*(today.?s?\s+)?absences?$|^who.?s?\s+(out|off|absent)(\s+today)?$"
    r"|^attendance(\s+today)?$",
    re.IGNORECASE,
)
TASKS_INTENTS = re.compile(
    r"(my\s+tasks?|my\s+to\s*-?\s*do|todo\s+list|outstanding\s+tasks?"
    r"|what\s+(do\s+i\s+need\s+to\s+do|tasks?\s+do\s+i\s+have)"
    r"|pending\s+tasks?|open\s+tasks?)",
    re.IGNORECASE,
)
COMMAND_PATTERN = re.compile(r"^[/!](\w+)", re.IGNORECASE)


# ── Group chat helpers ─────────────────────────────────────────────────────────
def _is_group_chat(turn_context: TurnContext) -> bool:
    """True if this is a group chat or Teams channel (not a 1:1 DM)."""
    conv = turn_context.activity.conversation
    conv_type = getattr(conv, "conversation_type", None)
    if conv_type is not None:
        return conv_type in ("groupChat", "channel")
    return bool(getattr(conv, "is_group", False))


def _is_mentioned(turn_context: TurnContext) -> bool:
    """True if the bot is @mentioned in the message."""
    bot_id = turn_context.activity.recipient.id
    for entity in turn_context.activity.entities or []:
        ent = entity if isinstance(entity, dict) else (entity.serialize() if hasattr(entity, "serialize") else {})
        if ent.get("type") == "mention":
            if ent.get("mentioned", {}).get("id", "") == bot_id:
                return True
    return False


def _strip_mention(text: str, turn_context: TurnContext) -> str:
    """Remove the bot's @mention tag from message text."""
    bot_name = turn_context.activity.recipient.name or BOT_NAME
    text = re.sub(rf"<at>{re.escape(bot_name)}</at>", "", text, flags=re.IGNORECASE)
    text = re.sub(rf"@{re.escape(bot_name)}", "", text, flags=re.IGNORECASE)
    return text.strip()


# ── Card helper ────────────────────────────────────────────────────────────────
async def send_card(turn_context: TurnContext, card: dict):
    attachment = Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content=card,
    )
    await turn_context.send_activity(Activity(type=ActivityTypes.message, attachments=[attachment]))


# ── Graph context builders ─────────────────────────────────────────────────────
def _emails_context(token: str) -> str:
    emails = get_recent_emails(token)
    if not emails:
        return "The user's inbox appears empty or could not be retrieved."
    lines = ["Here are the user's recent emails (newest first):"]
    for e in emails:
        sender   = e.get("from", {}).get("emailAddress", {}).get("name", "Unknown")
        subject  = e.get("subject", "(no subject)")
        preview  = e.get("bodyPreview", "")[:120]
        received = e.get("receivedDateTime", "")[:16].replace("T", " ")
        unread   = " [UNREAD]" if not e.get("isRead") else ""
        lines.append(f"- {received}{unread} | From: {sender} | {subject}: {preview}")
    return "\n".join(lines)


def _calendar_context(token: str) -> str:
    from datetime import datetime
    import zoneinfo
    AEST      = zoneinfo.ZoneInfo("Australia/Brisbane")
    today_str = datetime.now(AEST).strftime("%-d %B %Y")
    events    = get_calendar_today(token)
    if not events:
        return f"The user has no calendar events today ({today_str})."
    lines = [f"Today's calendar ({today_str}):"]
    for ev in events:
        subject = ev.get("subject", "(no title)")
        start   = ev.get("start", {}).get("dateTime", "")[:16].replace("T", " ")
        end     = ev.get("end",   {}).get("dateTime", "")[:16].replace("T", " ")[11:]
        loc     = ev.get("location", {}).get("displayName", "")
        entry   = f"- {start}–{end} | {subject}"
        if loc:
            entry += f" @ {loc}"
        lines.append(entry)
    return "\n".join(lines)


def _calendar_tomorrow_context(token: str) -> str:
    from datetime import datetime, timedelta
    import zoneinfo
    AEST     = zoneinfo.ZoneInfo("Australia/Brisbane")
    tmrw_str = (datetime.now(AEST) + timedelta(days=1)).strftime("%-d %B %Y")
    events   = get_calendar_tomorrow(token)
    if not events:
        return f"The user has no calendar events tomorrow ({tmrw_str})."
    lines = [f"Tomorrow's calendar ({tmrw_str}):"]
    for ev in events:
        subject   = ev.get("subject", "(no title)")
        start     = ev.get("start", {}).get("dateTime", "")[:16].replace("T", " ")
        end       = ev.get("end",   {}).get("dateTime", "")[:16].replace("T", " ")[11:]
        loc       = ev.get("location", {}).get("displayName", "")
        cancelled = ev.get("isCancelled", False)
        entry     = f"- {start}–{end} | {subject}"
        if loc:
            entry += f" @ {loc}"
        if cancelled:
            entry += " [CANCELLED]"
        lines.append(entry)
    return "\n".join(lines)


def _calendar_week_context(token: str) -> str:
    from datetime import datetime
    import zoneinfo
    AEST   = zoneinfo.ZoneInfo("Australia/Brisbane")
    events = get_calendar_week(token)
    if not events:
        return "The user has no upcoming calendar events in the next 7 days."
    lines = ["Upcoming calendar (next 7 days):"]
    prev_date = None
    for ev in events:
        raw_start = ev.get("start", {}).get("dateTime", "")
        date_str  = raw_start[:10]
        time_str  = raw_start[11:16]
        end_str   = ev.get("end", {}).get("dateTime", "")[11:16]
        subject   = ev.get("subject", "(no title)")
        loc       = ev.get("location", {}).get("displayName", "")
        is_allday = ev.get("isAllDay", False)

        if date_str != prev_date:
            try:
                dt      = datetime.fromisoformat(raw_start)
                day_lbl = dt.strftime("%A %-d %b")
            except Exception:
                day_lbl = date_str
            lines.append(f"\n{day_lbl}:")
            prev_date = date_str

        if is_allday:
            entry = f"- (All day) {subject}"
        else:
            entry = f"- {time_str}–{end_str} | {subject}"
        if loc:
            entry += f" @ {loc}"
        lines.append(entry)
    return "\n".join(lines)


def _shared_mailbox_context(token: str, mailbox: str) -> str:
    emails = get_shared_mailbox_emails(token, mailbox)
    if not emails:
        return f"No emails found in {mailbox} or access not available."
    lines = [f"Recent emails in {mailbox} (newest first):"]
    for e in emails:
        sender   = e.get("from", {}).get("emailAddress", {}).get("name", "Unknown")
        subject  = e.get("subject", "(no subject)")
        preview  = e.get("bodyPreview", "")[:150]
        received = e.get("receivedDateTime", "")[:16].replace("T", " ")
        lines.append(f"- {received} | From: {sender} | {subject}: {preview}")
    return "\n".join(lines)


def _tasks_context(token: str) -> str:
    tasks = get_tasks(token)
    if not tasks:
        return "The user has no outstanding tasks in Microsoft To Do."
    lines = ["The user's outstanding tasks:"]
    by_list: dict[str, list] = {}
    for t in tasks:
        lst = t.get("_list_name", "Tasks")
        by_list.setdefault(lst, []).append(t)
    for lst_name, lst_tasks in by_list.items():
        lines.append(f"\n{lst_name}:")
        for t in lst_tasks:
            title    = t.get("title", "(untitled)")
            imp      = t.get("importance", "normal")
            due_raw  = (t.get("dueDateTime") or {}).get("dateTime", "")
            due      = due_raw[:10] if due_raw else ""
            imp_flag = " [HIGH]" if imp == "high" else ""
            due_flag = f" (due {due})" if due else ""
            lines.append(f"- {title}{imp_flag}{due_flag}")
    return "\n".join(lines)


def _check_absences(token: str) -> list[dict]:
    """Parse today's absence emails from the shared mailbox."""
    from datetime import datetime
    import zoneinfo
    AEST     = zoneinfo.ZoneInfo("Australia/Brisbane")
    today_dt = datetime.now(AEST).date()

    emails   = get_shared_mailbox_emails(token, SHARED_MAILBOX)
    keywords = [
        "absent", "sick", "sick day", "leave", "annual leave", "personal leave",
        "off today", "not in today", "won't be in", "wont be in",
        "wfh", "working from home",
    ]
    absences = []
    for e in emails:
        try:
            received_dt = datetime.fromisoformat(
                e.get("receivedDateTime", "").replace("Z", "+00:00")
            ).astimezone(AEST).date()
        except Exception:
            continue
        if received_dt != today_dt:
            continue
        text = (e.get("bodyPreview", "") + " " + e.get("subject", "")).lower()
        if any(kw in text for kw in keywords):
            sender = e.get("from", {}).get("emailAddress", {})
            absences.append({
                "name":    sender.get("name", "Unknown"),
                "subject": e.get("subject", ""),
            })
    return absences


# ── Command handlers ───────────────────────────────────────────────────────────
async def handle_command(turn_context: TurnContext, command: str, user_id: str) -> bool:
    """
    Handle slash/bang commands. Returns True if the command was handled.
    Inspired by OpenClaw's /status, /usage, /activation, /think commands.
    """
    cmd = command.lower()

    if cmd == "help":
        token       = get_token(user_id)
        auth_status = "Connected" if token else "Not connected"
        help_text = (
            f"**{BOT_NAME} — Help**\n\n"
            "**Microsoft 365 features** (requires sign-in):\n"
            "- *\"my emails\"* — recent inbox messages\n"
            "- *\"my calendar\"* or *\"my schedule\"* — today's meetings\n"
            "- *\"this week\"* or *\"upcoming meetings\"* — next 7 days\n"
            "- *\"my tasks\"* — outstanding To Do items\n"
        )
        if SHARED_MAILBOX:
            help_text += "- *\"absences\"* or *\"who's out\"* — today's absence report\n"
        help_text += (
            "\n**Account**:\n"
            "- *sign in* — connect your Microsoft account\n"
            "- *sign out* — disconnect your account\n"
            f"- Your account status: {auth_status}\n"
            "\n**Commands**:\n"
            "- `/help` — show this message\n"
            "- `/status` — show connection & history info\n"
            "- `/clear` — clear conversation history\n"
            "\nFor anything else, just ask me naturally!"
        )
        await turn_context.send_activity(help_text)
        return True

    if cmd == "status":
        token = get_token(user_id)
        info  = get_user_info(user_id)
        stats = get_stats(user_id)
        if token and info:
            acct = f"Connected as **{info['display_name']}** ({info['email']})"
        else:
            acct = "Not connected — say *sign in* to connect"
        msg = (
            f"**{BOT_NAME} Status**\n\n"
            f"Account: {acct}\n"
            f"Conversation history: {stats['message_count']} messages"
            + (f" (oldest {stats['history_age']} ago)" if stats["message_count"] else "")
        )
        await turn_context.send_activity(msg)
        return True

    if cmd in ("clear", "forget", "reset"):
        clear_history(user_id)
        await turn_context.send_activity("Conversation history cleared. Starting fresh!")
        return True

    return False  # unknown command — fall through to AI


# ── Bot logic ──────────────────────────────────────────────────────────────────
async def on_turn(turn_context: TurnContext):
    if turn_context.activity.type == ActivityTypes.message:
        await handle_message(turn_context)
    elif turn_context.activity.type == ActivityTypes.conversation_update:
        await handle_greeting(turn_context)


async def handle_message(turn_context: TurnContext):
    user_id   = turn_context.activity.from_property.id
    user_name = turn_context.activity.from_property.name or "there"

    # Card action (button press)
    action_data = turn_context.activity.value
    if action_data and isinstance(action_data, dict) and "gnb_action" in action_data:
        await handle_card_action(turn_context, action_data, user_id)
        return

    user_text = (turn_context.activity.text or "").strip()

    # Group chat: only respond when @mentioned
    if _is_group_chat(turn_context):
        if not _is_mentioned(turn_context):
            return
        user_text = _strip_mention(user_text, turn_context)

    if not user_text:
        return

    log.info(f"Message from {user_name}: {user_text[:80]}")

    # ── Commands (/help, /status, /clear, etc.) ───────────────────────────────
    cmd_match = COMMAND_PATTERN.match(user_text)
    if cmd_match:
        handled = await handle_command(turn_context, cmd_match.group(1), user_id)
        if handled:
            return

    # ── Built-in intents ──────────────────────────────────────────────────────
    if SIGNOUT_INTENTS.match(user_text):
        delete_token(user_id)
        await turn_context.send_activity(
            "You've been signed out. Your Microsoft account has been disconnected."
        )
        return

    if SIGNIN_INTENTS.match(user_text):
        await send_card(turn_context, build_signin_card(user_id))
        return

    if ABSENCE_INTENTS.match(user_text) and SHARED_MAILBOX:
        token = get_token(user_id)
        if not token:
            await turn_context.send_activity(
                "Say **sign in** first to connect your Microsoft account."
            )
            return
        await turn_context.send_activity(Activity(type=ActivityTypes.typing))
        loop     = asyncio.get_event_loop()
        absences = await loop.run_in_executor(None, _check_absences, token)
        await send_card(turn_context, build_absences_card(absences))
        return

    # ── Load persistent conversation history ──────────────────────────────────
    history = load_history(user_id)
    history.append({"role": "user", "content": user_text})

    await turn_context.send_activity(Activity(type=ActivityTypes.typing))

    # ── Enrich system prompt with M365 context ─────────────────────────────────
    sys_prompt = SYSTEM_PROMPT
    token      = get_token(user_id)
    if token:
        loop      = asyncio.get_event_loop()
        ctx_parts = []

        info = get_user_info(user_id)
        if info and info.get("display_name"):
            ctx_parts.append(f"The user's name is {info['display_name']}.")

        if EMAIL_INTENTS.search(user_text):
            email_ctx = await loop.run_in_executor(None, _emails_context, token)
            ctx_parts.append("=== REAL DATA FROM USER'S INBOX (use this, do not guess) ===\n" + email_ctx)

        if SHARED_MAILBOX_INTENTS.search(user_text) and SHARED_MAILBOX:
            shared_ctx = await loop.run_in_executor(
                None, lambda: _shared_mailbox_context(token, SHARED_MAILBOX)
            )
            ctx_parts.append("=== REAL DATA FROM SHARED MAILBOX: " + SHARED_MAILBOX + " ===\n" + shared_ctx)

        if CALENDAR_WEEK_INTENTS.search(user_text):
            cal_ctx = await loop.run_in_executor(None, _calendar_week_context, token)
            ctx_parts.append("=== REAL DATA FROM USER'S CALENDAR (use this, do not guess) ===\n" + cal_ctx)
        elif CALENDAR_TOMORROW_INTENTS.search(user_text):
            cal_ctx = await loop.run_in_executor(None, _calendar_tomorrow_context, token)
            ctx_parts.append("=== REAL DATA FROM USER'S CALENDAR (use this, do not guess) ===\n" + cal_ctx)
        elif CALENDAR_TODAY_INTENTS.search(user_text):
            cal_ctx = await loop.run_in_executor(None, _calendar_context, token)
            ctx_parts.append("=== REAL DATA FROM USER'S CALENDAR (use this, do not guess) ===\n" + cal_ctx)

        if TASKS_INTENTS.search(user_text):
            tasks_ctx = await loop.run_in_executor(None, _tasks_context, token)
            ctx_parts.append("=== REAL DATA FROM USER'S TASKS (use this, do not guess) ===\n" + tasks_ctx)

        if ctx_parts:
            sys_prompt = SYSTEM_PROMPT + "\n\n" + "\n\n".join(ctx_parts)

    # ── Call AI ────────────────────────────────────────────────────────────────
    try:
        loop  = asyncio.get_event_loop()
        reply = await loop.run_in_executor(None, call_ai, history, sys_prompt)
        if reply:
            history.append({"role": "assistant", "content": reply})
            save_history(user_id, history)
        else:
            reply = "Sorry, I ran into an issue — please try again in a moment."
    except Exception as e:
        log.error(f"AI error: {e}")
        reply = "Sorry, I ran into an issue — please try again in a moment."

    await turn_context.send_activity(reply)


async def handle_card_action(turn_context: TurnContext, action_data: dict, user_id: str):
    if action_data.get("gnb_action") == "show_absences" and SHARED_MAILBOX:
        token = get_token(user_id)
        if not token:
            await send_card(turn_context, build_signin_card(user_id))
            return
        await turn_context.send_activity(Activity(type=ActivityTypes.typing))
        loop     = asyncio.get_event_loop()
        absences = await loop.run_in_executor(None, _check_absences, token)
        await send_card(turn_context, build_absences_card(absences))


async def handle_greeting(turn_context: TurnContext):
    if turn_context.activity.members_added:
        for member in turn_context.activity.members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity(
                    f"G'day! I'm **{BOT_NAME}**, your AI assistant for GNB Energy.\n\n"
                    "Ask me anything, or say **sign in** to connect your Microsoft account "
                    "for email and calendar features.\n\n"
                    "Type `/help` to see everything I can do."
                )


# ── HTTP endpoints ──────────────────────────────────────────────────────────────
async def messages(req: web.Request) -> web.Response:
    if "application/json" not in req.content_type:
        return web.Response(status=415)
    body        = await req.json()
    activity    = Activity().deserialize(body)
    auth_header = req.headers.get("Authorization", "")
    try:
        await adapter.process_activity(activity, auth_header, on_turn)
        return web.Response(status=200)
    except Exception as e:
        log.error(f"Adapter error: {e}")
        return web.Response(status=500, text=str(e))


async def health(req: web.Request) -> web.Response:
    return web.Response(text=f"{BOT_NAME} is running", status=200)


async def auth_callback(req: web.Request) -> web.Response:
    """Microsoft OAuth callback — exchanges code for tokens."""
    code          = req.rel_url.query.get("code")
    teams_user_id = req.rel_url.query.get("state", "")
    error         = req.rel_url.query.get("error")

    if error:
        desc = req.rel_url.query.get("error_description", error)
        return web.Response(
            content_type="text/html",
            text=f"<h2>Sign in failed</h2><p>{desc}</p>",
        )

    if not code:
        return web.Response(status=400, text="No authorisation code received.")

    r = http_requests.post(
        f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/oauth2/v2.0/token",
        data={
            "grant_type":    "authorization_code",
            "client_id":     AZURE_CLIENT_ID,
            "client_secret": AZURE_CLIENT_SECRET,
            "redirect_uri":  OAUTH_REDIRECT,
            "code":          code,
            "scope":         OAUTH_SCOPES,
        },
        timeout=15,
    )
    tokens = r.json()

    if "access_token" not in tokens:
        log.error(f"Token exchange failed: {tokens}")
        return web.Response(
            status=500,
            text=f"Token exchange failed: {tokens.get('error_description', '')}",
        )

    profile_r    = http_requests.get(
        "https://graph.microsoft.com/v1.0/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        timeout=10,
    )
    profile      = profile_r.json() if profile_r.ok else {}
    email        = profile.get("mail") or profile.get("userPrincipalName", "")
    display_name = profile.get("displayName", "")

    store_token(
        teams_user_id=teams_user_id,
        tenant_id=AZURE_TENANT_ID,
        email=email,
        display_name=display_name,
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token", ""),
        expires_in=tokens.get("expires_in", 3600),
    )
    log.info(f"Authenticated: {display_name} ({email})")

    return web.Response(
        content_type="text/html",
        text=(
            "<h2 style='font-family:sans-serif;color:#107C10'>Signed in successfully!</h2>"
            f"<p style='font-family:sans-serif'>Connected as <strong>{display_name}</strong> ({email}).</p>"
            "<p style='font-family:sans-serif'>You can close this tab and return to Teams.</p>"
        ),
    )


@web.middleware
async def cors_middleware(request, handler):
    response = await handler(request)
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


async def options_handler(req: web.Request) -> web.Response:
    return web.Response(
        status=200,
        headers={
            "Access-Control-Allow-Origin":  "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        },
    )


app = web.Application(middlewares=[cors_middleware])
app.router.add_post("/api/messages", messages)
app.router.add_options("/api/messages", options_handler)
app.router.add_get("/health", health)
app.router.add_get("/auth/callback", auth_callback)

if __name__ == "__main__":
    log.info(f"Starting {BOT_NAME} on port {BOT_PORT}")
    web.run_app(app, host="0.0.0.0", port=BOT_PORT)
