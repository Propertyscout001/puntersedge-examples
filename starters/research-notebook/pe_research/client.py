"""A small, careful client for the research notebook.

* The key comes from PUNTERSEDGE_API_KEY (or the caller); it is sent in X-API-Key and never put in a
  URL, a log line or an exception message.
* Retries only what retrying can fix: 429 (honouring Retry-After), 5xx and network errors, with
  exponential backoff and jitter. 401/402/403/422 raise immediately with the API's own explanation.
* A hard cap on calls per run (max_calls), and a running total of credits from X-Credits-Cost, so a
  notebook re-run cannot quietly spend a month's allowance.
"""
from __future__ import annotations

import os
import random
import time
from typing import Any, Optional

import requests

API_BASE = "https://api.puntersedge.online"
USER_AGENT = "puntersedge-starter-research-notebook/1.0"
_CODES = {401: "auth", 402: "credits", 403: "plan", 404: "not_found", 422: "invalid", 429: "rate_limited"}


class ApiError(Exception):
    def __init__(self, status: int, message: str, *, code: str, retry_after: Optional[float] = None,
                 body: Any = None):
        super().__init__(f"HTTP {status}: {message}" if status else message)
        self.status, self.message, self.code, self.retry_after, self.body = status, message, code, retry_after, body

    @property
    def fatal(self) -> bool:
        return self.code in ("auth", "credits", "plan", "invalid")


class BudgetExceeded(RuntimeError):
    pass


def _detail(body: Any) -> Optional[str]:
    if isinstance(body, dict):
        d = body.get("detail") or body.get("title")
        return d if isinstance(d, str) else None
    return None


class Client:
    def __init__(self, api_key: Optional[str] = None, *, base: str = API_BASE, session=None,
                 max_calls: int = 40, timeout: float = 30.0, max_retries: int = 3, sleep=time.sleep):
        key = (api_key if api_key is not None else os.environ.get("PUNTERSEDGE_API_KEY", "")).strip()
        if not key or key == "replace-with-your-key":
            raise ApiError(0, "Set PUNTERSEDGE_API_KEY (or run with PE_USE_FIXTURES=1).", code="auth")
        self._key = key
        self.base = base.rstrip("/")
        self.session = session or requests.Session()
        self.max_calls, self.timeout, self.max_retries, self.sleep = max_calls, timeout, max_retries, sleep
        self.calls = 0
        self.credits = 0

    def __repr__(self) -> str:                       # never show the key
        return f"Client(base={self.base!r}, calls={self.calls}, credits={self.credits})"

    def get(self, path: str, **params) -> tuple[Any, dict]:
        """(json body, response headers). Raises ApiError or BudgetExceeded."""
        params = {k: v for k, v in params.items() if v is not None and v != ""}
        attempt = 0
        while True:
            if self.calls >= self.max_calls:
                raise BudgetExceeded(f"Stopped after {self.calls} API calls (PE_MAX_CALLS). "
                                     "Raise it if you meant to fetch more.")
            self.calls += 1
            try:
                r = self.session.get(self.base + path, params=params, timeout=self.timeout,
                                     headers={"X-API-Key": self._key, "User-Agent": USER_AGENT,
                                              "Accept": "application/json"})
            except requests.RequestException:
                err = ApiError(0, "Could not reach the API.", code="network")
            else:
                cost = r.headers.get("X-Credits-Cost")
                if cost and cost.isdigit():
                    self.credits += int(cost)
                if r.status_code < 400:
                    return r.json(), dict(r.headers)
                try:
                    body = r.json()
                except ValueError:
                    body = None
                ra = r.headers.get("Retry-After")
                err = ApiError(r.status_code, _detail(body) or f"The API answered {r.status_code}.",
                               code=_CODES.get(r.status_code, "server" if r.status_code >= 500 else "invalid"),
                               retry_after=float(ra) if ra and ra.replace(".", "", 1).isdigit() else None,
                               body=body)
            retryable = err.code in ("rate_limited", "server", "network")
            if not retryable or attempt >= self.max_retries:
                raise err
            wait = min(60.0, (2 ** attempt) + random.uniform(0, 0.5))
            if err.retry_after:
                wait = max(wait, min(err.retry_after, 120.0))
            attempt += 1
            self.sleep(wait)
