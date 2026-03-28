"""
fetch_tasks.py
--------------
Fetches the last N emails (read + unread), analyzes them for remaining tasks,
saves a markdown summary to the Summary MD files folder, and pushes tasks
to Microsoft To-Do via the Graph API.
"""

import os
import re
import json
import imaplib
import email
import uuid
from email.header import decode_header
from datetime import datetime
from dotenv import load_dotenv

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from .app_logging import get_logger
from .email_normalize import build_preview
from .sync_state import (
    filter_new_items,
    load_state,
    meeting_key,
    remember_items,
    save_state,
    task_key,
)

load_dotenv()

IMAP_SERVER        = os.getenv("IMAP_SERVER")
IMAP_PORT          = int(os.getenv("IMAP_PORT", "993"))
EMAIL_ADDRESS      = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD     = os.getenv("EMAIL_PASSWORD")
IMAP_USERNAME      = os.getenv("IMAP_USERNAME") or EMAIL_ADDRESS
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL       = os.getenv("OPENAI_MODEL", "gpt-5-mini")
PUSH_TO_TODO       = os.getenv("PUSH_TO_TODO", "true").lower() == "true"

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "Summary MD files")
logger = get_logger("email_agent.sync")


# ── Email fetching ─────────────────────────────────────────────────────────────

def decode_str(value) -> str:
    if value is None:
        return ""
    decoded_parts = []
    for part, charset in decode_header(value):
        if isinstance(part, bytes):
            try:
                decoded_parts.append(part.decode(charset or "utf-8", errors="replace"))
            except Exception:
                decoded_parts.append(part.decode("utf-8", errors="replace"))
        else:
            decoded_parts.append(str(part))
    return "".join(decoded_parts)


def get_body_preview(msg, max_chars=800) -> str:
    return build_preview(msg, max_chars=max_chars)


def fetch_last_n_emails(n=50):
    logger.info("Connecting to IMAP server server=%s port=%s user=%s limit=%s", IMAP_SERVER, IMAP_PORT, IMAP_USERNAME, n)
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(IMAP_USERNAME, EMAIL_PASSWORD)
    mail.select("INBOX")

    status, data = mail.search(None, "ALL")
    if status != "OK":
        raise RuntimeError("IMAP SEARCH failed")

    all_ids = data[0].split()
    recent_ids = list(reversed(all_ids[-n:]))

    logger.info("Fetched mailbox index total_emails=%s selected=%s", len(all_ids), len(recent_ids))

    emails = []
    for uid in recent_ids:
        status, msg_data = mail.fetch(uid, "(RFC822)")
        if status != "OK" or not msg_data or msg_data[0] is None:
            continue
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        emails.append({
            "id":         uid.decode(),
            "subject":    decode_str(msg.get("Subject", "(No Subject)")),
            "sender":     decode_str(msg.get("From", "Unknown")),
            "received":   msg.get("Date", ""),
            "preview":    get_body_preview(msg),
            "importance": msg.get("Importance", msg.get("X-Priority", "normal")),
        })

    mail.close()
    mail.logout()
    return emails


# ── OpenAI analysis ────────────────────────────────────────────────────────────

def analyze_inbox(emails: list[dict]) -> dict:
    """Single OpenAI call that returns summary markdown plus structured tasks and meetings."""
    if OpenAI is None or not OPENAI_API_KEY:
        raise RuntimeError("OpenAI is not configured. Install the openai package and set OPENAI_API_KEY.")
    client = OpenAI(api_key=OPENAI_API_KEY)

    email_block = ""
    for i, e in enumerate(emails, 1):
        email_block += f"""
--- Email {i} ---
ID       : {e['id']}
Subject  : {e['subject']}
From     : {e['sender']}
Date     : {e['received']}
Importance: {e['importance']}
Preview  : {e['preview']}
"""

    today = datetime.now().strftime("%Y-%m-%d")

    prompt = f"""You are an executive assistant for Dilpreet, an IT Network and Fibre Facilities Technician.

Below are the last {len(emails)} emails from his inbox. Today is {today}.

Review them carefully and output ONLY a valid JSON object with exactly these top-level keys:
- "summary_markdown": markdown string with a concise task summary grouped into Urgent, This Week, and Low Priority
- "tasks": array of pending action items
- "meetings": array of meetings, calls, prep sessions, or scheduled events

Ignore purely informational emails with no action required.

Each task object must have exactly these keys:
- "title": short task title under 80 characters
- "action": a single imperative sentence describing the one thing Dilpreet should do now
- "body": who it involves and the supporting context in 2-3 sentences max
- "urgent": true if action is needed within 24 hours, false otherwise
- "due_date": ISO 8601 string like "2026-03-27T00:00:00" if a specific date is mentioned, otherwise null

Each meeting object must have exactly these keys:
- "title": meeting name under 80 characters
- "date": ISO date string "YYYY-MM-DD" if a specific date is mentioned, otherwise null
- "attendees": comma-separated names of who is involved
- "agenda": one sentence describing the purpose of the meeting
- "status": one of "Needs Scheduling", "Scheduled", or "Confirmed"
- "link": full URL if a Zoom, Teams, WebEx, or any meeting join link is mentioned, otherwise null

Requirements:
- Return raw JSON only, with no markdown fences or explanation.
- If there are no tasks, return "tasks": [].
- If there are no meetings, return "meetings": [].
- Keep summary_markdown concise and practical.

EMAILS:
{email_block}
"""

    logger.info("Sending emails to OpenAI for structured analysis email_count=%s", len(emails))
    response = client.responses.create(
        model=OPENAI_MODEL,
        input=prompt,
    )
    raw = response.output_text.strip()
    parsed = _parse_json_response(raw, "analysis payload")
    if not isinstance(parsed, dict):
        raise RuntimeError("OpenAI returned an invalid analysis payload.")

    return {
        "summary_markdown": str(parsed.get("summary_markdown", "")).strip(),
        "tasks": _coerce_list_of_dicts(parsed.get("tasks")),
        "meetings": _coerce_list_of_dicts(parsed.get("meetings")),
    }


def _parse_json_response(raw: str, label: str):
    raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("` \n")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse OpenAI {label} JSON: {e}")


def _coerce_list_of_dicts(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


# ── Markdown saving ────────────────────────────────────────────────────────────

def save_markdown(task_analysis: str, email_count: int) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename  = f"Task_Summary_{timestamp}.md"
    filepath  = os.path.join(OUTPUT_DIR, filename)

    content = f"""# Email Task Summary
**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M")}
**Mailbox:** {EMAIL_ADDRESS}
**Emails reviewed:** Last {email_count}

---

{task_analysis}

---
*Generated by Outlook AI Email Agent*
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info("Saved markdown summary path=%s email_count=%s", filepath, email_count)
    return filepath


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    run_id = uuid.uuid4().hex[:8]
    logger.info("Sync run started run_id=%s mailbox=%s", run_id, EMAIL_ADDRESS)
    emails = fetch_last_n_emails(25)
    if not emails:
        logger.info("No emails found run_id=%s", run_id)
    else:
        analysis = analyze_inbox(emails)
        markdown = analysis["summary_markdown"]
        tasks = analysis["tasks"]
        meetings = analysis["meetings"]
        logger.info(
            "OpenAI analysis complete run_id=%s emails=%s tasks=%s meetings=%s",
            run_id,
            len(emails),
            len(tasks),
            len(meetings),
        )

        path = save_markdown(markdown, len(emails))

        print("\n" + "="*60)
        print(markdown.encode("ascii", errors="replace").decode("ascii"))
        print("="*60)
        print(f"\nFile saved to: {path}")

        state = load_state()
        new_tasks, new_task_keys = filter_new_items(tasks, "tasks", state, task_key)
        new_meetings, new_meeting_keys = filter_new_items(meetings, "meetings", state, meeting_key)

        skipped_tasks = len(tasks) - len(new_tasks)
        skipped_meetings = len(meetings) - len(new_meetings)
        if skipped_tasks:
            logger.info("Skipping previously synced tasks run_id=%s count=%s", run_id, skipped_tasks)
        if skipped_meetings:
            logger.info("Skipping previously synced meetings run_id=%s count=%s", run_id, skipped_meetings)

        if PUSH_TO_TODO:
            from .notion_tasks import push_tasks_to_notion, push_meetings_to_notion

            if new_tasks:
                logger.info("Pushing new tasks run_id=%s count=%s", run_id, len(new_tasks))
                try:
                    push_tasks_to_notion(new_tasks)
                    remember_items(state, "tasks", new_task_keys)
                except Exception as e:
                    logger.exception("Could not push tasks run_id=%s error=%s", run_id, e)

            if new_meetings:
                logger.info("Pushing new meetings run_id=%s count=%s", run_id, len(new_meetings))
                try:
                    push_meetings_to_notion(new_meetings)
                    remember_items(state, "meetings", new_meeting_keys)
                except Exception as e:
                    logger.exception("Could not push meetings run_id=%s error=%s", run_id, e)
        else:
            logger.info("Notion sync disabled run_id=%s", run_id)

        try:
            from .telegram_notify import notify
            notify(new_tasks, new_meetings)
        except Exception as e:
            logger.exception("Could not send Telegram notification run_id=%s error=%s", run_id, e)

        if new_task_keys or new_meeting_keys:
            save_state(state)
            logger.info(
                "Sync state saved run_id=%s task_keys=%s meeting_keys=%s",
                run_id,
                len(new_task_keys),
                len(new_meeting_keys),
            )
        logger.info("Sync run completed run_id=%s", run_id)


if __name__ == "__main__":
    main()
