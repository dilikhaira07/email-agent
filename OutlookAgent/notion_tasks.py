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

try:
    from .app_logging import get_logger
    from .http_client import patch_json, post_json
except ImportError:
    from app_logging import get_logger
    from http_client import patch_json, post_json

load_dotenv()

NOTION_TOKEN          = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID    = os.getenv("NOTION_DATABASE_ID")
NOTION_MEETINGS_DB_ID = os.getenv("NOTION_MEETINGS_DB_ID")

NOTION_API_VERSION = "2022-06-28"
BASE_URL           = "https://api.notion.com/v1"
logger = get_logger("email_agent.notion")


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


def _query_database(database_id: str, payload: dict) -> list[dict]:
    response = post_json(f"{BASE_URL}/databases/{database_id}/query", payload, headers=_headers())
    response.raise_for_status()
    body = response.json()
    return body.get("results", [])


def _priority_label(task: dict) -> str:
    if task.get("urgent"):
        return "Urgent"
    due = task.get("due_date")
    if due:
        return "This Week"
    return "Low Priority"


def _priority_emoji(task: dict) -> str:
    label = _priority_label(task)
    return {"Urgent": "🔴", "This Week": "🟡", "Low Priority": "🟢"}.get(label, "")


def _task_display_title(task: dict) -> str:
    emoji = _priority_emoji(task)
    raw_title = _strip_phones(task.get("title", "Untitled Task"))
    return f"{emoji} {raw_title}" if emoji else raw_title


def _meeting_display_title(meeting: dict) -> str:
    status = meeting.get("status", "Needs Scheduling")
    status_emoji = {"Needs Scheduling": "🔲", "Scheduled": "🟦", "Confirmed": "✅"}.get(status, "📅")
    raw_title = _strip_phones(meeting.get("title", "Untitled Meeting"))
    return f"{status_emoji} {raw_title}"


def _property_plain_text(page: dict, property_name: str) -> str:
    prop = (page.get("properties") or {}).get(property_name) or {}
    if "title" in prop:
        return "".join(part.get("plain_text", "") for part in prop.get("title", []))
    if "rich_text" in prop:
        return "".join(part.get("plain_text", "") for part in prop.get("rich_text", []))
    return ""


def _property_date(page: dict, property_name: str) -> str | None:
    prop = (page.get("properties") or {}).get(property_name) or {}
    date_value = prop.get("date") or {}
    return date_value.get("start")


def _property_select_name(page: dict, property_name: str) -> str | None:
    prop = (page.get("properties") or {}).get(property_name) or {}
    select_value = prop.get("select") or {}
    return select_value.get("name")


def task_exists(task: dict) -> bool:
    display_title = _task_display_title(task)[:100]
    due_date = task.get("due_date")
    due_start = due_date[:10] if due_date else None
    results = _query_database(
        NOTION_DATABASE_ID,
        {
            "filter": {
                "property": "Task",
                "title": {"equals": display_title},
            },
            "page_size": 10,
        },
    )
    for page in results:
        existing_title = _property_plain_text(page, "Task")
        existing_due = _property_date(page, "Due Date")
        if existing_title == display_title and existing_due == due_start:
            return True
    return False


def meeting_exists(meeting: dict) -> bool:
    display_title = _meeting_display_title(meeting)[:100]
    meeting_date = meeting.get("date")
    results = _query_database(
        NOTION_MEETINGS_DB_ID,
        {
            "filter": {
                "property": "Meeting",
                "title": {"equals": display_title},
            },
            "page_size": 10,
        },
    )
    for page in results:
        existing_title = _property_plain_text(page, "Meeting")
        existing_date = _property_date(page, "Date")
        if existing_title == display_title and existing_date == meeting_date:
            return True
    return False


def create_task(task: dict) -> dict:
    """
    Creates a single page (task) in the Notion database.

    Expected task keys:
        title    (str)  — task title
        body     (str)  — details / context
        urgent   (bool) — drives Priority field
        due_date (str)  — ISO date string e.g. "2026-03-27T00:00:00", or None
    """
    display_title = _task_display_title(task)

    properties = {
        "Task": {
            "title": [{"text": {"content": display_title[:100]}}]
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

    action_text = _strip_phones(task.get("action", ""))
    body_text   = _strip_phones(task.get("body", ""))
    details_parts = []
    if action_text:
        details_parts.append(f"→ {action_text}")
    if body_text:
        details_parts.append(f"Context: {body_text}")
    details = "\n\n".join(details_parts)
    if details:
        properties["Details"] = {
            "rich_text": [{"text": {"content": details[:2000]}}]
        }

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": properties,
    }

    r = post_json(f"{BASE_URL}/pages", payload, headers=_headers())
    r.raise_for_status()
    return r.json()


def create_manual_task(title: str) -> dict:
    return create_task({
        "title": title,
        "action": "",
        "body": "Added from Telegram",
        "urgent": False,
        "due_date": None,
    })


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
    status = meeting.get("status", "Needs Scheduling")
    display_title = _meeting_display_title(meeting)

    properties = {
        "Meeting": {
            "title": [{"text": {"content": display_title[:100]}}]
        },
        "Status": {
            "select": {"name": status}
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

    r = post_json(f"{BASE_URL}/pages", payload, headers=_headers())
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
        logger.info("No meetings to push.")
        return []

    logger.info("Pushing meetings to Notion count=%s", len(meetings))
    created = []
    for m in meetings:
        try:
            if meeting_exists(m):
                logger.info("Skipping existing meeting title=%s date=%s", m.get("title"), m.get("date"))
                continue
            page = create_meeting(m)
            created.append(page)
            link_label = f" | {m['link']}" if m.get("link") else ""
            logger.info("Created meeting title=%s date=%s%s", m["title"], m.get("date", "no date"), link_label)
        except requests.HTTPError as e:
            logger.error("Failed to create meeting title=%s response=%s", m.get("title"), e.response.text)
        except requests.RequestException as e:
            logger.error("Failed to create meeting title=%s error=%s", m.get("title"), e)

    logger.info("Finished meeting sync created=%s total=%s", len(created), len(meetings))
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
        logger.info("No tasks to push.")
        return []

    logger.info("Pushing tasks to Notion count=%s", len(tasks))
    created = []
    for t in tasks:
        try:
            if task_exists(t):
                logger.info("Skipping existing task title=%s due_date=%s", t.get("title"), t.get("due_date"))
                continue
            page = create_task(t)
            created.append(page)
            priority = _priority_label(t)
            logger.info("Created task priority=%s title=%s", priority, t["title"])
        except requests.HTTPError as e:
            logger.error("Failed to create task title=%s response=%s", t.get("title"), e.response.text)
        except requests.RequestException as e:
            logger.error("Failed to create task title=%s error=%s", t.get("title"), e)

    logger.info("Finished task sync created=%s total=%s", len(created), len(tasks))
    return created


def list_open_tasks(limit: int = 10) -> list[dict]:
    if not NOTION_TOKEN:
        raise RuntimeError("NOTION_TOKEN is not set in .env")
    if not NOTION_DATABASE_ID:
        raise RuntimeError("NOTION_DATABASE_ID is not set in .env")

    results = _query_database(
        NOTION_DATABASE_ID,
        {
            "filter": {
                "property": "Status",
                "select": {"does_not_equal": "Done"},
            },
            "sorts": [
                {"property": "Due Date", "direction": "ascending"},
                {"timestamp": "created_time", "direction": "descending"},
            ],
            "page_size": limit,
        },
    )

    tasks = []
    for page in results:
        tasks.append({
            "id": page.get("id"),
            "title": _property_plain_text(page, "Task"),
            "status": _property_select_name(page, "Status"),
            "priority": _property_select_name(page, "Priority"),
            "due_date": _property_date(page, "Due Date"),
        })
    return tasks


def update_task_status(page_id: str, status: str) -> dict:
    response = patch_json(
        f"{BASE_URL}/pages/{page_id}",
        {
            "properties": {
                "Status": {
                    "select": {"name": status}
                }
            }
        },
        headers=_headers(),
    )
    response.raise_for_status()
    return response.json()


def archive_page(page_id: str) -> dict:
    response = patch_json(
        f"{BASE_URL}/pages/{page_id}",
        {"archived": True},
        headers=_headers(),
    )
    response.raise_for_status()
    return response.json()
