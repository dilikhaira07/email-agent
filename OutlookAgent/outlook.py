"""
outlook.py
----------
Connects to an IMAP mail server using Python's built-in imaplib to fetch
unread emails. No Azure or OAuth setup required — just IMAP credentials.
"""

import os
import imaplib
import email
from email.header import decode_header
from dotenv import load_dotenv

from .email_normalize import build_preview

load_dotenv()

IMAP_SERVER = os.getenv("IMAP_SERVER")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
# Use IMAP_USERNAME if set, otherwise fall back to full EMAIL_ADDRESS
IMAP_USERNAME = os.getenv("IMAP_USERNAME") or EMAIL_ADDRESS


def _decode_str(value) -> str:
    """
    Safely decodes an email header value that may be encoded (e.g. UTF-8, base64).

    Args:
        value: Raw header value (str or bytes).

    Returns:
        str: Human-readable decoded string.
    """
    if value is None:
        return ""
    parts, _ = decode_header(value)[0], None
    decoded_parts = []
    for part, charset in decode_header(value):
        if isinstance(part, bytes):
            try:
                decoded_parts.append(part.decode(charset or "utf-8", errors="replace"))
            except (LookupError, UnicodeDecodeError):
                decoded_parts.append(part.decode("utf-8", errors="replace"))
        else:
            decoded_parts.append(str(part))
    return "".join(decoded_parts)


def _get_body_preview(msg, max_chars: int = 500) -> str:
    """
    Extracts a readable preview from an email message object and preserves a few useful links.
    """
    return build_preview(msg, max_chars=max_chars)


def fetch_emails(max_emails: int = 10) -> list[dict]:
    """
    Connects to the IMAP server over SSL and fetches unread emails from the INBOX.

    Args:
        max_emails (int): Maximum number of unread emails to return. Default is 10.

    Returns:
        list[dict]: A list of email dicts with keys:
                    id, subject, sender, received, preview, importance.

    Raises:
        RuntimeError: If connection, login, or fetching fails.
    """
    # Validate credentials are loaded
    if not all([IMAP_SERVER, EMAIL_ADDRESS, EMAIL_PASSWORD]):
        raise RuntimeError(
            "IMAP credentials are missing. Check IMAP_SERVER, EMAIL_ADDRESS, "
            "and EMAIL_PASSWORD in your .env file."
        )

    try:
        # Connect using SSL (port 993)
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    except OSError as e:
        raise RuntimeError(
            f"Could not connect to IMAP server '{IMAP_SERVER}:{IMAP_PORT}': {e}\n"
            "Check your IMAP_SERVER and IMAP_PORT in .env."
        )

    try:
        mail.login(IMAP_USERNAME, EMAIL_PASSWORD)
    except imaplib.IMAP4.error as e:
        raise RuntimeError(
            f"IMAP login failed: {e}\n"
            "Check your EMAIL_ADDRESS, IMAP_USERNAME, and EMAIL_PASSWORD in .env."
        )

    try:
        # Select the INBOX (read-only=False so we can mark as read later)
        status, _ = mail.select("INBOX")
        if status != "OK":
            raise RuntimeError("Could not select INBOX.")

        # Search for all UNSEEN (unread) messages
        status, data = mail.search(None, "UNSEEN")
        if status != "OK":
            raise RuntimeError("IMAP SEARCH command failed.")

        # data[0] is a space-separated list of message IDs as bytes
        message_ids = data[0].split()

        if not message_ids:
            return []

        # Take the most recent N (IDs are in ascending order, so we take the last N)
        recent_ids = message_ids[-max_emails:]
        # Reverse so newest is first
        recent_ids = list(reversed(recent_ids))

        emails = []
        for uid in recent_ids:
            # Fetch the full RFC822 message
            status, msg_data = mail.fetch(uid, "(RFC822)")
            if status != "OK" or not msg_data or msg_data[0] is None:
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            subject = _decode_str(msg.get("Subject", "(No Subject)"))
            sender = _decode_str(msg.get("From", "Unknown"))
            received = msg.get("Date", "")
            importance = msg.get("Importance", msg.get("X-Priority", "normal"))
            preview = _get_body_preview(msg)

            emails.append({
                "id": uid.decode(),
                "subject": subject,
                "sender": sender,
                "received": received,
                "preview": preview,
                "importance": importance,
            })

        return emails

    finally:
        # Always close the connection cleanly
        try:
            mail.close()
            mail.logout()
        except Exception:
            pass


def mark_email_as_read(message_uid: str) -> None:
    """
    Marks a specific email as read (Seen) on the IMAP server.

    Args:
        message_uid (str): The IMAP message UID (as returned in the 'id' field).
    """
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(IMAP_USERNAME, EMAIL_PASSWORD)
        mail.select("INBOX")
        mail.store(message_uid, "+FLAGS", "\\Seen")
        mail.close()
        mail.logout()
    except Exception as e:
        print(f"  Warning: Could not mark email as read: {e}")
