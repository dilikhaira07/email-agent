"""
sync_state.py
-------------
Lightweight local state store for deduplicating tasks and meetings across runs.
"""

import hashlib
import json
import os
import sqlite3
from datetime import datetime

DEFAULT_STATE_DIR = os.path.join(os.path.dirname(__file__), ".state")
STATE_PATH = os.getenv("SYNC_STATE_PATH") or os.path.join(DEFAULT_STATE_DIR, "synced_items.db")
STATE_DIR = os.path.dirname(STATE_PATH)
MAX_ITEMS_PER_KIND = int(os.getenv("SYNC_STATE_MAX_ITEMS", "1000"))


def _normalize(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip().lower()


def _hash_parts(parts: list[str]) -> str:
    payload = "||".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def task_key(task: dict) -> str:
    return _hash_parts([
        _normalize(task.get("title")),
        _normalize(task.get("action")),
        _normalize(task.get("body")),
        _normalize(task.get("urgent")),
        _normalize(task.get("due_date")),
    ])


def meeting_key(meeting: dict) -> str:
    return _hash_parts([
        _normalize(meeting.get("title")),
        _normalize(meeting.get("date")),
        _normalize(meeting.get("attendees")),
        _normalize(meeting.get("agenda")),
        _normalize(meeting.get("status")),
        _normalize(meeting.get("link")),
    ])


def load_state() -> dict:
    if _is_json_state():
        return _load_json_state()
    return _load_sqlite_state()


def save_state(state: dict) -> None:
    if _is_json_state():
        _save_json_state(state)
        return
    _save_sqlite_state(state)


def remember_items(state: dict, kind: str, keys: list[str]) -> None:
    entries = state.setdefault(kind, {})
    stamped = datetime.now().isoformat(timespec="seconds")
    for key in keys:
        entries[key] = stamped


def filter_new_items(items: list[dict], kind: str, state: dict, key_fn) -> tuple[list[dict], list[str]]:
    seen_in_run = set()
    existing = set(state.get(kind, {}))
    fresh_items = []
    fresh_keys = []
    for item in items:
        item_key = key_fn(item)
        if item_key in existing or item_key in seen_in_run:
            continue
        seen_in_run.add(item_key)
        fresh_items.append(item)
        fresh_keys.append(item_key)
    return fresh_items, fresh_keys


def _is_json_state() -> bool:
    return STATE_PATH.lower().endswith(".json")


def _load_json_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {"tasks": {}, "meetings": {}}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"tasks": {}, "meetings": {}}
    return {
        "tasks": dict(data.get("tasks", {})),
        "meetings": dict(data.get("meetings", {})),
    }


def _save_json_state(state: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    trimmed = {
        "tasks": _trim_entries(state.get("tasks", {})),
        "meetings": _trim_entries(state.get("meetings", {})),
    }
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, indent=2, sort_keys=True)


def _load_sqlite_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {"tasks": {}, "meetings": {}}
    with _connect() as conn:
        _ensure_schema(conn)
        state = {"tasks": {}, "meetings": {}}
        for kind in ("tasks", "meetings"):
            rows = conn.execute(
                "SELECT item_key, created_at FROM synced_items WHERE kind = ? ORDER BY created_at DESC LIMIT ?",
                (kind, MAX_ITEMS_PER_KIND),
            ).fetchall()
            state[kind] = {row[0]: row[1] for row in rows}
        return state


def _save_sqlite_state(state: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with _connect() as conn:
        _ensure_schema(conn)
        conn.execute("DELETE FROM synced_items")
        for kind in ("tasks", "meetings"):
            entries = _trim_entries(state.get(kind, {}))
            conn.executemany(
                "INSERT OR REPLACE INTO synced_items (kind, item_key, created_at) VALUES (?, ?, ?)",
                [(kind, key, created_at) for key, created_at in entries.items()],
            )
        conn.commit()


def _connect() -> sqlite3.Connection:
    os.makedirs(STATE_DIR, exist_ok=True)
    return sqlite3.connect(STATE_PATH)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS synced_items (
            kind TEXT NOT NULL,
            item_key TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (kind, item_key)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_synced_items_kind_created_at ON synced_items (kind, created_at DESC)"
    )


def _trim_entries(entries: dict) -> dict:
    if len(entries) <= MAX_ITEMS_PER_KIND:
        return entries
    ordered = sorted(entries.items(), key=lambda item: item[1], reverse=True)
    return dict(ordered[:MAX_ITEMS_PER_KIND])
