"""Best available win/place price per runner, across every covered bookmaker.

Endpoint    GET /v1/racing/best-odds         (3 credits per call, measured 2026-08-30)
Free tier   3,000 credits/month  ->  ~1,000 calls.

`market_percentage` is the sum of implied probabilities at the best available prices,
times 100. It describes how competitive the combined market is — nothing else.

Needs a key (free tier is fine):
https://puntersedge.online/api?utm_source=github_examples&utm_medium=cookbook_nokey#signup
"""
import sys

from puntersedge import PuntersEdge
from puntersedge.exceptions import ApiKeyError

SIGNUP = "https://puntersedge.online/api?utm_source=github_examples&utm_medium=cookbook_nokey#signup"


def main():
    try:
        pe = PuntersEdge()
    except ApiKeyError:
        sys.exit("No API key found. Free keys (3,000 credits/month, no card):\n  " + SIGNUP)

    races = pe.racing_best_odds(num_races=3)
    for race in races:
        print(
            f"\n{race['venue']} R{race['race_number']} ({race['category']}, {race['country']})"
            f"  jumps {race['start_time']}"
        )
        print(
            f"  market {race['market_percentage']:.1f}% across {race['books_compared']} books"
        )
        print(f"  {'no.':>4} {'runner':<24} {'best win':>9} {'@ book':<14} {'best place':>10} {'@ book':<14}")
        for runner in race.get("runners", []):
            win, place = runner.get("best_win") or {}, runner.get("best_place") or {}
            print(
                f"  {runner['number']:>4} {runner['name']:<24}"
                f" {win.get('price', 0):>9.2f} {win.get('bookmaker', '-'):<14}"
                f" {place.get('price', 0):>10.2f} {place.get('bookmaker', '-'):<14}"
            )


if __name__ == "__main__":
    main()
