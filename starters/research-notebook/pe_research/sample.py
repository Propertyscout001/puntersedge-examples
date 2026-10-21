"""Fetch an available historical sample: coverage first, then one day of closing prices and results.

Two paths, chosen by what the key's plan allows:

* closing_lines(...)   GET /v1/racing/closing-lines?date=   (Standard and above). One row per
                       runner per bookmaker, opening and closing win price, `is_closing_line` when the
                       last observation was within 300 s of the jump. Paged with limit/offset.
* free_sample(...)     every plan: GET /v1/racing/results for recent races, then
                       GET /v1/racing/price-history?race_id= for a few of them (races that started in
                       the last 24 hours are readable on every plan). Rows are shaped like closing-line
                       rows so the same join and analysis run on either.

results(...)           GET /v1/racing/results?date=, paged with offset by X-Limit-Applied.
coverage(...)          the archive's and the results store's own coverage dates, read from the API
                       (/v1/racing/closing-lines/coverage, /v1/racing/results/coverage) rather than
                       typed into the notebook.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(os.path.dirname(HERE), "fixtures")
AET = dt.timezone(dt.timedelta(hours=10))


def default_date(today: Optional[dt.date] = None) -> str:
    """Yesterday in Australian Eastern (standard) time: the latest day that has fully settled."""
    today = today or dt.datetime.now(AET).date()
    return (today - dt.timedelta(days=1)).isoformat()


def load_fixture(name: str) -> Any:
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        doc = json.load(fh)
    return doc["data"] if isinstance(doc, dict) and "data" in doc and "_fixture" in doc else doc


def coverage(client) -> dict:
    cl, _ = client.get("/v1/racing/closing-lines/coverage")
    rs, _ = client.get("/v1/racing/results/coverage")
    keep = lambda d, ks: {k: d.get(k) for k in ks if k in d}            # noqa: E731
    return {"closing_lines": keep(cl, ("archive_from", "archive_to", "races", "rows", "results_from",
                                       "window_days", "window_from", "races_without_result",
                                       "results_without_race", "scratched_rows")),
            "results": keep(rs, ("coverage_from", "from_day", "to_day", "races", "complete_pct",
                                 "pending", "overdue", "unavailable", "unsupported"))}


def closing_lines(client, date: str, *, country: str = "AU", category: Optional[str] = None,
                  page: int = 5000, max_pages: int = 10) -> list:
    rows, offset = [], 0
    for _ in range(max_pages):
        body, _h = client.get("/v1/racing/closing-lines", date=date, country=country, category=category,
                              limit=page, offset=offset, include_scratched="true")
        got = body.get("rows") or []
        rows += got
        total = body.get("total_rows")
        offset += len(got)
        if len(got) < page or (isinstance(total, int) and offset >= total):
            break
    return rows


def results(client, date: str, *, country: str = "AU", category: Optional[str] = None,
            max_pages: int = 10) -> list:
    rows, offset = [], 0
    for _ in range(max_pages):
        page, headers = client.get("/v1/racing/results", date=date, country=country, category=category,
                                   limit=200, offset=offset)
        rows += page
        size = int({k.lower(): v for k, v in headers.items()}.get("x-limit-applied", 200))
        if len(page) < size:
            break
        offset += size
    return rows


def price_history_rows(ph: dict) -> list:
    """price-history for one race -> closing-line-shaped rows (one per runner per bookmaker)."""
    out = []
    for runner in ph.get("runners") or []:
        for b in runner.get("bookmakers") or []:
            close_secs = b.get("close_secs_to_jump")
            out.append({
                "race_id": ph.get("race_id"), "start_time": ph.get("start_time"), "venue": ph.get("venue"),
                "race_number": ph.get("race_number"), "category": ph.get("category"),
                "country": ph.get("country"), "runner_number": runner.get("number"),
                "runner_name": runner.get("name"), "bookmaker_key": b.get("key"),
                "open_win_price": b.get("open_price"), "close_win_price": b.get("close_price"),
                "open_is_baseline": b.get("open_is_baseline"), "close_secs_to_jump": close_secs,
                "is_closing_line": close_secs is not None and close_secs <= 300,
                "scratched": False, "finish_position": None, "result_status": None,
                "source": "price-history"})
    return out


def free_sample(client, *, hours_back: int = 12, country: str = "AU", category: Optional[str] = None,
                max_races: int = 5) -> tuple[list, list]:
    """Every plan: recent final results, then price history for up to max_races of them."""
    res, _ = client.get("/v1/racing/results", hours_back=hours_back, country=country,
                        category=category, status="final", limit=50)
    picked = [r for r in res if r.get("race_id")][:max_races]
    prices = []
    for r in picked:
        ph, _ = client.get("/v1/racing/price-history", race_id=r["race_id"], include_points="false")
        prices += price_history_rows(ph)
    return prices, res
