"""Join closing prices to results on the API's stable identifiers, and say what did not join.

THE RULE: prices and results join on `race_id` (the API's own race identifier, carried by both),
and runners on `runner_number` within a race. Nothing is matched on venue and start time, even when
they look identical: two different races can share both (twin meetings, a re-run, a code mix-up),
and a guessed merge corrupts a study silently. A price race with no result under its race_id is
reported as unmatched, with the details needed to look into it, and left out of the analysis.

What the report separates:
  matched races            a result exists under the price row's race_id
  prices without a result  price races whose race_id has no result row (listed)
  results without prices   result rows whose race_id has no price rows (counted)
  scratched                price rows for runners scratched before the race (excluded from movement)
  not final                races whose result is interim (provisional) or abandoned (not run)
  field incomplete         final races where only the placegetters' positions are known
  position disagreements   the price archive's finish_position differs from the result's
"""
from __future__ import annotations

from typing import Any

import pandas as pd


def _state(res: dict) -> str:
    c = res.get("completeness") or {}
    if c.get("state"):
        return c["state"]
    status = res.get("status")                       # rows from before 2026-10-20 carry no completeness
    if status == "abandoned":
        return "not_run"
    if status != "final":
        return "provisional"
    return "complete_full_field" if res.get("field_status") == "complete" else "final_placings"


def positions(res: dict) -> dict:
    """{runner number: position or None}, and which numbers ran / were scratched."""
    pos, scratched = {}, set()
    for r in res.get("runners") or []:
        n = r.get("number")
        if n is None:
            continue
        if r.get("status") == "scratched":
            scratched.add(n)
            continue
        pos[n] = r.get("position")
    for p in res.get("placings") or []:                 # placegetters are known even without a field
        if p.get("number") is not None and pos.get(p["number"]) is None:
            pos[p["number"]] = p.get("position")
    return {"positions": pos, "scratched": scratched,
            "field_known": res.get("field_status") == "complete" and bool(res.get("runners"))}


def join(price_rows: list, results: list) -> tuple[pd.DataFrame, dict]:
    by_race = {r["race_id"]: r for r in results if r.get("race_id")}
    price_races = {}
    for row in price_rows:
        price_races.setdefault(row.get("race_id"), row)
    out = []
    for row in price_rows:
        res = by_race.get(row.get("race_id"))
        rec = {k: row.get(k) for k in ("race_id", "venue", "race_number", "category", "start_time",
                                       "bookmaker_key", "runner_number", "runner_name",
                                       "open_win_price", "close_win_price", "is_closing_line")}
        rec["scratched_in_prices"] = bool(row.get("scratched"))
        rec["archive_finish_position"] = row.get("finish_position")
        if res is None:
            rec.update(match="race_unmatched", state=None, position=None, position_known=False,
                       scratched=rec["scratched_in_prices"])
        else:
            p = positions(res)
            n = row.get("runner_number")
            scratched = rec["scratched_in_prices"] or n in p["scratched"]
            pos = p["positions"].get(n)
            known = pos is not None or p["field_known"]
            rec.update(match="matched" if (n in p["positions"] or scratched or not p["field_known"]) else "runner_unmatched",
                       state=_state(res), position=pos, position_known=known, scratched=scratched)
        out.append(rec)
    df = pd.DataFrame(out)
    if df.empty:
        return df, {"price_races": 0, "result_races": len(by_race), "matched_races": 0,
                    "prices_without_result": [], "results_without_prices": len(by_race),
                    "scratched_rows": 0, "not_final": [], "field_incomplete": [], "position_disagreements": []}
    matched_ids = set(df.loc[df["match"] != "race_unmatched", "race_id"])
    unmatched = [{"race_id": rid, "venue": r.get("venue"), "race_number": r.get("race_number"),
                  "start_time": r.get("start_time")}
                 for rid, r in price_races.items() if rid not in matched_ids]
    races = df.drop_duplicates("race_id")
    disagree = df[(df["match"] == "matched") & df["archive_finish_position"].notna() & df["position"].notna()
                  & (df["archive_finish_position"] != df["position"])]
    report = {
        "price_races": int(df["race_id"].nunique()),
        "result_races": len(by_race),
        "matched_races": len(matched_ids),
        "prices_without_result": unmatched,
        "results_without_prices": len(set(by_race) - set(price_races)),
        "scratched_rows": int(df["scratched"].sum()),
        "not_final": races.loc[races["state"].isin(["provisional", "not_run"]),
                               ["race_id", "venue", "race_number", "state"]].to_dict("records"),
        "field_incomplete": races.loc[races["state"] == "final_placings",
                                      ["race_id", "venue", "race_number"]].to_dict("records"),
        "position_disagreements": disagree.drop_duplicates(["race_id", "runner_number"])[
            ["race_id", "runner_number", "archive_finish_position", "position"]].to_dict("records"),
    }
    return df, report


def summary_lines(report: dict) -> list:
    return [
        f"{report['matched_races']} of {report['price_races']} priced races joined to a result on race_id.",
        f"{len(report['prices_without_result'])} priced races have no result under their race_id (listed, not merged).",
        f"{report['results_without_prices']} resulted races have no prices in this sample.",
        f"{report['scratched_rows']} price rows are scratched runners (excluded from movement).",
        f"{len(report['not_final'])} races are not final (interim or not run) and are excluded.",
        f"{len(report['field_incomplete'])} final races have placegetters only (unplaced runners' positions unknown).",
        f"{len(report['position_disagreements'])} runners where the archive's finish position differs from the result.",
    ]
