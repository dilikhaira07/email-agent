"""
telegram_bot.py
---------------
Claude chatbot for Telegram using webhooks (runs as a web service on Render).
Telegram pushes messages to this server — no polling needed.
"""

import os
import logging
import requests
import anthropic
from flask import Flask, request
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN")
AUTHORIZED_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
PORT          = int(os.getenv("PORT", 5000))

client  = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
app     = Flask(__name__)
history: list[dict] = []

logging.basicConfig(level=logging.INFO)

SYSTEM_PROMPT = (
    "You are Dilpreet's personal assistant. "
    "He is an IT Network and Fibre Facilities Technician in Winnipeg. "
    "Always reply in 1-3 sentences max. No preamble, no fluff, no sign-offs. "
    "Direct answers only. If you don't know something, say so in one sentence."
)


def send(chat_id: int, text: str):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
    )


@app.route("/webhook", methods=["POST"])
def webhook():
    data    = request.get_json(silent=True) or {}
    message = data.get("message") or data.get("edited_message", {})
    chat_id = message.get("chat", {}).get("id")
    text    = message.get("text", "").strip()

    if not chat_id or chat_id != AUTHORIZED_ID or not text:
        return "ok"

    if text in ("/clear", "/start"):
        history.clear()
        send(chat_id, "Ready." if text == "/start" else "Cleared.")
        return "ok"

    history.append({"role": "user", "content": text})

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=history[-20:],
        )
        reply = response.content[0].text.strip()
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
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
            json={"url": f"{url}/webhook"},
        )
        logging.info(f"Webhook set: {r.json()}")
    else:
        logging.warning("RENDER_EXTERNAL_URL not set — webhook not registered.")


if __name__ == "__main__":
    set_webhook()
    app.run(host="0.0.0.0", port=PORT)
