"""Select races, then poll their results until nothing more will arrive (or the budget is spent).

Selection: GET /v1/racing/events?date=&country=&category= (1 credit), filtered to a venue here
(events takes no venue parameter), or the race_ids you pass. Polling: GET /v1/racing/results with
date (+ venue, country, category) every `interval` seconds, paged by X-Limit-Applied, 2 credits a
page. A result row is matched to a tracked race on race_id only; a row whose race_id is null is
reported, never matched by venue and number.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from .client import ApiError, BudgetSpent


def select_races(client, *, date: str, country: str = "AU", category: Optional[str] = None,
                 venue: Optional[str] = None) -> list:
    events, _ = client.get("/v1/racing/events", date=date, country=country, category=category)
    v = (venue or "").strip().lower()
    return [e for e in events if e.get("race_id") and (not v or str(e.get("venue", "")).lower() == v)]


def fetch_results(client, *, date: str, country: Optional[str], category: Optional[str],
                  venue: Optional[str], max_pages: int = 5) -> list:
    rows, offset = [], 0
    for _ in range(max_pages):
        page, headers = client.get("/v1/racing/results", date=date, country=country, category=category,
                                   venue=venue, limit=200, offset=offset)
        rows += page
        size = int(headers.get("x-limit-applied", 200))
        if len(page) < size:
            break
        offset += size
    return rows


def poll_once(client, store, *, date, country, category, venue) -> dict:
    """One poll: apply every result row for a tracked race; return events and loose ends."""
    tracked = {r["race_id"]: r for r in store.tracked()}
    events, unmatched = [], []
    for row in fetch_results(client, date=date, country=country, category=category, venue=venue):
        rid = row.get("race_id")
        if rid is None:
            unmatched.append({"venue": row.get("venue"), "race_number": row.get("race_number"),
                              "start_time": row.get("start_time"), "status": row.get("status")})
            continue
        if rid in tracked:
            events += store.apply(row)
    return {"events": events, "unmatched": unmatched, "remaining": store.remaining()}


def run(client, store, *, date, country="AU", category=None, venue=None, interval: int = 120,
        max_hours: float = 8.0, emit: Callable = print, sleep=time.sleep, clock=time.monotonic) -> dict:
    """Poll until every tracked race is done, the budget is spent, or max_hours pass."""
    interval = max(60, int(interval))
    deadline = clock() + max_hours * 3600
    polls = 0
    while True:
        try:
            out = poll_once(client, store, date=date, country=country, category=category, venue=venue)
        except BudgetSpent as e:
            emit({"kind": "stopped", "reason": str(e)})
            return {"stopped": "budget", "polls": polls}
        except ApiError as e:
            if e.fatal:
                emit({"kind": "stopped", "reason": e.message, "status": e.status})
                return {"stopped": "fatal", "polls": polls, "status": e.status}
            emit({"kind": "poll_failed", "reason": e.message})        # retried already; try next cycle
            out = {"events": [], "unmatched": [], "remaining": store.remaining()}
        polls += 1
        for ev in out["events"]:
            emit(ev)
        for u in out["unmatched"]:
            emit({"kind": "result_without_race_id", **u})
        if not out["remaining"]:
            emit({"kind": "done", "polls": polls})
            return {"stopped": "done", "polls": polls}
        if clock() + interval > deadline:
            emit({"kind": "stopped", "reason": f"{max_hours} h limit", "remaining": [r["race_id"] for r in out["remaining"]]})
            return {"stopped": "time", "polls": polls}
        sleep(interval)
