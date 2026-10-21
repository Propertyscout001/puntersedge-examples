#!/usr/bin/env python3
"""Follow racing results until they are final (and the full field is in), reporting each change once.

    python tracker.py --date 2026-10-24 --venue Flemington            # every race at a meeting
    python tracker.py --date 2026-10-24 --country AU --category greyhound
    python tracker.py --date 2026-10-24 --race-id <id> --race-id <id>  # specific races
    python tracker.py --replay fixtures/                                # offline demo, synthetic data

Each change is printed as one JSON line (pipe it into whatever you use). State lives in PE_DB, so a
restart resumes without repeating anything. See README.md for costs, limits and plan notes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from pe_results import tracker as T
from pe_results.client import GUIDANCE, ApiError, Client
from pe_results.state import Store


def emit(ev: dict) -> None:
    print(json.dumps(ev, default=str), flush=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", help="race date, Australian Eastern (YYYY-MM-DD)")
    ap.add_argument("--venue", help="exact venue name, e.g. Flemington")
    ap.add_argument("--country", default="AU")
    ap.add_argument("--category", choices=("horse", "greyhound", "harness"))
    ap.add_argument("--race-id", action="append", default=[], help="track these races (repeatable)")
    ap.add_argument("--interval", type=int, default=int(os.environ.get("PE_POLL_SECONDS", "120")),
                    help="seconds between polls, minimum 60 (default 120)")
    ap.add_argument("--max-requests", type=int, default=int(os.environ.get("PE_MAX_REQUESTS", "300")))
    ap.add_argument("--max-hours", type=float, default=8.0)
    ap.add_argument("--once", action="store_true", help="poll once and exit")
    ap.add_argument("--replay", metavar="DIR", help="replay fixture polls from DIR (no key, no network)")
    a = ap.parse_args(argv)

    store = Store(os.environ.get("PE_DB", "results-tracker.sqlite3") if not a.replay else ":memory:")
    if a.replay:
        from pe_results.replay import ReplayClient
        client = ReplayClient(a.replay)
        a.date = a.date or client.date
        emit({"kind": "note", "text": "REPLAY of synthetic fixtures: invented races, not real results."})
    else:
        if not a.date:
            ap.error("--date is required")
        try:
            client = Client(max_requests=a.max_requests)
        except ApiError as e:
            print(e.message, file=sys.stderr)
            return 2
    try:
        if a.race_id:
            for rid in a.race_id:
                store.track({"race_id": rid})
        else:
            races = T.select_races(client, date=a.date, country=a.country, category=a.category, venue=a.venue)
            if not races:
                emit({"kind": "nothing_to_track", "date": a.date, "venue": a.venue,
                      "hint": "No races found for that date and filter. Check the venue's exact name in "
                              "/v1/racing/events, or the date (Australian Eastern)."})
                return 0
            for r in races:
                store.track(r)
            emit({"kind": "tracking", "races": len(races), "date": a.date, "venue": a.venue})
        if a.once:
            out = T.poll_once(client, store, date=a.date, country=a.country, category=a.category, venue=a.venue)
            for ev in out["events"]:
                emit(ev)
            return 0
        sleep = (lambda s: None) if a.replay else None
        kwargs = {"sleep": sleep} if sleep else {}
        res = T.run(client, store, date=a.date, country=a.country, category=a.category, venue=a.venue,
                    interval=a.interval, max_hours=a.max_hours, emit=emit, **kwargs)
    except ApiError as e:
        emit({"kind": "stopped", "status": e.status, "reason": e.message, "what_to_do": GUIDANCE.get(e.code, "")})
        return 1
    if hasattr(client, "credits"):
        emit({"kind": "usage", "requests": getattr(client, "requests", None), "credits": client.credits})
    return 0 if res.get("stopped") in ("done", "time") else 1


if __name__ == "__main__":
    sys.exit(main())
