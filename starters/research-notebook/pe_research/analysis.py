"""Descriptive analysis only. Nothing here predicts anything or claims a betting return.

movement_by_position   how far prices moved from first to last captured price, grouped by where the
                       runner finished (winner / placed 2-3 / unplaced). Uses matched, final, unscratched
                       rows whose last price was within 300 s of the jump (`is_closing_line`) and whose
                       position is known.
market_percentage      for each race and bookmaker that priced every runner that started: the sum of
                       1 / closing price (the bookmaker's overround, 100% = no margin).
best_close_share       which bookmaker held the best closing price, share of runners (ties split).
"""
from __future__ import annotations

import pandas as pd


def usable(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    m = (df["match"] == "matched") & df["state"].isin(["final_placings", "complete_full_field"]) \
        & ~df["scratched"] & df["is_closing_line"].fillna(False).astype(bool) \
        & (df["open_win_price"] > 1) & (df["close_win_price"] > 1)
    return df[m].copy()


def _bucket(pos, known) -> str:
    if pos == 1:
        return "1 winner"
    if pos in (2, 3):
        return "2-3 placed"
    if pos is not None and pos == pos and pos >= 4:        # pos == pos drops NaN
        return "4+ unplaced"
    return "unplaced (position not published)" if known else "unknown"


def movement_by_position(df: pd.DataFrame) -> pd.DataFrame:
    u = usable(df)
    if u.empty:
        return pd.DataFrame(columns=["finish", "rows", "runners", "median_move_pct", "share_shortened"])
    u["move_pct"] = (u["close_win_price"] / u["open_win_price"] - 1.0) * 100.0
    u["finish"] = [_bucket(p, k) for p, k in zip(u["position"], u["position_known"])]
    u = u[u["finish"] != "unknown"].copy()
    u["shortened"] = u["close_win_price"] < u["open_win_price"]
    g = u.groupby("finish")
    out = pd.DataFrame({
        "rows": g.size(),
        "runners": u.drop_duplicates(["finish", "race_id", "runner_number"]).groupby("finish").size(),
        "median_move_pct": g["move_pct"].median().round(2),
        "share_shortened": g["shortened"].mean().round(3),
    }).reset_index()
    return out.sort_values("finish").reset_index(drop=True)


def market_percentage(df: pd.DataFrame) -> pd.DataFrame:
    u = usable(df)
    if u.empty:
        return pd.DataFrame(columns=["bookmaker_key", "races", "median_market_pct"])
    starters = u.groupby("race_id")["runner_number"].nunique()
    per = u.groupby(["race_id", "bookmaker_key"]).agg(n=("runner_number", "nunique"),
                                                      book=("close_win_price", lambda s: (1.0 / s).sum()))
    per = per.join(starters.rename("starters"), on="race_id")
    full = per[per["n"] == per["starters"]].reset_index()
    out = full.groupby("bookmaker_key").agg(races=("race_id", "nunique"),
                                             median_market_pct=("book", lambda s: round(s.median() * 100, 1)))
    return out.reset_index().sort_values("median_market_pct").reset_index(drop=True)


def best_close_share(df: pd.DataFrame) -> pd.DataFrame:
    u = usable(df)
    if u.empty:
        return pd.DataFrame(columns=["bookmaker_key", "share"])
    best = u.groupby(["race_id", "runner_number"])["close_win_price"].transform("max")
    top = u[u["close_win_price"] == best]
    weight = 1.0 / top.groupby(["race_id", "runner_number"])["bookmaker_key"].transform("count")
    share = weight.groupby(top["bookmaker_key"]).sum() / u[["race_id", "runner_number"]].drop_duplicates().shape[0]
    return share.round(3).rename("share").reset_index().sort_values("share", ascending=False).reset_index(drop=True)
