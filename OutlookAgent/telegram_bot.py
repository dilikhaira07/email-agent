"""
telegram_bot.py
---------------
A Telegram chatbot powered by Claude.
Responds only to the authorized user with short, direct answers.
Runs 24/7 via long-polling — deploy to Railway or any cloud host.
"""

import os
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
import anthropic
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN")
AUTHORIZED_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

SYSTEM_PROMPT = (
    "You are Dilpreet's personal assistant. "
    "He is an IT Network and Fibre Facilities Technician in Winnipeg. "
    "Always reply in 1-3 sentences max. No preamble, no fluff, no sign-offs. "
    "Direct answers only. If you don't know something, say so in one sentence."
)

# Per-user conversation history (in-memory, resets on restart)
history: list[dict] = []

logging.basicConfig(level=logging.INFO)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != AUTHORIZED_ID:
        return
    await update.message.reply_text("Ready.")


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != AUTHORIZED_ID:
        return
    history.clear()
    await update.message.reply_text("Conversation cleared.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != AUTHORIZED_ID:
        return

    user_text = update.message.text
    history.append({"role": "user", "content": user_text})

    # Keep last 20 messages for context
    recent = history[-20:]

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=SYSTEM_PROMPT,
        messages=recent,
    )

    reply = response.content[0].text.strip()
    history.append({"role": "assistant", "content": reply})

    await update.message.reply_text(reply)


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()
