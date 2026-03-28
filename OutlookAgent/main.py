"""
main.py
-------
Legacy console-only email triage loop.

This module remains available for simple mailbox triage, but the canonical
workflow in this repo is `python -m OutlookAgent.fetch_tasks`, which performs:
  1. structured OpenAI extraction
  2. Notion sync
  3. Telegram summary delivery

Usage:
    python -m OutlookAgent.main
"""

import os
import schedule
import time
from datetime import datetime
from dotenv import load_dotenv

from .outlook import fetch_emails
from .claude_agent import analyze_emails

load_dotenv()

# How many unread emails to fetch and analyze per run
MAX_EMAILS = 10

# How often to run the agent (in minutes)
SCHEDULE_INTERVAL_MINUTES = 60


def run_agent():
    """
    Main agent loop: fetch emails, analyze them with OpenAI, print a report.
    Errors are caught and logged so the scheduler keeps running.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    account = os.getenv("EMAIL_ADDRESS", "unknown")

    print(f"\n{'='*60}")
    print(f"  Outlook AI Agent — Run started at {timestamp}")
    print(f"  Mailbox: {account}")
    print(f"{'='*60}")

    # Step 1: Fetch unread emails via IMAP
    try:
        print(f"\n[1/2] Fetching up to {MAX_EMAILS} unread emails...")
        emails = fetch_emails(max_emails=MAX_EMAILS)
        print(f"      Found {len(emails)} unread email(s).")
    except RuntimeError as e:
        print(f"\n[ERROR] Could not fetch emails:\n  {e}")
        print("  The agent will retry on the next scheduled run.")
        return

    if not emails:
        print("\n  Inbox is clear — no unread emails to process.")
        return

    # Step 2: Analyze emails with OpenAI
    print(f"\n[2/2] Sending emails to OpenAI ({len(emails)} to analyze)...")
    try:
        analyzed = analyze_emails(emails)
    except RuntimeError as e:
        print(f"\n[ERROR] OpenAI analysis failed:\n  {e}")
        return

    # Step 3: Print formatted report
    print(f"\n{'─'*60}")
    print(f"  EMAIL ANALYSIS REPORT — {len(analyzed)} email(s) processed")
    print(f"{'─'*60}")

    urgent_count = sum(1 for e in analyzed if e.get("urgent"))
    if urgent_count:
        print(f"  *** {urgent_count} URGENT email(s) require your attention ***\n")

    for i, email in enumerate(analyzed, start=1):
        urgency_label = "URGENT" if email.get("urgent") else "normal"
        print(f"\n  [{i}] {'*** URGENT ***' if email.get('urgent') else ''}")
        print(f"  Subject  : {email['subject']}")
        print(f"  From     : {email['sender']}")
        print(f"  Received : {email['received']}")
        print(f"  Priority : {urgency_label}")
        print(f"  Summary  : {email.get('summary', 'N/A')}")
        print(f"  Action   : {email.get('action', 'N/A')}")
        print(f"  {'·'*50}")

    print(f"\n{'='*60}")
    print(f"  Run complete. Next run in {SCHEDULE_INTERVAL_MINUTES} minute(s).")
    print(f"{'='*60}\n")


def main():
    """
    Bootstraps the legacy triage loop: runs once immediately, then schedules it on a timer.
    """
    required_vars = ["IMAP_SERVER", "IMAP_PORT", "EMAIL_ADDRESS", "EMAIL_PASSWORD", "OPENAI_API_KEY"]
    missing = [v for v in required_vars if not os.getenv(v)]

    if missing:
        print("[ERROR] The following .env variables are not configured:")
        for var in missing:
            print(f"  - {var}")
        print("\nPlease fill in your .env file before running the agent.")
        return

    if os.getenv("OPENAI_API_KEY", "").startswith("your_"):
        print("[ERROR] Please set your real OPENAI_API_KEY in .env.")
        return

    server = os.getenv("IMAP_SERVER")
    account = os.getenv("EMAIL_ADDRESS")
    print("[LEGACY] This console triage loop is retained for manual use.")
    print("[LEGACY] Preferred workflow: python -m OutlookAgent.fetch_tasks")
    print("Outlook AI Email Agent starting...")
    print(f"IMAP server  : {server}:{os.getenv('IMAP_PORT')}")
    print(f"Mailbox      : {account}")
    print(f"Interval     : every {SCHEDULE_INTERVAL_MINUTES} minute(s)")
    print(f"Max per run  : {MAX_EMAILS} emails")

    # Run immediately on startup
    run_agent()

    # Then schedule subsequent runs
    schedule.every(SCHEDULE_INTERVAL_MINUTES).minutes.do(run_agent)

    # Keep the scheduler alive
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
