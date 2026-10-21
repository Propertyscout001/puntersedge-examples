"""Remember what has been reported, so nothing is reported twice (SQLite, stdlib).

apply(row) compares a result row with the stored snapshot of that race and returns only the
changes, as events:

  result_interim        placings first seen, not final yet
  placings_changed      interim placings moved
  result_final          the result is final (settle on this, never on interim)
  dividends_declared    straight dividends appeared
  exotics_declared      exotic dividends appeared (they follow the placings by a few minutes)
  full_field_complete   every runner's finish is in
  field_source_unavailable   the full field's source is refusing / unavailable (placings still final)
  no_full_field_source  no supported source publishes this race's full field
  race_not_run          abandoned, postponed or transferred
  full_field_not_coming the collector has stopped retrying: placings stay final, no full field

Each event is stored with a key unique to (race, kind, content), so re-polling the same data, a
retried request, a duplicate webhook delivery or a restart never emits it again.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
from typing import Optional

from .classify import classify, is_terminal

_SCHEMA = """
CREATE TABLE IF NOT EXISTS races (
  race_id TEXT PRIMARY KEY, venue TEXT, race_number INTEGER, start_time TEXT,
  phase TEXT NOT NULL DEFAULT 'pending', placings TEXT, dividends INTEGER DEFAULT 0,
  exotics INTEGER DEFAULT 0, terminal INTEGER DEFAULT 0, updated_at TEXT);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, event_key TEXT UNIQUE NOT NULL, race_id TEXT NOT NULL,
  kind TEXT NOT NULL, at TEXT NOT NULL, detail TEXT);
CREATE TABLE IF NOT EXISTS deliveries (event_id TEXT PRIMARY KEY, received_at TEXT NOT NULL);
"""


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path)
        self.db.executescript(_SCHEMA)

    def track(self, race: dict) -> None:
        """Start following a race (from /v1/racing/events, or a race_id you supply)."""
        self.db.execute("INSERT OR IGNORE INTO races (race_id, venue, race_number, start_time, updated_at) "
                        "VALUES (?, ?, ?, ?, ?)", (race["race_id"], race.get("venue"), race.get("race_number"),
                                                    race.get("start_time"), _now()))
        self.db.commit()

    def tracked(self) -> list:
        cur = self.db.execute("SELECT race_id, venue, race_number, start_time, phase FROM races ORDER BY start_time, race_id")
        return [dict(zip(("race_id", "venue", "race_number", "start_time", "phase"), r)) for r in cur.fetchall()]

    def remaining(self) -> list:
        """Tracked races that can still change (not abandoned, not complete, field still coming)."""
        return [r for r in self.tracked() if not self.db.execute(
            "SELECT terminal FROM races WHERE race_id = ?", (r["race_id"],)).fetchone()[0]]

    def phase(self, race_id: str) -> Optional[str]:
        r = self.db.execute("SELECT phase FROM races WHERE race_id = ?", (race_id,)).fetchone()
        return r[0] if r else None

    def seen_delivery(self, event_id: str) -> bool:
        """True if this webhook delivery was already processed; records it otherwise."""
        if not event_id:
            return False
        cur = self.db.execute("INSERT OR IGNORE INTO deliveries (event_id, received_at) VALUES (?, ?)",
                              (event_id, _now()))
        self.db.commit()
        return cur.rowcount == 0

    def _emit(self, out: list, race_id: str, kind: str, detail: dict) -> None:
        blob = json.dumps(detail, sort_keys=True, default=str)
        key = hashlib.sha256(f"{race_id}|{kind}|{blob}".encode()).hexdigest()
        cur = self.db.execute("INSERT OR IGNORE INTO events (event_key, race_id, kind, at, detail) VALUES (?, ?, ?, ?, ?)",
                              (key, race_id, kind, _now(), blob))
        if cur.rowcount:
            out.append({"race_id": race_id, "kind": kind, **detail})

    def apply(self, row: dict) -> list:
        info = classify(row)
        rid = info["race_id"]
        if not rid:
            return []
        prev = self.db.execute("SELECT phase, placings, dividends, exotics FROM races WHERE race_id = ?", (rid,)).fetchone()
        if prev is None:
            self.track({"race_id": rid, "venue": row.get("venue"), "race_number": row.get("race_number"),
                        "start_time": row.get("start_time")})
            prev = ("pending", None, 0, 0)
        old_phase, old_pl, old_div, old_ex = prev
        new_pl = json.dumps(info["placings"])
        out: list = []
        placings = [{"position": p, "number": n} for p, n in info["placings"]]
        if info["phase"] == "not_run":
            self._emit(out, rid, "race_not_run", {"status": info["status"]})
        elif info["phase"] == "interim":
            if old_phase == "pending" or old_pl is None:
                self._emit(out, rid, "result_interim", {"placings": placings})
            elif new_pl != old_pl:
                self._emit(out, rid, "placings_changed", {"placings": placings})
        else:
            self._emit(out, rid, "result_final", {"placings": placings})
            if info["phase"] == "full_field_complete":
                self._emit(out, rid, "full_field_complete", {})
            elif info["phase"] == "final_field_unavailable":
                # keyed on when the refusal began only: the retry horizon moves and must not re-emit
                self._emit(out, rid, "field_source_unavailable", {"since": info["source_refused_since"]})
            elif info["phase"] == "final_no_field_source":
                self._emit(out, rid, "no_full_field_source", {"field_status": info["field_status"]})
            if info["phase"] in ("final_field_pending", "final_field_unavailable") and is_terminal(info):
                self._emit(out, rid, "full_field_not_coming", {"field_status": info["field_status"]})
        if info["dividends"] and not old_div:
            self._emit(out, rid, "dividends_declared", {})
        if info["exotics"] and not old_ex:
            self._emit(out, rid, "exotics_declared", {})
        # Never move a race backwards (a webhook's bare "final" after a full field, a stale poll).
        order = ["pending", "interim", "final_field_pending", "final_field_unavailable",
                 "final_no_field_source", "full_field_complete", "not_run"]
        phase = info["phase"] if order.index(info["phase"]) >= order.index(old_phase or "pending") else old_phase
        done = int(is_terminal(dict(info, phase=phase)))
        self.db.execute("UPDATE races SET phase = ?, placings = ?, dividends = ?, exotics = ?, terminal = ?, "
                        "updated_at = ? WHERE race_id = ?", (phase, new_pl, int(info["dividends"] or old_div),
                                                             int(info["exotics"] or old_ex), done, _now(), rid))
        self.db.commit()
        return out
