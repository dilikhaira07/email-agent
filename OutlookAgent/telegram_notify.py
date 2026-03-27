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
    urgent   = [t for t in tasks if t.get("urgent")]
    thisweek = [t for t in tasks if not t.get("urgent")]

    lines = ["<b>Email Sync Complete</b>"]
    lines.append(f"{len(tasks)} task(s) | {len(meetings)} meeting(s)\n")

    if urgent:
        lines.append("<b>URGENT</b>")
        for t in urgent:
            lines.append(f"  - {t['title']}")

    if thisweek:
        lines.append("\n<b>This Week</b>")
        for t in thisweek[:5]:  # cap at 5 to keep message short
            lines.append(f"  - {t['title']}")
        if len(thisweek) > 5:
            lines.append(f"  ...and {len(thisweek) - 5} more")

    if meetings:
        lines.append("\n<b>Meetings</b>")
        for m in meetings:
            date = f" ({m['date']})" if m.get("date") else ""
            lines.append(f"  - {m['title']}{date}")

    return "\n".join(lines)


def notify(tasks: list[dict], meetings: list[dict]):
    msg = build_summary(tasks, meetings)
    send_message(msg)
