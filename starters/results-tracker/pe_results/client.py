"""Results tracker client: GETs only, safe to retry, bounded.

* Key from PUNTERSEDGE_API_KEY, sent in X-API-Key; never in a URL, log line or exception.
* Retries 429 (honouring Retry-After), 5xx and network errors with exponential backoff and jitter;
  never retries 401/402/403/422, which only a change of key, plan, month or parameters can fix.
* A request budget per run (max_requests): the tracker stops cleanly when it is spent.
"""
from __future__ import annotations

import os
import random
import time
from typing import Any, Optional

import requests

API_BASE = "https://api.puntersedge.online"
USER_AGENT = "puntersedge-starter-results-tracker/1.0"
_CODES = {401: "auth", 402: "credits", 403: "plan", 404: "not_found", 422: "invalid", 429: "rate_limited"}
GUIDANCE = {
    "auth": "Check PUNTERSEDGE_API_KEY: the API says whether it is missing, mistyped or replaced.",
    "credits": "This month's credits are used up; requests resume at the reset (00:00 UTC on the 1st).",
    "plan": "Your plan does not include this request; the message names the plans that do.",
    "invalid": "A parameter was refused; the message names it.",
}


class ApiError(Exception):
    def __init__(self, status: int, message: str, code: str, retry_after: Optional[float] = None):
        super().__init__(f"HTTP {status}: {message}" if status else message)
        self.status, self.message, self.code, self.retry_after = status, message, code, retry_after

    @property
    def fatal(self) -> bool:
        return self.code in GUIDANCE


class BudgetSpent(RuntimeError):
    pass


class Client:
    def __init__(self, api_key: Optional[str] = None, *, base: str = API_BASE, session=None,
                 max_requests: int = 300, timeout: float = 30.0, max_retries: int = 4, sleep=time.sleep):
        key = (api_key if api_key is not None else os.environ.get("PUNTERSEDGE_API_KEY", "")).strip()
        if not key or key == "replace-with-your-key":
            raise ApiError(0, "Set PUNTERSEDGE_API_KEY.", "auth")
        self._key, self.base = key, base.rstrip("/")
        self.session = session or requests.Session()
        self.max_requests, self.timeout, self.max_retries, self.sleep = max_requests, timeout, max_retries, sleep
        self.requests = 0
        self.credits = 0

    def __repr__(self) -> str:
        return f"Client(requests={self.requests}, credits={self.credits})"

    def get(self, path: str, **params) -> tuple[Any, dict]:
        params = {k: v for k, v in params.items() if v not in (None, "")}
        attempt = 0
        while True:
            if self.requests >= self.max_requests:
                raise BudgetSpent(f"request budget of {self.max_requests} spent")
            self.requests += 1
            try:
                r = self.session.get(self.base + path, params=params, timeout=self.timeout,
                                     headers={"X-API-Key": self._key, "User-Agent": USER_AGENT})
            except requests.RequestException:
                err = ApiError(0, "Could not reach the API.", "network")
            else:
                c = r.headers.get("X-Credits-Cost")
                if c and c.isdigit():
                    self.credits += int(c)
                if r.status_code < 400:
                    return r.json(), {k.lower(): v for k, v in r.headers.items()}
                try:
                    body = r.json()
                    msg = body.get("detail") if isinstance(body, dict) else None
                except ValueError:
                    msg = None
                ra = r.headers.get("Retry-After")
                err = ApiError(r.status_code, msg if isinstance(msg, str) else f"The API answered {r.status_code}.",
                               _CODES.get(r.status_code, "server" if r.status_code >= 500 else "invalid"),
                               float(ra) if ra and ra.replace(".", "", 1).isdigit() else None)
            if err.code not in ("rate_limited", "server", "network") or attempt >= self.max_retries:
                raise err
            wait = min(120.0, 2.0 * (2 ** attempt) + random.uniform(0, 1.0))
            if err.retry_after:
                wait = max(wait, min(err.retry_after, 300.0))
            attempt += 1
            self.sleep(wait)
