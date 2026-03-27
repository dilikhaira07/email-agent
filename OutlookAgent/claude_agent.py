"""
claude_agent.py
---------------
Uses the Anthropic SDK to analyze a batch of emails.
For each email it:
  1. Summarizes the content in plain language
  2. Flags whether it is urgent
  3. Suggests a concrete next action
"""

import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# The Claude model to use for analysis
MODEL = "claude-sonnet-4-20250514"

# Initialize the Anthropic client once at module level
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def analyze_email(email: dict) -> dict:
    """
    Sends a single email to Claude for analysis.

    Args:
        email (dict): An email dict as returned by outlook.fetch_emails().
                      Expected keys: subject, sender, received, preview, importance.

    Returns:
        dict: The original email dict enriched with:
              - summary  (str): A 1-2 sentence plain-language summary.
              - urgent   (bool): True if the email needs prompt attention.
              - action   (str): A suggested next action for the user.
              - raw_analysis (str): Full Claude response text (for debugging).

    Raises:
        RuntimeError: If the Claude API call fails.
    """
    # Build a structured prompt with the email details
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
        message = client.messages.create(
            model=MODEL,
            max_tokens=300,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        raw = message.content[0].text.strip()

        # Parse the structured response from Claude
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

    except anthropic.AuthenticationError:
        raise RuntimeError(
            "Anthropic authentication failed. Check your ANTHROPIC_API_KEY in .env."
        )
    except anthropic.RateLimitError:
        raise RuntimeError(
            "Anthropic rate limit reached. The agent will retry on the next scheduled run."
        )
    except anthropic.APIError as e:
        raise RuntimeError(f"Claude API error: {e}")


def analyze_emails(emails: list[dict]) -> list[dict]:
    """
    Analyzes a list of emails, skipping any that fail without crashing the whole run.

    Args:
        emails (list[dict]): List of email dicts from outlook.fetch_emails().

    Returns:
        list[dict]: Analyzed emails, sorted so urgent ones appear first.
    """
    if not emails:
        return []

    results = []
    for i, email in enumerate(emails, start=1):
        print(f"  Analyzing email {i}/{len(emails)}: {email['subject'][:60]}...")
        try:
            analyzed = analyze_email(email)
            results.append(analyzed)
        except RuntimeError as e:
            # Log the error but continue processing remaining emails
            print(f"  [!] Skipped email '{email['subject']}' due to error: {e}")

    # Sort: urgent emails bubble to the top
    results.sort(key=lambda e: (not e.get("urgent", False)))

    return results


def _extract_field(text: str, field: str) -> str:
    """
    Extracts the value of a labeled field from Claude's structured response.

    Example input:
        "SUMMARY: Meeting request for next Tuesday\nURGENT: YES\nACTION: Confirm attendance"

    Args:
        text (str): The full response text from Claude.
        field (str): The field label to extract (e.g. "SUMMARY").

    Returns:
        str: The extracted value, or an empty string if the field is not found.
    """
    for line in text.splitlines():
        if line.startswith(f"{field}:"):
            return line[len(f"{field}:"):].strip()
    return ""
