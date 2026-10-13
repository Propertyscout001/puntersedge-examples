"""Upcoming Australian races, soonest first, with the current favourite.

Endpoint    GET /v1/racing/next-to-go        (2 credits per call, measured 2026-08-30)
Free tier   3,000 credits/month  ->  ~1,500 calls, so hourly polling fits with room to spare.

Works with NO KEY against the demo sandbox (3 races, truncated bookmaker lists).
For the full feed, grab a free key (3,000 credits/month, no card) and export it:

    export PUNTERSEDGE_API_KEY=...

https://puntersedge.online/api?utm_source=github_examples&utm_medium=cookbook_nokey#signup
"""
import json
import os
import urllib.request
from datetime import datetime, timezone

SIGNUP = "https://puntersedge.online/api?utm_source=github_examples&utm_medium=cookbook_nokey#signup"


def fetch_races():
    key = os.environ.get("PUNTERSEDGE_API_KEY")
    if key:
        from puntersedge import PuntersEdge  # pip install puntersedge
        return PuntersEdge().racing_next_to_go(), False
    req = urllib.request.Request(
        "https://api.puntersedge.online/v1/demo/racing/next-to-go",
        headers={"User-Agent": "puntersedge-examples/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.load(resp)
    return payload["races"], True


def mins_to_jump(start_time_iso):
    start = datetime.fromisoformat(start_time_iso.replace("Z", "+00:00"))
    return (start - datetime.now(timezone.utc)).total_seconds() / 60


def favourite(race):
    """Runner with the lowest best win price. Purely descriptive — shortest price, nothing more."""
    best = None
    for runner in race.get("runners", []):
        prices = [b["win_price"] for b in runner.get("bookmakers", []) if b.get("win_price")]
        if not prices:
            continue
        top = max(prices)  # best price for a backer is the HIGHEST win price on offer
        if best is None or top < best[1]:
            best = (runner["name"], top)
    return best


def main():
    races, demo = fetch_races()
    if demo:
        print("DEMO MODE — sandbox sample (3 races, truncated books). Full feed is a free key away:")
        print("  " + SIGNUP + "\n")
    races = sorted(races, key=lambda r: r["start_time"])
    print(f"{'jump':>7}  {'venue':<18} {'race':>4}  {'cat':<9} {'runners':>7}  favourite")
    for race in races:
        fav = favourite(race)
        fav_str = f"{fav[0]} @ {fav[1]:.2f}" if fav else "-"
        print(
            f"{mins_to_jump(race['start_time']):>6.0f}m"
            f"  {race['venue']:<18} R{race['race_number']:<3}"
            f"  {race['category']:<9} {len(race.get('runners', [])):>7}  {fav_str}"
        )


if __name__ == "__main__":
    main()
