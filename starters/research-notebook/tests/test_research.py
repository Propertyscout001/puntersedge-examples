"""pe_research: sampling, joining on stable ids, and the descriptive analysis.  pytest -q"""
import json
import os
import re
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pe_research import analysis, join, sample                          # noqa: E402
from pe_research.client import ApiError, BudgetExceeded, Client         # noqa: E402

CL = sample.load_fixture("closing_lines.json")
RS = sample.load_fixture("results.json")
CONTRACT = json.load(open(os.path.join(ROOT, "..", "contract", "openapi-subset.json")))


@pytest.fixture
def joined():
    return join.join(CL["rows"], RS)


# ── join ────────────────────────────────────────────────────────────────────────────────────

def test_joins_only_on_race_id_and_reports_the_rest(joined):
    df, rep = joined
    assert rep["price_races"] == 5 and rep["matched_races"] == 4
    assert [r["race_id"] for r in rep["prices_without_result"]] == ["fx-C"]
    assert rep["results_without_prices"] == 1                 # fx-C-twin: same venue and start, NOT merged
    assert set(df.loc[df["race_id"] == "fx-C", "match"]) == {"race_unmatched"}


def test_scratchings_not_final_and_incomplete_fields_are_named(joined):
    df, rep = joined
    assert rep["scratched_rows"] == 2
    assert {r["race_id"]: r["state"] for r in rep["not_final"]} == {"fx-D": "provisional", "fx-E": "not_run"}
    assert [r["race_id"] for r in rep["field_incomplete"]] == ["fx-B"]


def test_position_disagreement_between_archive_and_result(joined):
    _df, rep = joined
    assert rep["position_disagreements"] == [{"race_id": "fx-A", "runner_number": 3,
                                              "archive_finish_position": 5.0, "position": 4.0}]


def test_unplaced_runner_in_a_placings_only_race_is_unknown_not_unplaced(joined):
    df, _ = joined
    k = df[(df["race_id"] == "fx-B") & (df["runner_number"] == 4)].iloc[0]
    assert k["position_known"] == False and pd.isna(k["position"])           # noqa: E712


def test_rows_before_completeness_existed_fall_back_to_status():
    old = dict(RS[1]); old.pop("completeness")
    assert join._state(old) == "final_placings"
    old["status"] = "abandoned"
    assert join._state(old) == "not_run"


def test_summary_lines_are_plain_counts(joined):
    lines = join.summary_lines(joined[1])
    assert lines[0] == "4 of 5 priced races joined to a result on race_id."
    assert any("not merged" in x for x in lines)


# ── analysis ────────────────────────────────────────────────────────────────────────────────

def test_movement_uses_only_matched_final_unscratched_closing_rows(joined):
    df, _ = joined
    u = analysis.usable(df)
    assert set(u["race_id"]) == {"fx-A", "fx-B"}
    assert not u["scratched"].any()
    assert "pointsbetau" not in set(u["bookmaker_key"])        # its last price was 900 s before the jump
    m = analysis.movement_by_position(df).set_index("finish")
    assert m.loc["1 winner", "runners"] == 2                    # fx-A no.2 and fx-B no.1
    assert m.loc["1 winner", "median_move_pct"] < 0             # both shortened in the fixture
    assert "4+ unplaced" in m.index and "unknown" not in m.index


def test_market_percentage_only_for_books_that_priced_every_starter(joined):
    df, _ = joined
    mp = analysis.market_percentage(df)
    assert set(mp["bookmaker_key"]) == {"tab", "sportsbet", "ladbrokes_au"}
    assert (mp["median_market_pct"] > 0).all()


def test_best_close_share_sums_to_one(joined):
    df, _ = joined
    s = analysis.best_close_share(df)
    assert abs(s["share"].sum() - 1.0) < 0.01


def test_empty_inputs_give_empty_tables_not_errors():
    df, rep = join.join([], [])
    assert rep["matched_races"] == 0
    assert analysis.movement_by_position(df).empty and analysis.market_percentage(df).empty


# ── client ──────────────────────────────────────────────────────────────────────────────────

class FakeResp:
    def __init__(self, status, body, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}

    def json(self):
        if self._body is None:
            raise ValueError
        return self._body


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, params=None, timeout=None, headers=None):
        self.calls.append((url, dict(params or {}), dict(headers or {})))
        return self.responses.pop(0)


def test_client_key_in_header_never_in_url_or_repr():
    s = FakeSession([FakeResp(200, [], {"X-Credits-Cost": "2"})])
    c = Client("secret-key-1", session=s, sleep=lambda x: None)
    c.get("/v1/racing/results", date="2026-10-21")
    url, params, headers = s.calls[0]
    assert headers["X-API-Key"] == "secret-key-1" and "secret-key-1" not in url + json.dumps(params)
    assert "secret-key-1" not in repr(c) and c.credits == 2


def test_client_retries_429_and_5xx_then_gives_up_and_stops_on_fatal():
    waits = []
    s = FakeSession([FakeResp(429, {"detail": "slow"}, {"Retry-After": "3"}), FakeResp(503, None), FakeResp(200, {"ok": 1})])
    assert Client("k", session=s, sleep=waits.append).get("/x")[0] == {"ok": 1}
    assert waits[0] >= 3 and len(waits) == 2
    s = FakeSession([FakeResp(403, {"detail": "Closing lines are available on Standard and above."})])
    with pytest.raises(ApiError) as e:
        Client("k", session=s, sleep=lambda x: None).get("/x")
    assert e.value.code == "plan" and e.value.fatal and "Standard" in e.value.message and len(s.calls) == 1


def test_client_budget_caps_calls():
    s = FakeSession([FakeResp(200, [])] * 5)
    c = Client("k", session=s, max_calls=2, sleep=lambda x: None)
    c.get("/a"); c.get("/b")
    with pytest.raises(BudgetExceeded):
        c.get("/c")


def test_client_refuses_to_start_without_a_key(monkeypatch):
    monkeypatch.delenv("PUNTERSEDGE_API_KEY", raising=False)
    with pytest.raises(ApiError):
        Client()
    with pytest.raises(ApiError):
        Client("replace-with-your-key")


# ── sampling ────────────────────────────────────────────────────────────────────────────────

class FakeClient:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, path, **params):
        self.calls.append((path, params))
        return self.pages[path].pop(0)


def test_closing_lines_pages_until_total_rows():
    rows = [{"race_id": str(i)} for i in range(5)]
    fc = FakeClient({"/v1/racing/closing-lines": [({"rows": rows[:2], "total_rows": 5}, {}),
                                                    ({"rows": rows[2:4], "total_rows": 5}, {}),
                                                    ({"rows": rows[4:], "total_rows": 5}, {})]})
    got = sample.closing_lines(fc, "2026-10-21", page=2)
    assert len(got) == 5 and [c[1]["offset"] for c in fc.calls] == [0, 2, 4]
    assert all(c[1]["include_scratched"] == "true" for c in fc.calls)


def test_results_page_by_x_limit_applied():
    fc = FakeClient({"/v1/racing/results": [([{"race_id": "a"}] * 200, {"X-Limit-Applied": "200"}),
                                             ([{"race_id": "b"}] * 3, {"X-Limit-Applied": "200"})]})
    assert len(sample.results(fc, "2026-10-21")) == 203
    assert [c[1]["offset"] for c in fc.calls] == [0, 200]


def test_free_sample_shapes_price_history_like_closing_lines():
    ph = {"race_id": "r1", "venue": "V", "race_number": 1, "category": "horse", "country": "AU",
          "start_time": "2026-10-21T02:00:00Z",
          "runners": [{"name": "A", "number": 1, "bookmakers": [{"key": "tab", "open_price": 3.0, "close_price": 2.5,
                                                                 "close_secs_to_jump": 30, "open_is_baseline": True}]}]}
    fc = FakeClient({"/v1/racing/results": [([{"race_id": "r1"}, {"race_id": None}], {})],
                     "/v1/racing/price-history": [(ph, {})]})
    prices, res = sample.free_sample(fc, max_races=5)
    assert len(fc.calls) == 2                                    # races without a race_id are skipped
    assert prices[0]["is_closing_line"] is True and prices[0]["close_win_price"] == 2.5
    df, rep = join.join(prices, res)
    assert rep["matched_races"] == 1


def test_default_date_is_yesterday_aet():
    import datetime as dt
    assert sample.default_date(dt.date(2026, 10, 22)) == "2026-10-21"


# ── contract and secrets ────────────────────────────────────────────────────────────────────

def test_fixtures_use_the_live_schema_field_names():
    cl = CONTRACT["paths"]["/v1/racing/closing-lines"]
    row_fields = set(cl["nested"]["rows"])
    for r in CL["rows"]:
        assert set(r) <= row_fields, set(r) - row_fields
    rs = CONTRACT["paths"]["/v1/racing/results"]
    for r in RS:
        assert set(r) <= set(rs["fields"]), set(r) - set(rs["fields"])
        assert set(r["completeness"]) <= set(rs["nested"]["completeness"])
        assert r["completeness"]["state"] in rs["enums"]["completeness.state"]
    for q in ("date", "country", "category", "limit", "offset", "include_scratched"):
        assert q in cl["query"]
    for q in ("date", "hours_back", "status", "limit", "offset", "country"):
        assert q in rs["query"]
    assert {"race_id", "include_points"} <= set(CONTRACT["paths"]["/v1/racing/price-history"]["query"])


def test_no_key_like_strings_in_the_project():
    for d, _, files in os.walk(ROOT):
        if ".ipynb_checkpoints" in d or "__pycache__" in d:
            continue
        for f in files:
            p = os.path.join(d, f)
            if f.endswith((".png", ".pyc")):
                continue
            s = open(p, encoding="utf-8", errors="ignore").read()
            assert not re.search(r"\bpe_[0-9a-f]{20,}\b", s), p
