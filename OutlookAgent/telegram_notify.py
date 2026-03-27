"""
telegram_notify.py
------------------
Sends a task summary to a Telegram chat via Bot API.

Required .env variables:
    TELEGRAM_BOT_TOKEN — token from @BotFather
    TELEGRAM_CHAT_ID   — your personal chat ID
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
API_URL   = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


def send_message(text: str):
    if not BOT_TOKEN or not CHAT_ID:
        print("[Telegram] Skipped — TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set.")
        return
    r = requests.post(API_URL, json={
        "chat_id":    CHAT_ID,
        "text":       text,
        "parse_mode": "HTML",
    })
    if r.status_code == 200:
        print("[Telegram] Message sent.")
    else:
        print(f"[Telegram] Failed: {r.text}")


def build_summary(tasks: list[dict], meetings: list[dict]) -> str:
    from datetime import datetime
    urgent   = [t for t in tasks if t.get("urgent")]
    thisweek = [t for t in tasks if not t.get("urgent")]
    today    = datetime.now().strftime("%a, %b %d %Y")

    lines = [
        f"📬 <b>Daily Email Brief</b>",
        f"<i>{today}</i>",
        "─────────────────────",
    ]

    if urgent:
        lines.append(f"\n🔴 <b>URGENT  ({len(urgent)})</b>")
        for t in urgent:
            due = f"  <i>Due: {t['due_date'][:10]}</i>" if t.get("due_date") else ""
            lines.append(f"• {t['title']}{due}")

    if thisweek:
        lines.append(f"\n🟡 <b>THIS WEEK  ({len(thisweek)})</b>")
        for t in thisweek[:6]:
            lines.append(f"• {t['title']}")
        if len(thisweek) > 6:
            lines.append(f"  <i>+{len(thisweek) - 6} more in Notion</i>")

    if meetings:
        lines.append(f"\n📅 <b>MEETINGS  ({len(meetings)})</b>")
        for m in meetings:
            date = f" — {m['date']}" if m.get("date") else ""
            link = f"\n  🔗 <a href=\"{m['link']}\">Join</a>" if m.get("link") else ""
            lines.append(f"• {m['title']}{date}{link}")

    lines.append("\n─────────────────────")
    lines.append("✅ Notion synced")

    return "\n".join(lines)


def notify(tasks: list[dict], meetings: list[dict]):
    msg = build_summary(tasks, meetings)
    send_message(msg)
