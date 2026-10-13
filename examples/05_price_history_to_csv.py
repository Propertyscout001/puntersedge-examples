"""Price history for one race -> open/close/high/low per runner per bookmaker, as CSV.

Endpoint    GET /v1/racing/price-history     (5 credits per call, measured 2026-08-30)
            With no --race-id it first asks /v1/racing/results for the latest settled
            race (2 credits), so a bare run costs 7 credits total.

This is the per-race view. The bulk, back-to-day-one version of the same data is
GET /v1/racing/closing-lines — a paid endpoint (Standard plan and up).

Usage:
    python 05_price_history_to_csv.py                       # latest settled race
    python 05_price_history_to_csv.py --race-id <uuid>

Needs a key (free tier is fine):
https://puntersedge.online/api?utm_source=github_examples&utm_medium=cookbook_nokey#signup
"""
import argparse
import csv
import os
import sys

import requests

SIGNUP = "https://puntersedge.online/api?utm_source=github_examples&utm_medium=cookbook_nokey#signup"
UA = "puntersedge-examples/1.0 (+https://github.com/Propertyscout001/puntersedge-examples)"
BASE = "https://api.puntersedge.online/v1"


def get(key, path, **params):
    resp = requests.get(
        BASE + path, params=params, headers={"X-API-Key": key, "User-Agent": UA}, timeout=30
    )
    resp.raise_for_status()
    return resp.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--race-id", default=None)
    ap.add_argument("--out", default="price_history.csv")
    args = ap.parse_args()

    key = os.environ.get("PUNTERSEDGE_API_KEY")
    if not key:
        sys.exit("Set PUNTERSEDGE_API_KEY. Free keys (3,000 credits/month, no card):\n  " + SIGNUP)

    race_id = args.race_id
    if not race_id:
        latest = get(key, "/racing/results", hours_back=6, limit=1)
        if not latest:
            sys.exit("No settled races in the last 6 hours — pass --race-id instead.")
        race_id = latest[0]["race_id"]
        print(f"Latest settled race: {latest[0]['venue']} R{latest[0]['race_number']} ({race_id})")

    hist = get(key, "/racing/price-history", race_id=race_id)

    fields = [
        "runner", "number", "bookmaker", "open_price", "close_price",
        "high", "low", "move_pct", "points_count",
    ]
    rows = 0
    with open(args.out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for runner in hist.get("runners", []):
            for book in runner.get("bookmakers", []):
                writer.writerow({
                    "runner": runner["name"],
                    "number": runner["number"],
                    "bookmaker": book["key"],
                    "open_price": book.get("open_price"),
                    "close_price": book.get("close_price"),
                    "high": book.get("high"),
                    "low": book.get("low"),
                    "move_pct": book.get("move_pct"),
                    "points_count": book.get("points_count"),
                })
                rows += 1
    print(f"{hist['venue']} R{hist['race_number']}: {rows} runner-book rows -> {args.out}")


if __name__ == "__main__":
    main()
