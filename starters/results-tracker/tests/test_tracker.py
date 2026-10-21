"""Results tracker: classification, de-duplication, polling, retries, webhooks.  pytest -q"""
import hashlib
import hmac
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pe_results import tracker as T                                     # noqa: E402
from pe_results.classify import classify, from_webhook, is_terminal     # noqa: E402
from pe_results.client import ApiError, BudgetSpent, Client             # noqa: E402
from pe_results.replay import ReplayClient, _load                       # noqa: E402
from pe_results.state import Store                                      # noqa: E402
import webhook_receiver as W                                            # noqa: E402

FX = os.path.join(ROOT, "fixtures")
POLLS = [_load(os.path.join(FX, f"poll_{i}.json")) for i in range(1, 6)]
CONTRACT = json.load(open(os.path.join(ROOT, "..", "contract", "openapi-subset.json")))


def row(poll, rid):
    return next(r for r in POLLS[poll - 1] if r["race_id"] == rid)


# ── classify ────────────────────────────────────────────────────────────────────────────────

def test_phases_from_completeness():
    assert classify(row(2, "fx-r1"))["phase"] == "interim"
    assert classify(row(3, "fx-r1"))["phase"] == "final_field_pending"
    assert classify(row(5, "fx-r1"))["phase"] == "full_field_complete"
    assert classify(row(3, "fx-r2"))["phase"] == "final_field_unavailable"
    assert classify(row(2, "fx-r3"))["phase"] == "not_run"


def test_rows_without_completeness_and_unknown_fields():
    old = dict(row(3, "fx-r1")); old.pop("completeness"); old["a_field_added_next_year"] = {"x": 1}
    assert classify(old)["phase"] == "final_field_pending"
    old["field_status"] = "unsupported"
    assert classify(old)["phase"] == "final_no_field_source" and is_terminal(classify(old))


def test_terminal_rules():
    assert not is_terminal(classify(row(3, "fx-r1")))            # field still coming
    assert is_terminal(classify(row(5, "fx-r1")))
    assert not is_terminal(classify(row(3, "fx-r2")))            # source refusing, collector still retrying
    assert is_terminal(classify(row(5, "fx-r2")))                # retrying stopped: the field will not come
    assert is_terminal(classify(row(2, "fx-r3")))


# ── state: every change once ────────────────────────────────────────────────────────────────

def kinds(events):
    return [(e["race_id"], e["kind"]) for e in events]


def test_meeting_progresses_and_nothing_is_reported_twice():
    s = Store()
    for rid in ("fx-r1", "fx-r2", "fx-r3"):
        s.track({"race_id": rid})
    seen = []
    for p in POLLS:
        for r in p:
            if r.get("race_id"):
                seen += kinds(s.apply(r))
    assert seen == [
        ("fx-r1", "result_interim"), ("fx-r3", "race_not_run"),
        ("fx-r1", "result_final"), ("fx-r1", "dividends_declared"),
        ("fx-r2", "result_final"), ("fx-r2", "field_source_unavailable"),
        ("fx-r1", "exotics_declared"),
        ("fx-r1", "full_field_complete"), ("fx-r2", "full_field_not_coming"),
    ]
    again = [e for r in POLLS[-1] for e in s.apply(r)]
    assert again == []                                           # re-polling the same data: silent
    assert s.remaining() == []


def test_state_survives_a_restart(tmp_path):
    db = str(tmp_path / "t.sqlite3")
    s = Store(db)
    s.apply(row(3, "fx-r1"))
    s2 = Store(db)
    assert s2.apply(row(3, "fx-r1")) == []
    assert kinds(s2.apply(row(5, "fx-r1"))) == [("fx-r1", "full_field_complete"), ("fx-r1", "exotics_declared")]
    assert Store(db).apply(row(5, "fx-r1")) == []


def test_interim_placings_change_is_reported():
    s = Store()
    r = row(2, "fx-r1")
    s.apply(r)
    moved = dict(r, placings=[{"position": 1, "number": 1}, {"position": 2, "number": 3}])
    assert kinds(s.apply(moved)) == [("fx-r1", "placings_changed")]


def test_a_late_bare_final_never_moves_a_race_backwards():
    s = Store()
    s.apply(row(5, "fx-r1"))
    hook = from_webhook(_load(os.path.join(FX, "webhook_race_result.json")))
    s.apply(hook)
    assert s.phase("fx-r1") == "full_field_complete"


# ── polling ─────────────────────────────────────────────────────────────────────────────────

def test_replay_tracks_the_venue_reports_loose_ends_and_stops_when_done():
    client, store, out = ReplayClient(FX), Store(), []
    for r in T.select_races(client, date="2026-10-24", venue="fixture park"):
        store.track(r)
    assert len(store.tracked()) == 3                              # "Elsewhere" filtered out
    res = T.run(client, store, date="2026-10-24", venue="Fixture Park", interval=60, emit=out.append,
                sleep=lambda s: None)
    assert res == {"stopped": "done", "polls": 5}
    assert {"kind": "result_without_race_id", "venue": "Fixture Park", "race_number": 4,
            "start_time": "2026-10-24T09:00:00Z", "status": "final"} in out
    assert sum(1 for e in out if e.get("kind") == "result_final") == 2


class Seq:
    """A fake API session answering a scripted sequence of (status, body, headers)."""
    def __init__(self, script):
        self.script, self.calls = list(script), []

    def get(self, url, params=None, timeout=None, headers=None):
        self.calls.append((url, params, headers))
        status, body, hdrs = self.script.pop(0)
        return Resp(status, body, hdrs)


class Resp:
    def __init__(self, status, body, headers):
        self.status_code, self._b, self.headers = status, body, headers or {}

    def json(self):
        if self._b is None:
            raise ValueError
        return self._b


def test_retries_429_with_retry_after_and_5xx_then_succeeds():
    waits = []
    s = Seq([(429, {"detail": "slow"}, {"Retry-After": "30"}), (502, None, {}), (200, [], {"X-Credits-Cost": "2"})])
    c = Client("k", session=s, sleep=waits.append)
    assert c.get("/v1/racing/results")[0] == []
    assert waits[0] >= 30 and len(waits) == 2 and c.credits == 2 and c.requests == 3


@pytest.mark.parametrize("status", [401, 402, 403, 422])
def test_fatal_refusals_are_not_retried_and_stop_the_run(status):
    s = Seq([(status, {"detail": "explained"}, {})])
    c = Client("k", session=s, sleep=lambda x: None)
    store, out = Store(), []
    store.track({"race_id": "x"})
    res = T.run(c, store, date="2026-10-24", emit=out.append, sleep=lambda x: None)
    assert res["stopped"] == "fatal" and len(s.calls) == 1
    assert out[-1]["reason"] == "explained"


def test_budget_stops_cleanly():
    s = Seq([(200, [], {})] * 10)
    c = Client("k", session=s, max_requests=2, sleep=lambda x: None)
    store, out = Store(), []
    store.track({"race_id": "never-resulted"})
    res = T.run(c, store, date="2026-10-24", emit=out.append, sleep=lambda x: None)
    assert res["stopped"] == "budget" and len(s.calls) == 2


def test_key_is_a_header_never_in_the_url_or_repr():
    s = Seq([(200, [], {})])
    c = Client("my-secret", session=s, sleep=lambda x: None)
    c.get("/v1/racing/results", date="2026-10-24")
    url, params, headers = s.calls[0]
    assert headers["X-API-Key"] == "my-secret" and "my-secret" not in url + json.dumps(params) + repr(c)


def test_interval_has_a_floor_of_sixty_seconds():
    slept = []
    client, store = ReplayClient(FX), Store()
    store.track({"race_id": "fx-r1"})
    T.run(client, store, date="2026-10-24", interval=5, emit=lambda e: None, sleep=slept.append)
    assert slept and min(slept) == 60


# ── webhooks ────────────────────────────────────────────────────────────────────────────────

def sign(body: bytes, secret: str, t: int) -> str:
    return f"t={t},v1=" + hmac.new(secret.encode(), str(t).encode() + b"." + body, hashlib.sha256).hexdigest()


HOOK = json.dumps(_load(os.path.join(FX, "webhook_race_result.json"))).encode()


def test_webhook_verified_once_then_duplicate_dropped():
    s, now = Store(), 1_800_000_000
    h = {"x-puntersedge-signature": sign(HOOK, "whsec", now)}
    status, events = W.handle(s, h, HOOK, ["whsec"], now=now)
    assert status == 200 and kinds(events) == [("fx-r1", "result_final"), ("fx-r1", "dividends_declared")]
    assert W.handle(s, h, HOOK, ["whsec"], now=now) == (200, [])


def test_webhook_rejects_bad_signature_stale_timestamp_and_accepts_previous_secret():
    s, now = Store(), 1_800_000_000
    assert W.handle(s, {"x-puntersedge-signature": sign(HOOK, "wrong", now)}, HOOK, ["whsec"], now=now)[0] == 401
    assert W.handle(s, {"x-puntersedge-signature": sign(HOOK, "whsec", now - 301)}, HOOK, ["whsec"], now=now)[0] == 401
    assert W.handle(s, {}, HOOK, ["whsec"], now=now)[0] == 401
    tampered = HOOK.replace(b'"position": 1', b'"position": 2')
    assert W.handle(s, {"x-puntersedge-signature": sign(HOOK, "whsec", now)}, tampered, ["whsec"], now=now)[0] == 401
    assert W.handle(s, {"x-puntersedge-signature": sign(HOOK, "old", now)}, HOOK, ["new", "old"], now=now)[0] == 200


def test_webhook_ignores_other_events_and_oversized_bodies():
    s, now = Store(), 1_800_000_000
    other = json.dumps({"event": "arb.opportunity", "event_id": "e2"}).encode()
    assert W.handle(s, {"x-puntersedge-signature": sign(other, "k", now)}, other, ["k"], now=now) == (200, [])
    big = b"x" * (W.MAX_BODY + 1)
    assert W.handle(s, {}, big, ["k"], now=now)[0] == 413


# ── contract and secrets ────────────────────────────────────────────────────────────────────

def test_fixtures_match_the_live_schema():
    rs = CONTRACT["paths"]["/v1/racing/results"]
    for p in POLLS:
        for r in p:
            assert set(r) <= set(rs["fields"]), set(r) - set(rs["fields"])
            assert set(r["completeness"]) <= set(rs["nested"]["completeness"])
            assert r["status"] in rs["enums"]["status"] and r["field_status"] in rs["enums"]["field_status"]
    ev = CONTRACT["paths"]["/v1/racing/events"]
    for e in _load(os.path.join(FX, "events.json")):
        assert set(e) <= set(ev["fields"]), set(e) - set(ev["fields"])
    assert {"date", "venue", "country", "category", "limit", "offset"} <= set(rs["query"])
    assert {"date", "country", "category"} <= set(ev["query"]) and "venue" not in ev["query"]
    hook = _load(os.path.join(FX, "webhook_race_result.json"))
    assert set(hook) <= set(CONTRACT["webhook_race_result"]["fields"])


def test_no_key_like_strings_in_the_project():
    for d, _, files in os.walk(ROOT):
        if "__pycache__" in d:
            continue
        for f in files:
            s = open(os.path.join(d, f), encoding="utf-8", errors="ignore").read()
            assert not re.search(r"\bpe_[0-9a-f]{20,}\b", s), f
