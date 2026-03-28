"""
claude_agent.py
---------------
Uses the OpenAI SDK to analyze a batch of emails.
For each email it:
  1. Summarizes the content in plain language
  2. Flags whether it is urgent
  3. Suggests a concrete next action
"""

import os

from dotenv import load_dotenv

try:
    from openai import AuthenticationError, OpenAI, OpenAIError, RateLimitError
except ImportError:
    AuthenticationError = RateLimitError = OpenAIError = Exception
    OpenAI = None

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
client = OpenAI(api_key=OPENAI_API_KEY) if OpenAI and OPENAI_API_KEY else None


def analyze_email(email: dict) -> dict:
    prompt = f"""You are an executive email assistant. Analyze the following email and respond in exactly this format:

SUMMARY: <1-2 sentence plain-language summary of what the email is about>
URGENT: <YES or NO — urgent means it requires a response or action within 24 hours>
ACTION: <one specific, concrete action the recipient should take, e.g. "Reply confirming the meeting time" or "No action needed">

Email details:
- Subject: {email['subject']}
- Sender: {email['sender']}
- Received: {email['received']}
- Importance flag: {email['importance']}
- Body preview: {email['preview']}
"""

    try:
        if client is None:
            raise RuntimeError("OpenAI client is unavailable. Install the openai package and set OPENAI_API_KEY.")
        response = client.responses.create(
            model=MODEL,
            input=prompt,
        )
        raw = response.output_text.strip()
        summary = _extract_field(raw, "SUMMARY")
        urgent_text = _extract_field(raw, "URGENT")
        action = _extract_field(raw, "ACTION")
        return {
            **email,
            "summary": summary,
            "urgent": urgent_text.upper() == "YES",
            "action": action,
            "raw_analysis": raw,
        }
    except AuthenticationError:
        raise RuntimeError("OpenAI authentication failed. Check your OPENAI_API_KEY in .env.")
    except RateLimitError:
        raise RuntimeError("OpenAI rate limit reached. The agent will retry on the next scheduled run.")
    except OpenAIError as e:
        raise RuntimeError(f"OpenAI API error: {e}")


def analyze_emails(emails: list[dict]) -> list[dict]:
    if not emails:
        return []

    results = []
    for i, email in enumerate(emails, start=1):
        print(f"  Analyzing email {i}/{len(emails)}: {email['subject'][:60]}...")
        try:
            analyzed = analyze_email(email)
            results.append(analyzed)
        except RuntimeError as e:
            print(f"  [!] Skipped email '{email['subject']}' due to error: {e}")

    results.sort(key=lambda e: (not e.get("urgent", False)))
    return results


def _extract_field(text: str, field: str) -> str:
    for line in text.splitlines():
        if line.startswith(f"{field}:"):
            return line[len(f"{field}:"):].strip()
    return ""
