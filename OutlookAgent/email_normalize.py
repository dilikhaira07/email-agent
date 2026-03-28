"""
email_normalize.py
------------------
Helpers for decoding email bodies into readable previews and preserving useful links.
"""

import re
from html import unescape
from html.parser import HTMLParser

URL_RE = re.compile(r"https?://[^\s<>\"]+")
MAX_LINKS = 3


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts)


def decode_part(part) -> str:
    try:
        charset = part.get_content_charset() or "utf-8"
        payload = part.get_payload(decode=True)
        if payload is None:
            return ""
        return payload.decode(charset, errors="replace")
    except Exception:
        return ""


def html_to_text(html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(unescape(html))
    parser.close()
    return clean_whitespace(parser.get_text())


def clean_whitespace(text: str) -> str:
    return " ".join(text.split())


def extract_urls(text: str) -> list[str]:
    seen = set()
    urls = []
    for match in URL_RE.findall(text or ""):
        if match not in seen:
            seen.add(match)
            urls.append(match.rstrip(".,);"))
        if len(urls) >= MAX_LINKS:
            break
    return urls


def build_preview(msg, max_chars: int = 800) -> str:
    text_body = ""
    html_body = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition.lower():
                continue

            if content_type == "text/plain" and not text_body:
                text_body = decode_part(part)
            elif content_type == "text/html" and not html_body:
                html_body = decode_part(part)
    else:
        content_type = msg.get_content_type()
        payload = decode_part(msg)
        if content_type == "text/html":
            html_body = payload
        else:
            text_body = payload

    preview_source = clean_whitespace(text_body) if text_body else html_to_text(html_body)
    urls = extract_urls(text_body) or extract_urls(html_body)

    if urls:
        preview_source = f"{preview_source} Links: {' '.join(urls)}".strip()

    return preview_source[:max_chars]
