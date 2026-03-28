# Email Agent

This repo currently contains two separate services built around the same mailbox and OpenAI account:

1. `OutlookAgent.fetch_tasks`
   Scheduled email sync pipeline. It fetches recent IMAP email, normalizes message bodies, asks OpenAI for a structured summary, dedupes tasks and meetings, pushes new items into Notion, and sends a Telegram digest.

2. `OutlookAgent.telegram_bot`
   Telegram webhook chatbot. It runs as a web service and answers messages from one authorized Telegram chat using OpenAI.

These services share some support modules, but they are operationally distinct and should be treated that way.

## Entrypoints

- Email sync pipeline: `python -m OutlookAgent.fetch_tasks`
- Telegram webhook bot: `python -m OutlookAgent.telegram_bot`
- Legacy console-only email triage loop: `python -m OutlookAgent.main`

`main.py` is still present, but the richer sync workflow is `fetch_tasks.py`.

## Canonical Path

If you are choosing one operational workflow, use `python -m OutlookAgent.fetch_tasks`.

Use `OutlookAgent.main` only for manual console triage when you explicitly do not want:

- Notion sync
- Telegram summary delivery
- sync-state dedupe
- structured task and meeting extraction pipeline

## Requirements

- Python 3.11+
- IMAP mailbox credentials
- OpenAI API key
- Notion integration token and database IDs for sync
- Telegram bot token and personal chat ID for notifications

Install dependencies:

```powershell
python -m pip install -r OutlookAgent/requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and fill in the values you actually use.

Important groups:

- IMAP: mailbox access for email fetch
- OpenAI: `OPENAI_API_KEY`
- Notion: task and meeting database targets
- Telegram notify: digest delivery
- Telegram webhook bot: public bot service settings, including `TELEGRAM_WEBHOOK_SECRET`

## Running Locally

Email sync:

```powershell
python -m OutlookAgent.fetch_tasks
```

Telegram webhook bot:

```powershell
python -m OutlookAgent.telegram_bot
```

For the webhook bot, `RENDER_EXTERNAL_URL` must point to the public base URL when registering the Telegram webhook.

## Deployment Notes

- `render.yaml` now defines two Render services:
- `telegram-claude-bot` as a web service
- `email-sync` as a cron job
- The bot now requires `TELEGRAM_WEBHOOK_SECRET` in the deployment environment.
- The sync cron job runs `python -m OutlookAgent.scheduled_sync`.
- The Render cron schedule is `45 * * * *`, which means every hour at `:45` UTC.
- `OutlookAgent.scheduled_sync` then checks local Winnipeg time and only runs the sync at:
- `8:45 AM`
- `9:45 AM`
- `10:45 AM`
- `11:45 AM`
- `12:45 PM`
- `1:45 PM`
- This avoids daylight saving time drift without needing to rewrite the cron expression seasonally.
- `Procfile` is aligned to a web process for platforms that use Procfiles.

## State And Output

- Markdown summaries are written under `OutlookAgent/Summary MD files/`
- Dedupe state is written under `OutlookAgent/.state/synced_items.db` by default
- You can override the dedupe file location with `SYNC_STATE_PATH`

## Current Architecture

Shared modules:

- `email_normalize.py`: email body parsing and link-preserving previews
- `http_client.py`: bounded retries and network timeouts
- `sync_state.py`: local dedupe across runs
- `app_logging.py`: shared logging setup

Service modules:

- `fetch_tasks.py`: scheduled sync workflow
- `telegram_bot.py`: Telegram webhook assistant
- `telegram_notify.py`: Telegram digest sender
- `notion_tasks.py`: Notion task and meeting writes

## Operational Notes

- The Telegram bot only accepts webhook requests with the configured secret token.
- The sync pipeline dedupes tasks and meetings locally before pushing to Notion or Telegram.
- The OpenAI extraction path is single-pass structured JSON, not markdown followed by re-parsing.
- Local dedupe state now uses SQLite by default for safer persistence than a flat JSON file.
- Local dedupe state still requires persistent storage. On stateless cron platforms, set `SYNC_STATE_PATH` to a persistent location or move dedupe state to an external store.
