"""Tip tracker: did your tips beat the closing price?

Log a tip at the best price on offer, then after the race settle it against the closing price
and the result: closing-line value (CLV) and profit per tip, and a running summary.

    export PUNTERSEDGE_API_KEY=your_key_here
    python examples/08_tip_tracker.py next                 # next AU races, best price per runner
    python examples/08_tip_tracker.py add RACE_ID 4        # log runner 4 at the best price right now
    python examples/08_tip_tracker.py add RACE_ID 4 --price 5.50 --book tab   # or the price you took
    python examples/08_tip_tracker.py settle               # after the race: close, finish, CLV, profit

Endpoints   GET /v1/racing/next-to-go     2 credits (next), 4 credits (add: one 200-race pull)
            GET /v1/racing/closing-lines  5 credits per tip settled
Plans       next and add work on the free tier; settle reads the closing-line archive, Standard and above.
Tips are kept in tips.csv beside this script.

Free key (no card): https://puntersedge.online/api?utm_source=demo&utm_medium=github&utm_campaign=tip-tracker#signup
CLV compares a price with the market's final view of the race, not with the result. This is a
measuring tool, not a betting strategy.
"""
import csv
import os
import sys
from datetime import datetime, timezone

import requests

API = "https://api.puntersedge.online/v1/racing"
UA = "puntersedge-examples/1.0 (+https://github.com/Propertyscout001/puntersedge-examples)"
KEY = os.environ.get("PUNTERSEDGE_API_KEY")
if not KEY:
    sys.exit("set PUNTERSEDGE_API_KEY first (free key: https://puntersedge.online/api#signup)")
H = {"X-API-Key": KEY, "User-Agent": UA}
FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tips.csv")
COLS = ["logged_at", "race_id", "venue", "race", "runner", "name", "taken_price", "taken_book",
        "close_price", "finish", "clv_pct", "profit"]


def get(path, **params):
    r = requests.get(f"{API}/{path}", params=params, headers=H, timeout=30)
    if r.status_code == 403:
        try:
            detail = r.json().get("detail") or r.text
        except ValueError:
            detail = r.text
        sys.exit(f"{path} is not on your plan: {detail}")
    r.raise_for_status()
    return r.json()


def load():
    if not os.path.exists(FILE):
        return []
    with open(FILE, newline="") as fh:
        return list(csv.DictReader(fh))


def save(rows):
    with open(FILE, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)


def best(runner):
    quotes = [(b["win_price"], b["key"]) for b in runner["bookmakers"] if b.get("win_price")]
    return max(quotes) if quotes else (None, None)


def cmd_next():
    for race in get("next-to-go", num_races=5, country="AU"):
        print(f"{race['race_id']}  {race['venue']} R{race['race_number']}  {race['start_time']}")
        for rn in race["runners"]:
            price, book = best(rn)
            if price:
                print(f"    {rn['number']:>2} {rn['name']:<24} {price:>6.2f} {book}")


def cmd_add(race_id, number, price=None, book=None):
    race = next((r for r in get("next-to-go", num_races=200) if r["race_id"] == race_id), None)
    venue = race["venue"] if race else ""
    rno = race["race_number"] if race else ""
    name = ""
    if race:
        rn = next(r for r in race["runners"] if r["number"] == number)
        name = rn["name"]
        if price is None:
            price, book = best(rn)
    if price is None:
        sys.exit("race not on the live board: pass --price and --book for a bet you already took")
    rows = load()
    rows.append({"logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "race_id": race_id,
                 "venue": venue, "race": rno, "runner": number, "name": name, "taken_price": price,
                 "taken_book": book or ""})
    save(rows)
    print(f"logged {name or 'runner ' + str(number)} at {float(price):.2f} ({book})")


def cmd_settle():
    rows = load()
    for t in rows:
        if t.get("finish"):
            continue
        lines = get("closing-lines", race_id=t["race_id"], resulted_only="true")["rows"]
        mine = [r for r in lines if r["runner_number"] == int(t["runner"]) and r["close_win_price"]]
        if not mine:
            continue                                   # not resulted yet: try again later
        close = max(r["close_win_price"] for r in mine)
        finish = mine[0]["finish_position"]
        taken = float(t["taken_price"])
        t.update(venue=t["venue"] or mine[0]["venue"], race=t["race"] or mine[0]["race_number"],
                 name=t["name"] or mine[0]["runner_name"], close_price=close, finish=finish,
                 clv_pct=round((taken / close - 1) * 100, 1),
                 profit=round(taken - 1, 2) if finish == 1 else -1.0)
        print(f"{t['venue']} R{t['race']} {t['name']}: took {taken:.2f}, closed {close:.2f} "
              f"(CLV {t['clv_pct']:+.1f}%), finished {finish}, profit {t['profit']:+.2f} units")
    save(rows)
    done = [t for t in rows if t.get("finish")]
    if done:
        beat = sum(1 for t in done if float(t["clv_pct"]) > 0)
        pnl = sum(float(t["profit"]) for t in done)
        print(f"\n{len(done)} settled: {beat} beat the closing price, profit {pnl:+.2f} units")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "next":
        cmd_next()
    elif a[0] == "add":
        opt = dict(zip(a[3::2], a[4::2]))
        cmd_add(a[1], int(a[2]), float(opt["--price"]) if "--price" in opt else None, opt.get("--book"))
    elif a[0] == "settle":
        cmd_settle()
    else:
        print(__doc__)
