"""British and Irish racing: today's card bookmaker by bookmaker, then the results with SPs.

Prints each upcoming race in London time with every runner's price at every bookmaker that
quotes it (Ladbrokes / Coral, William Hill, Betway and the Australian books that price UK
racing), shown as a UK fraction where the decimal sits on the fractional ladder. Then the
races that have finished, with each runner's starting price.

Needs a free key (no card): https://puntersedge.online/uk-racing-odds-api?utm_source=github_examples&utm_medium=cookbook_uk

    export PUNTERSEDGE_API_KEY=your_key_here
    python examples/07_uk_racing_card.py

Standard library only. Two calls: next-to-go (2 credits) and results (2 credits).
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

API = "https://api.puntersedge.online/v1"
LONDON = ZoneInfo("Europe/London")

# The UK fractional ladder as bookmakers print it. A decimal becomes a fraction only when it
# sits on a rung; anything else stays a decimal rather than a fraction the book never quoted.
LADDER = [(1, 10), (1, 8), (1, 6), (1, 5), (2, 9), (1, 4), (2, 7), (1, 3), (4, 11), (2, 5),
          (4, 9), (1, 2), (8, 15), (4, 7), (8, 13), (4, 6), (8, 11), (4, 5), (5, 6), (10, 11),
          (20, 21), (1, 1), (21, 20), (11, 10), (6, 5), (5, 4), (13, 10), (11, 8), (7, 5),
          (6, 4), (8, 5), (13, 8), (17, 10), (7, 4), (9, 5), (15, 8), (19, 10), (2, 1),
          (21, 10), (85, 40), (11, 5), (9, 4), (23, 10), (12, 5), (5, 2), (13, 5), (11, 4),
          (14, 5), (3, 1), (16, 5), (10, 3), (17, 5), (7, 2), (18, 5), (4, 1), (9, 2), (5, 1),
          (11, 2), (6, 1), (13, 2), (7, 1), (15, 2), (8, 1), (17, 2), (9, 1), (10, 1), (11, 1),
          (12, 1), (14, 1), (15, 1), (16, 1), (18, 1), (20, 1), (22, 1), (25, 1), (28, 1), (33, 1),
          (40, 1), (50, 1), (66, 1), (80, 1), (100, 1), (125, 1), (150, 1), (200, 1), (250, 1)]


def fraction(decimal, tol=0.006):
    if not isinstance(decimal, (int, float)) or decimal <= 1:
        return None
    num, den = min(LADDER, key=lambda r: abs(1 + r[0] / r[1] - decimal))
    if abs(1 + num / den - decimal) > tol:
        return None
    return "evens" if num == den else f"{num}/{den}"


def price(decimal):
    return fraction(decimal) or f"{decimal:.2f}"


def get(path, **params):
    key = os.environ.get("PUNTERSEDGE_API_KEY")
    if not key:
        sys.exit("Set PUNTERSEDGE_API_KEY first. A free key, no card: "
                 "https://puntersedge.online/api?utm_source=github_examples&utm_medium=cookbook_uk#signup")
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"X-API-Key": key, "User-Agent": "puntersedge-examples/07"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def london(iso_utc):
    t = datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(LONDON)
    return t.strftime("%H:%M")


def show_card(races):
    for race in sorted(races, key=lambda r: r["start_time"]):
        books = sorted({leg["key"] for r in race["runners"] for leg in r["bookmakers"]})
        print(f"\n{london(race['start_time'])} {race['venue']} ({race['country']})  "
              f"{race.get('race_name') or ''}  places paid: {race.get('places_paid') or '-'}")
        print(" " * 26 + "".join(f"{b[:12]:>13}" for b in books))
        for runner in sorted(race["runners"], key=lambda r: r.get("number") or 0):
            legs = {leg["key"]: leg for leg in runner["bookmakers"]}
            cells = [price(legs[b]["win_price"]) if legs.get(b, {}).get("win_price") else "-" for b in books]
            print(f"{runner.get('number') or '':>2} {runner['name'][:22]:<23}" + "".join(f"{c:>13}" for c in cells))


def show_results(results):
    done = [r for r in results if r.get("category") == "horse"]
    if not done:
        print("\nNo British or Irish horse race has resulted in the last 24 hours.")
        return
    print("\nResults, with each runner's starting price:")
    for race in sorted(done, key=lambda r: r["start_time"]):
        print(f"\n{london(race['start_time'])} {race['venue']}  ({race.get('status')})")
        for runner in sorted(race["runners"], key=lambda r: (r.get("position") or 99)):
            if runner.get("position"):
                sp = runner.get("sp_fraction") or (f"{runner['sp']:.2f}" if runner.get("sp") else "-")
                print(f"  {runner['position']:>2}. {runner['name']:<24} SP {sp}")


if __name__ == "__main__":
    card = get("/racing/next-to-go", country="GB,IE", category="horse", num_races=6)
    print(f"Next {len(card)} British and Irish races, prices per bookmaker "
          "(UK fraction where the decimal sits on the ladder):")
    show_card(card)
    show_results(get("/racing/results", country="GB,IE", category="horse", hours_back=24, limit=3))
    print("\n18+. Gambling support: GamCare 0808 8020 133 (Great Britain), gamblingcare.ie (Ireland).")
