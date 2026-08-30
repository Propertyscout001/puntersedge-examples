"""Best available head-to-head price per team for one sport (NRL by default).

Endpoint    GET /v1/best-odds/{sport_key}    (3 credits per call, measured 2026-08-30)
Free tier   1,500 credits/month  ->  ~500 calls.

Works with NO KEY against the demo sandbox (truncated). The `arb_exists` flag is
computed and served by the API — display it, don't recompute it locally. For a
scanner with proper freshness/coverage gates, use the `puntersedge.arb` toolkit
that ships inside the SDK (`pip install puntersedge`).

Usage:
    python 06_sports_best_odds.py           # nrl
    python 06_sports_best_odds.py afl

https://puntersedge.online/api?utm_source=github_examples&utm_medium=cookbook_nokey#signup
"""
import json
import os
import sys
import urllib.parse
import urllib.request

SIGNUP = "https://puntersedge.online/api?utm_source=github_examples&utm_medium=cookbook_nokey#signup"


def fetch(sport):
    key = os.environ.get("PUNTERSEDGE_API_KEY")
    if key:
        from puntersedge import PuntersEdge
        return PuntersEdge().best_odds(sport), False
    url = "https://api.puntersedge.online/v1/demo/best-odds?sport=" + urllib.parse.quote(sport)
    req = urllib.request.Request(url, headers={"User-Agent": "puntersedge-examples/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)["events"], True


def main():
    sport = sys.argv[1] if len(sys.argv) > 1 else "nrl"
    events, demo = fetch(sport)
    if demo:
        print("DEMO MODE — sandbox sample. Full feed with a free key:")
        print("  " + SIGNUP + "\n")
    for event in events:
        print(f"\n{event['home_team']}  v  {event['away_team']}   ({event['commence_time']})")
        for sel in event.get("selections", []):
            quoted = len(sel.get("all_prices", []) or [])
            extra = f"  ({quoted} book{'s' if quoted != 1 else ''} quoting)" if quoted else ""
            print(f"   {sel['name']:<28} {sel['best_price']:>6.2f} @ {sel['best_bookmaker']}{extra}")
        if event.get("arb_exists"):
            print(f"   server flags arb_exists={event['arb_exists']} ({event.get('arb_profit_pct', 0):.2f}%)")


if __name__ == "__main__":
    main()
