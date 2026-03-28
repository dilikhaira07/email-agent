"""
telegram_notify.py
------------------
Sends a task summary to a Telegram chat via Bot API.

Required .env variables:
    TELEGRAM_BOT_TOKEN — token from @BotFather
    TELEGRAM_CHAT_ID   — your personal chat ID
"""

import os
from html import escape
from dotenv import load_dotenv

from .app_logging import get_logger
from .http_client import post_json

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
API_URL   = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
logger = get_logger("email_agent.telegram_notify")
MAX_TEXT_LEN = 140


def _safe(text) -> str:
    return escape("" if text is None else str(text), quote=True)


def _short(text, max_len: int = MAX_TEXT_LEN) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= max_len:
        return value
    return value[: max_len - 3].rstrip() + "..."


def _fmt_date(date_value) -> str:
    if not date_value:
        return ""
    return str(date_value)[:10]


def send_message(text: str):
    if not BOT_TOKEN or not CHAT_ID:
        logger.info("Telegram notification skipped because bot token or chat id is missing.")
        return
    r = post_json(API_URL, {
        "chat_id":    CHAT_ID,
        "text":       text,
        "parse_mode": "HTML",
    })
    if r.status_code == 200:
        logger.info("Telegram summary message sent.")
    else:
        logger.error("Telegram summary message failed status=%s body=%s", r.status_code, r.text[:500])


def build_summary(tasks: list[dict], meetings: list[dict]) -> str:
    from datetime import datetime
    urgent   = [t for t in tasks if t.get("urgent")]
    thisweek = [t for t in tasks if not t.get("urgent")]
    today    = datetime.now().strftime("%a, %b %d %Y")
    total_items = len(tasks) + len(meetings)

    lines = [
        f"📬 <b>Daily Email Brief — {today}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━",
        f"<b>New items:</b> {total_items}",
    ]

    if not total_items:
        lines.append("\nNo new tasks or meetings found.")

    if urgent:
        lines.append(f"\n🔴 <b>URGENT ({len(urgent)})</b>")
        for i, t in enumerate(urgent, 1):
            lines.append(f"\n<b>{i}. {_safe(_short(t.get('title', 'Untitled task')))}</b>")
            if t.get("action"):
                lines.append(f"   Action: {_safe(_short(t['action']))}")
            if t.get("due_date"):
                lines.append(f"   Due: {_safe(_fmt_date(t['due_date']))}")

    if thisweek:
        lines.append(f"\n🟡 <b>THIS WEEK ({len(thisweek)})</b>")
        for t in thisweek[:6]:
            lines.append(f"\n• <b>{_safe(_short(t.get('title', 'Untitled task')))}</b>")
            if t.get("action"):
                lines.append(f"  Action: {_safe(_short(t['action']))}")
            if t.get("due_date"):
                lines.append(f"  Due: {_safe(_fmt_date(t['due_date']))}")
        if len(thisweek) > 6:
            lines.append(f"\n  <i>+{len(thisweek) - 6} more — see Notion</i>")

    if meetings:
        lines.append(f"\n📅 <b>MEETINGS ({len(meetings)})</b>")
        for m in meetings:
            title = _safe(_short(m.get("title", "Untitled meeting")))
            lines.append(f"\n• <b>{title}</b>")
            if m.get("date"):
                lines.append(f"  Date: {_safe(_fmt_date(m['date']))}")
            if m.get("status"):
                lines.append(f"  Status: {_safe(m['status'])}")
            if m.get("agenda"):
                lines.append(f"  Agenda: {_safe(_short(m['agenda']))}")
            if m.get("link"):
                lines.append(f"  🔗 <a href=\"{_safe(m['link'])}\">Join meeting</a>")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("✅ Notion sync complete")

    return "\n".join(lines)


def notify(tasks: list[dict], meetings: list[dict]):
    msg = build_summary(tasks, meetings)
    send_message(msg)
