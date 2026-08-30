"""Racing steamers and drifters — the biggest price moves before the jump.

Endpoint    GET /v1/racing/movers            (3 credits per call, measured 2026-08-30)
Free tier   1,500 credits/month  ->  ~500 calls.

The API reports each mover's direction as `firming` (price shortening) or `drifting`
(price easing). This lists the moves; it says nothing about whether following them
is a good idea.

Usage:
    python 03_movers.py                 # both directions
    python 03_movers.py --min-move 10   # only moves of 10%+

Needs a key (free tier is fine):
https://puntersedge.online/api?utm_source=github_examples&utm_medium=cookbook_nokey#signup
"""
import argparse
import os
import sys

import requests

SIGNUP = "https://puntersedge.online/api?utm_source=github_examples&utm_medium=cookbook_nokey#signup"
UA = "puntersedge-examples/1.0 (+https://github.com/Propertyscout001/puntersedge-examples)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-move", type=float, default=None, help="minimum move in percent")
    ap.add_argument("--categories", default=None, help="e.g. horse,greyhound,harness")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    key = os.environ.get("PUNTERSEDGE_API_KEY")
    if not key:
        sys.exit("Set PUNTERSEDGE_API_KEY. Free keys (1,500 credits/month, no card):\n  " + SIGNUP)

    params = {"limit": args.limit}
    if args.min_move is not None:
        params["min_move_pct"] = args.min_move
    if args.categories:
        params["categories"] = args.categories

    resp = requests.get(
        "https://api.puntersedge.online/v1/racing/movers",
        params=params,
        headers={"X-API-Key": key, "User-Agent": UA},
        timeout=15,
    )
    resp.raise_for_status()

    rows = resp.json()
    print(f"{'venue':<18} {'race':>4}  {'runner':<24} {'open':>6} {'now':>6} {'move':>7}  {'jump':>6}  dir")
    for m in rows:
        print(
            f"{m['venue']:<18} R{m['race_number']:<3}"
            f"  {m['runner']:<24} {m['open_price']:>6.2f} {m['current_price']:>6.2f}"
            f" {m['move_pct']:>+6.1f}%  {m['mins_to_jump']:>5.0f}m  {m['direction']}"
        )


if __name__ == "__main__":
    main()
