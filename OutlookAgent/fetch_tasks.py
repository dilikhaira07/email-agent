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
from email.header import decode_header
from datetime import datetime
import anthropic
from dotenv import load_dotenv

load_dotenv()

IMAP_SERVER        = os.getenv("IMAP_SERVER")
IMAP_PORT          = int(os.getenv("IMAP_PORT", "993"))
EMAIL_ADDRESS      = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD     = os.getenv("EMAIL_PASSWORD")
IMAP_USERNAME      = os.getenv("IMAP_USERNAME") or EMAIL_ADDRESS
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY")
PUSH_TO_TODO       = os.getenv("PUSH_TO_TODO", "true").lower() == "true"

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "Summary MD files")


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
    preview = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                try:
                    charset = part.get_content_charset() or "utf-8"
                    preview = part.get_payload(decode=True).decode(charset, errors="replace")
                    break
                except Exception:
                    continue
    else:
        try:
            charset = msg.get_content_charset() or "utf-8"
            preview = msg.get_payload(decode=True).decode(charset, errors="replace")
        except Exception:
            pass
    return " ".join(preview.split())[:max_chars]


def fetch_last_n_emails(n=50):
    print(f"Connecting to {IMAP_SERVER}:{IMAP_PORT} as {IMAP_USERNAME}...")
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(IMAP_USERNAME, EMAIL_PASSWORD)
    mail.select("INBOX")

    status, data = mail.search(None, "ALL")
    if status != "OK":
        raise RuntimeError("IMAP SEARCH failed")

    all_ids = data[0].split()
    recent_ids = list(reversed(all_ids[-n:]))

    print(f"Found {len(all_ids)} total emails. Fetching last {len(recent_ids)}...")

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


# ── Claude analysis ────────────────────────────────────────────────────────────

def analyze_for_tasks(emails):
    """First Claude call: produces the full markdown task report."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    email_block = ""
    for i, e in enumerate(emails, 1):
        email_block += f"""
--- Email {i} ---
Subject  : {e['subject']}
From     : {e['sender']}
Date     : {e['received']}
Preview  : {e['preview']}
"""

    today = datetime.now().strftime("%Y-%m-%d")

    prompt = f"""You are an executive assistant for Dilpreet, an IT Network and Fibre Facilities Technician.

Below are the last {len(emails)} emails from his inbox. Today is {today}.

Review them carefully and produce:
1. A **Task List** of all remaining/pending action items (replies needed, tickets to action, follow-ups, approvals, etc.)
2. A **Summary** section grouping tasks by urgency: Urgent (within 24h), This Week, and Low Priority.

For each task include: what needs to be done, who it involves, due date or urgency if mentioned.
Ignore purely informational emails with no action required. Be concise and practical.

EMAILS:
{email_block}
"""

    print("Sending emails to Claude for task analysis...")
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text.strip()


def _claude_json_call(prompt: str, label: str) -> list[dict]:
    """Helper: sends a prompt to Claude and returns parsed JSON list."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    print(f"Extracting {label} from Claude...")
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = message.content[0].text.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("` \n")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[!] Failed to parse {label} JSON: {e}")
        return []


def extract_tasks_json(markdown: str) -> list[dict]:
    """Converts the markdown task report into a structured tasks JSON array."""
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = f"""Convert the following task list into a JSON array. Today is {today}.

Output ONLY a valid JSON array — no explanation, no markdown fences, just the raw JSON.

Each object must have exactly these keys:
- "title": short task title under 80 characters
- "body": who it involves and what needs to be done (1-2 sentences)
- "urgent": true if action needed within 24 hours, false otherwise
- "due_date": ISO 8601 string like "2026-03-27T00:00:00" if a specific date is mentioned, otherwise null

TASK LIST:
{markdown}
"""
    return _claude_json_call(prompt, "structured tasks")


def extract_meetings_json(markdown: str) -> list[dict]:
    """Extracts any meetings, calls, or prep sessions from the markdown task report."""
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = f"""From the task list below, extract only items that are meetings, calls, prep sessions, or scheduled events. Today is {today}.

Output ONLY a valid JSON array — no explanation, no markdown fences, just raw JSON.
If there are no meetings, output an empty array: []

Each object must have exactly these keys:
- "title": meeting name under 80 characters
- "date": ISO date string "YYYY-MM-DD" if a specific date is mentioned, otherwise null
- "attendees": comma-separated names of who is involved
- "agenda": one sentence describing the purpose of the meeting
- "status": one of "Needs Scheduling", "Scheduled", or "Confirmed"
- "link": full URL if a Zoom, Teams, WebEx, or any meeting join link is mentioned, otherwise null

TASK LIST:
{markdown}
"""
    return _claude_json_call(prompt, "meetings")


def extract_markdown(response_text: str) -> str:
    return response_text.strip()


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
    print(f"Saved: {filepath}")
    return filepath


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    emails = fetch_last_n_emails(25)
    if not emails:
        print("No emails found.")
    else:
        raw_response = analyze_for_tasks(emails)
        markdown     = extract_markdown(raw_response)
        tasks        = extract_tasks_json(raw_response)

        path = save_markdown(markdown, len(emails))

        print("\n" + "="*60)
        print(markdown.encode("ascii", errors="replace").decode("ascii"))
        print("="*60)
        print(f"\nFile saved to: {path}")

        meetings = extract_meetings_json(markdown)

        if PUSH_TO_TODO:
            from notion_tasks import push_tasks_to_notion, push_meetings_to_notion

            if tasks:
                print(f"\nExtracted {len(tasks)} task(s) from Claude.")
                try:
                    push_tasks_to_notion(tasks)
                except Exception as e:
                    print(f"[Notion] Could not push tasks: {e}")

            if meetings:
                print(f"Extracted {len(meetings)} meeting(s) from Claude.")
                try:
                    push_meetings_to_notion(meetings)
                except Exception as e:
                    print(f"[Notion] Could not push meetings: {e}")
        else:
            print("[Notion] PUSH_TO_TODO is disabled. Set PUSH_TO_TODO=true in .env to enable.")

        try:
            from telegram_notify import notify
            notify(tasks, meetings)
        except Exception as e:
            print(f"[Telegram] Could not send notification: {e}")
