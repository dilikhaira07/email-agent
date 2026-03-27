"""
notion_tasks.py
---------------
Pushes tasks extracted from emails into a Notion database.

Required .env variables:
    NOTION_TOKEN       — Internal Integration Token from notion.so/my-integrations
    NOTION_DATABASE_ID — ID of your Notion task database (shared with the integration)
"""

import os
import re
import requests
from dotenv import load_dotenv

load_dotenv()

NOTION_TOKEN          = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID    = os.getenv("NOTION_DATABASE_ID")
NOTION_MEETINGS_DB_ID = os.getenv("NOTION_MEETINGS_DB_ID")

NOTION_API_VERSION = "2022-06-28"
BASE_URL           = "https://api.notion.com/v1"


_PHONE_RE = re.compile(
    r'\+?1?[\s.\-]?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}'
    r'(?:[\s,]*(?:ext|x)[\s.]?\d+)?'
    r'|(?:tel|phone|ph|fax):\s*[\d\s.\-\(\)#,+]+',
    re.IGNORECASE
)

def _strip_phones(text: str) -> str:
    return _PHONE_RE.sub('', text).strip()


def _headers() -> dict:
    return {
        "Authorization":  f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_API_VERSION,
        "Content-Type":   "application/json",
    }


def _priority_label(task: dict) -> str:
    if task.get("urgent"):
        return "Urgent"
    due = task.get("due_date")
    if due:
        return "This Week"
    return "Low Priority"


def create_task(task: dict) -> dict:
    """
    Creates a single page (task) in the Notion database.

    Expected task keys:
        title    (str)  — task title
        body     (str)  — details / context
        urgent   (bool) — drives Priority field
        due_date (str)  — ISO date string e.g. "2026-03-27T00:00:00", or None
    """
    properties = {
        "Task": {
            "title": [{"text": {"content": _strip_phones(task.get("title", "Untitled Task"))[:100]}}]
        },
        "Priority": {
            "select": {"name": _priority_label(task)}
        },
        "Status": {
            "select": {"name": "To Do"}
        },
    }

    due = task.get("due_date")
    if due:
        # Notion date field wants YYYY-MM-DD
        date_str = due[:10]
        properties["Due Date"] = {"date": {"start": date_str}}

    body_text = _strip_phones(task.get("body", ""))
    if body_text:
        properties["Details"] = {
            "rich_text": [{"text": {"content": body_text[:2000]}}]
        }

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": properties,
    }

    r = requests.post(f"{BASE_URL}/pages", headers=_headers(), json=payload)
    r.raise_for_status()
    return r.json()


def create_meeting(meeting: dict) -> dict:
    """
    Creates a single meeting page in the Meeting Invites database.

    Expected meeting keys:
        title      (str)  — meeting name
        date       (str)  — ISO date string e.g. "2026-03-30", or None
        attendees  (str)  — comma-separated names
        agenda     (str)  — what the meeting is about
        status     (str)  — "Needs Scheduling" | "Scheduled" | "Confirmed"
    """
    properties = {
        "Meeting": {
            "title": [{"text": {"content": _strip_phones(meeting.get("title", "Untitled Meeting"))[:100]}}]
        },
        "Status": {
            "select": {"name": meeting.get("status", "Needs Scheduling")}
        },
    }

    date_str = meeting.get("date")
    if date_str:
        properties["Date"] = {"date": {"start": date_str[:10]}}

    attendees = _strip_phones(meeting.get("attendees", ""))
    if attendees:
        properties["Attendees"] = {
            "rich_text": [{"text": {"content": attendees[:2000]}}]
        }

    agenda = _strip_phones(meeting.get("agenda", ""))
    if agenda:
        properties["Agenda"] = {
            "rich_text": [{"text": {"content": agenda[:2000]}}]
        }

    link = meeting.get("link")
    if link:
        properties["Link"] = {"url": link}

    payload = {
        "parent": {"database_id": NOTION_MEETINGS_DB_ID},
        "properties": properties,
    }

    r = requests.post(f"{BASE_URL}/pages", headers=_headers(), json=payload)
    r.raise_for_status()
    return r.json()


def push_meetings_to_notion(meetings: list[dict]) -> list[dict]:
    """
    Pushes a list of meeting dicts into the Notion Meeting Invites database.

    Args:
        meetings: List of dicts with keys: title, date, attendees, agenda, status

    Returns:
        List of created Notion page objects.
    """
    if not NOTION_TOKEN:
        raise RuntimeError("NOTION_TOKEN is not set in .env")
    if not NOTION_MEETINGS_DB_ID:
        raise RuntimeError("NOTION_MEETINGS_DB_ID is not set in .env")
    if not meetings:
        print("[Notion] No meetings to push.")
        return []

    print(f"\n[Notion] Pushing {len(meetings)} meeting(s) to Meeting Invites...")
    created = []
    for m in meetings:
        try:
            page = create_meeting(m)
            created.append(page)
            link_label = f" | {m['link']}" if m.get("link") else ""
            print(f"  [+] {m['title']} ({m.get('date', 'no date')}){link_label}")
        except requests.HTTPError as e:
            print(f"  [!] Failed to create '{m.get('title')}': {e.response.text}")

    print(f"[Notion] Done — {len(created)}/{len(meetings)} meetings added.\n")
    return created


def push_tasks_to_notion(tasks: list[dict]) -> list[dict]:
    """
    Pushes a list of task dicts into the Notion database.

    Args:
        tasks: List of dicts with keys: title, body, urgent, due_date

    Returns:
        List of created Notion page objects.
    """
    if not NOTION_TOKEN:
        raise RuntimeError("NOTION_TOKEN is not set in .env")
    if not NOTION_DATABASE_ID:
        raise RuntimeError("NOTION_DATABASE_ID is not set in .env")
    if not tasks:
        print("[Notion] No tasks to push.")
        return []

    print(f"\n[Notion] Pushing {len(tasks)} task(s) to Notion...")
    created = []
    for t in tasks:
        try:
            page = create_task(t)
            created.append(page)
            priority = _priority_label(t)
            print(f"  [+] [{priority}] {t['title']}")
        except requests.HTTPError as e:
            print(f"  [!] Failed to create '{t.get('title')}': {e.response.text}")

    print(f"[Notion] Done — {len(created)}/{len(tasks)} tasks added.\n")
    return created
