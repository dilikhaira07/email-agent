"""
http_client.py
--------------
Shared HTTP client with explicit timeouts and bounded retries for external APIs.
"""

import os
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

CONNECT_TIMEOUT = float(os.getenv("HTTP_CONNECT_TIMEOUT", "3"))
READ_TIMEOUT = float(os.getenv("HTTP_READ_TIMEOUT", "10"))
RETRY_TOTAL = int(os.getenv("HTTP_RETRY_TOTAL", "3"))
STATUS_FORCE_LIST = (429, 500, 502, 503, 504)


def build_session() -> requests.Session:
    retry = Retry(
        total=RETRY_TOTAL,
        connect=RETRY_TOTAL,
        read=RETRY_TOTAL,
        backoff_factor=0.5,
        status_forcelist=STATUS_FORCE_LIST,
        allowed_methods=frozenset({"GET", "POST", "PATCH"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


session = build_session()


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> requests.Response:
    return session.post(url, json=payload, headers=headers, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))


def patch_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> requests.Response:
    return session.patch(url, json=payload, headers=headers, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
