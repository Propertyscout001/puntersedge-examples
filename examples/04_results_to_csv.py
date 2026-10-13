"""Settled race results -> results.csv (one row per placed runner).

Endpoint    GET /v1/racing/results           (2 credits per call, measured 2026-08-30)
Free tier   3,000 credits/month  ->  ~1,500 calls; one call covers a whole day of results.

Usage:
    python 04_results_to_csv.py               # last 24h
    python 04_results_to_csv.py --hours 48

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--out", default="results.csv")
    args = ap.parse_args()

    key = os.environ.get("PUNTERSEDGE_API_KEY")
    if not key:
        sys.exit("Set PUNTERSEDGE_API_KEY. Free keys (3,000 credits/month, no card):\n  " + SIGNUP)

    resp = requests.get(
        "https://api.puntersedge.online/v1/racing/results",
        params={"hours_back": args.hours, "limit": 200},  # 200 is the endpoint's max page size
        headers={"X-API-Key": key, "User-Agent": UA},
        timeout=30,
    )
    resp.raise_for_status()
    races = resp.json()

    fields = [
        "venue", "race_number", "category", "country", "start_time", "status",
        "position", "number", "name", "win_price", "place_price",
    ]
    rows = 0
    with open(args.out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for race in races:
            for placing in race.get("placings", []):
                writer.writerow({
                    "venue": race["venue"],
                    "race_number": race["race_number"],
                    "category": race["category"],
                    "country": race["country"],
                    "start_time": race["start_time"],
                    "status": race["status"],
                    "position": placing.get("position"),
                    "number": placing.get("number"),
                    "name": placing.get("name"),
                    "win_price": placing.get("win_price"),
                    "place_price": placing.get("place_price"),
                })
                rows += 1
    print(f"{len(races)} races, {rows} placings -> {args.out}")


if __name__ == "__main__":
    main()
