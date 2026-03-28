"""
telegram_bot.py
---------------
OpenAI chatbot for Telegram using webhooks (runs as a web service on Render).
Telegram pushes messages to this server — no polling needed.
"""

import os
import logging
from html import escape
from dotenv import load_dotenv
from flask import Flask, request

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from .http_client import post_json
except ImportError:
    from http_client import post_json

load_dotenv()

BOT_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN")
AUTHORIZED_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET")
PORT          = int(os.getenv("PORT", 5000))

client  = OpenAI(api_key=OPENAI_API_KEY) if OpenAI and OPENAI_API_KEY else None
app     = Flask(__name__)
history: list[dict] = []
pinned_command_messages: dict[int, int] = {}

logging.basicConfig(level=logging.INFO)

SYSTEM_PROMPT = (
    "You are Dilpreet's personal assistant. "
    "He is an IT Network and Fibre Facilities Technician in Winnipeg. "
    "Always reply in 1-3 sentences max. No preamble, no fluff, no sign-offs. "
    "Direct answers only. If you don't know something, say so in one sentence."
)
BUILD_MARKER = "BOT BUILD: TASK-COMMANDS-V3"
HELP_TEXT = (
    f"{BUILD_MARKER}\n\n"
    "Commands:\n"
    "/tasks or /task - list current open tasks\n"
    "/add <task> - add a task to Notion\n"
    "/done <number> - mark a listed task done\n"
    "/delete <number> - archive a listed task\n"
    "/clear - clear chat history"
)
COMMAND_FOOTER = (
    "\n\n"
    "<i>Commands: /tasks | /task | /add &lt;task&gt; | /done &lt;n&gt; | /delete &lt;n&gt; | /help | /clear</i>"
)


def send(chat_id: int, text: str):
    send_payload(chat_id, {"text": _with_command_footer(text), "parse_mode": "HTML"})


def send_payload(chat_id: int, payload: dict):
    response = post_json(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        {"chat_id": chat_id, **payload},
    )
    if response.status_code != 200:
        logging.error("Telegram send failed: status=%s body=%s", response.status_code, response.text[:500])
        return None
    try:
        return response.json()
    except ValueError:
        logging.error("Telegram send returned non-JSON body.")
        return None


def _safe(text) -> str:
    return escape("" if text is None else str(text), quote=True)


def _with_command_footer(text: str) -> str:
    if COMMAND_FOOTER in (text or ""):
        return text
    return f"{text}{COMMAND_FOOTER}"


def _pin_message(chat_id: int, message_id: int):
    response = post_json(
        f"https://api.telegram.org/bot{BOT_TOKEN}/pinChatMessage",
        {"chat_id": chat_id, "message_id": message_id, "disable_notification": True},
    )
    if response.status_code != 200:
        logging.error("Telegram pin failed: status=%s body=%s", response.status_code, response.text[:500])


def _unpin_message(chat_id: int, message_id: int):
    response = post_json(
        f"https://api.telegram.org/bot{BOT_TOKEN}/unpinChatMessage",
        {"chat_id": chat_id, "message_id": message_id},
    )
    if response.status_code != 200:
        logging.error("Telegram unpin failed: status=%s body=%s", response.status_code, response.text[:500])


def _pin_command_reference(chat_id: int):
    previous_message_id = pinned_command_messages.get(chat_id)
    if previous_message_id:
        _unpin_message(chat_id, previous_message_id)

    result = send_payload(
        chat_id,
        {
            "text": f"📌 <b>Command Reference</b>\n\n{HELP_TEXT}",
            "parse_mode": "HTML",
        },
    )
    message_id = (((result or {}).get("result")) or {}).get("message_id")
    if message_id:
        pinned_command_messages[chat_id] = message_id
        _pin_message(chat_id, message_id)


def _format_task_list(tasks: list[dict]) -> str:
    if not tasks:
        return f"{BUILD_MARKER}\n\nNo open tasks."

    lines = [
        BUILD_MARKER,
        "",
        f"🗂️ <b>Open Tasks ({len(tasks)})</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for i, task in enumerate(tasks, start=1):
        title = _safe(task.get("title") or "Untitled task")
        lines.append(f"\n<b>{i}. {title}</b>")
        if task.get("priority"):
            lines.append(f"   Priority: {_safe(task['priority'])}")
        if task.get("status"):
            lines.append(f"   Status: {_safe(task['status'])}")
        if task.get("due_date"):
            lines.append(f"   Due: {_safe(str(task['due_date'])[:10])}")
    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("Use the buttons below or /done N, /delete N")
    return "\n".join(lines)


def _build_task_keyboard(tasks: list[dict]) -> dict | None:
    if not tasks:
        return None
    inline_keyboard = []
    for i, task in enumerate(tasks, start=1):
        page_id = task.get("id")
        if not page_id:
            continue
        inline_keyboard.append([
            {"text": f"Done {i}", "callback_data": f"done:{page_id}"},
            {"text": f"Delete {i}", "callback_data": f"delete:{page_id}"},
        ])
    if not inline_keyboard:
        return None
    return {"inline_keyboard": inline_keyboard}


def _task_list_payload(tasks: list[dict]) -> dict:
    payload = {
        "text": _format_task_list(tasks),
        "parse_mode": "HTML",
    }
    keyboard = _build_task_keyboard(tasks)
    if keyboard:
        payload["reply_markup"] = keyboard
    return payload


def _send_task_list(chat_id: int):
    try:
        from .notion_tasks import list_open_tasks
    except ImportError:
        from notion_tasks import list_open_tasks

    tasks = list_open_tasks(limit=10)
    send_payload(chat_id, _task_list_payload(tasks))


def _edit_task_list(chat_id: int, message_id: int):
    try:
        from .notion_tasks import list_open_tasks
    except ImportError:
        from notion_tasks import list_open_tasks

    tasks = list_open_tasks(limit=10)
    response = post_json(
        f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText",
        {
            "chat_id": chat_id,
            "message_id": message_id,
            **_task_list_payload(tasks),
        },
    )
    if response.status_code != 200:
        logging.error("Telegram edit failed: status=%s body=%s", response.status_code, response.text[:500])


def _parse_index_arg(text: str) -> int | None:
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        return None
    try:
        return int(parts[1].strip())
    except ValueError:
        return None


def _command_name(text: str) -> str:
    first = (text or "").split(maxsplit=1)[0].strip()
    if not first.startswith("/"):
        return ""
    return first.split("@", 1)[0]


def _answer_callback(callback_query_id: str, text: str):
    response = post_json(
        f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
        {"callback_query_id": callback_query_id, "text": text},
    )
    if response.status_code != 200:
        logging.error("Telegram callback answer failed: status=%s body=%s", response.status_code, response.text[:500])


def _parse_callback_data(data: str) -> tuple[str, str] | tuple[None, None]:
    if ":" not in (data or ""):
        return None, None
    action, page_id = data.split(":", 1)
    if action not in {"done", "delete"} or not page_id:
        return None, None
    return action, page_id


def _handle_task_callback(callback_query: dict) -> bool:
    callback_id = callback_query.get("id")
    data = callback_query.get("data", "")
    message = callback_query.get("message", {})
    chat_id = (message.get("chat") or {}).get("id")
    message_id = message.get("message_id")
    action, page_id = _parse_callback_data(data)
    if not callback_id or not chat_id or not message_id or not action or not page_id:
        return False

    try:
        if action == "done":
            try:
                from .notion_tasks import update_task_status
            except ImportError:
                from notion_tasks import update_task_status

            update_task_status(page_id, "Done")
            _answer_callback(callback_id, "Task marked done.")
            _edit_task_list(chat_id, message_id)
        else:
            try:
                from .notion_tasks import archive_page
            except ImportError:
                from notion_tasks import archive_page

            archive_page(page_id)
            _answer_callback(callback_id, "Task deleted.")
            _edit_task_list(chat_id, message_id)
    except Exception as e:
        logging.exception("Task callback failed: %s", e)
        _answer_callback(callback_id, "Action failed.")
        send(chat_id, f"Task action failed: {_safe(e)}")
    return True


def _handle_task_command(chat_id: int, text: str) -> bool:
    command = _command_name(text)

    if command == "/help":
        send(chat_id, HELP_TEXT)
        _pin_command_reference(chat_id)
        return True

    if command in {"/tasks", "/task"}:
        try:
            _send_task_list(chat_id)
        except Exception as e:
            logging.exception("Task listing failed: %s", e)
            send(chat_id, f"Task list failed: {_safe(e)}")
        return True

    if command == "/add":
        title = text[5:].strip()
        if not title:
            send(chat_id, "Usage: /add <task>")
            return True
        try:
            try:
                from .notion_tasks import create_manual_task
            except ImportError:
                from notion_tasks import create_manual_task

            create_manual_task(title)
            send(chat_id, f"Added task: <b>{_safe(title)}</b>")
        except Exception as e:
            logging.exception("Task create failed: %s", e)
            send(chat_id, f"Task create failed: {_safe(e)}")
        return True

    if command == "/done":
        task_index = _parse_index_arg(text)
        if not task_index:
            send(chat_id, "Usage: /done <number>. Prefer /tasks and tap the buttons.")
            return True
        try:
            try:
                from .notion_tasks import list_open_tasks, update_task_status
            except ImportError:
                from notion_tasks import list_open_tasks, update_task_status

            tasks = list_open_tasks(limit=10)
            if task_index < 1 or task_index > len(tasks):
                send(chat_id, "Task number out of range. Run /tasks first.")
                return True
            page_id = tasks[task_index - 1].get("id")
            if not page_id:
                send(chat_id, "That task could not be resolved. Run /tasks again.")
                return True
            update_task_status(page_id, "Done")
            send(chat_id, f"Marked task {task_index} done.")
            _send_task_list(chat_id)
        except Exception as e:
            logging.exception("Task complete failed: %s", e)
            send(chat_id, f"Task complete failed: {_safe(e)}")
        return True

    if command == "/delete":
        task_index = _parse_index_arg(text)
        if not task_index:
            send(chat_id, "Usage: /delete <number>. Prefer /tasks and tap the buttons.")
            return True
        try:
            try:
                from .notion_tasks import archive_page, list_open_tasks
            except ImportError:
                from notion_tasks import archive_page, list_open_tasks

            tasks = list_open_tasks(limit=10)
            if task_index < 1 or task_index > len(tasks):
                send(chat_id, "Task number out of range. Run /tasks first.")
                return True
            page_id = tasks[task_index - 1].get("id")
            if not page_id:
                send(chat_id, "That task could not be resolved. Run /tasks again.")
                return True
            archive_page(page_id)
            send(chat_id, f"Deleted task {task_index}.")
            _send_task_list(chat_id)
        except Exception as e:
            logging.exception("Task delete failed: %s", e)
            send(chat_id, f"Task delete failed: {_safe(e)}")
        return True

    return False


@app.route("/webhook", methods=["POST"])
def webhook():
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        logging.warning("Rejected webhook request with invalid secret token.")
        return "forbidden", 403

    data    = request.get_json(silent=True) or {}
    callback_query = data.get("callback_query")
    if callback_query:
        callback_chat_id = ((callback_query.get("message") or {}).get("chat") or {}).get("id")
        if callback_chat_id == AUTHORIZED_ID and _handle_task_callback(callback_query):
            return "ok"
        return "ok"

    message = data.get("message") or data.get("edited_message", {})
    chat_id = message.get("chat", {}).get("id")
    text    = message.get("text", "").strip()

    if not chat_id or chat_id != AUTHORIZED_ID or not text:
        return "ok"

    if text in ("/clear", "/start"):
        history.clear()
        send(chat_id, ("Ready.\n\n" + HELP_TEXT) if text == "/start" else "Cleared.")
        _pin_command_reference(chat_id)
        return "ok"

    if _handle_task_command(chat_id, text):
        return "ok"

    if client is None:
        send(chat_id, "Chat replies are disabled because no OpenAI API key is configured. Task commands still work.")
        return "ok"

    history.append({"role": "user", "content": text})

    try:
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *history[-20:],
            ],
        )
        reply = response.output_text.strip()
    except Exception as e:
        reply = f"Error: {e}"

    history.append({"role": "assistant", "content": reply})
    send(chat_id, reply)
    return "ok"


@app.route("/")
def health():
    return "ok"


def set_webhook():
    url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    if url:
        response = post_json(
            f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
            {"url": f"{url}/webhook", "secret_token": WEBHOOK_SECRET},
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {"status_code": response.status_code, "body": response.text[:500]}
        logging.info("Webhook registration response: %s", payload)
    else:
        logging.warning("RENDER_EXTERNAL_URL not set — webhook not registered.")


def validate_config():
    missing = []
    required = {
        "TELEGRAM_BOT_TOKEN": BOT_TOKEN,
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID"),
        "TELEGRAM_WEBHOOK_SECRET": WEBHOOK_SECRET,
    }
    for key, value in required.items():
        if not value:
            missing.append(key)
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


if __name__ == "__main__":
    validate_config()
    set_webhook()
    app.run(host="0.0.0.0", port=PORT)
