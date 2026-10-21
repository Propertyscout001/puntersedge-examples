"""What a result row says about a race, in one word, from the fields the API sends.

GET /v1/racing/results rows carry three layers, read in this order:
  completeness.state   provisional | final_placings | complete_full_field | not_run   (from 2026-10-20)
  status               interim | final | abandoned
  field_status         complete | pending | overdue | unavailable | unsupported | not_applicable

PHASES (what the tracker reports):
  pending                no result row yet (the tracker sets this, not this module)
  interim                placings published but not final (they can still change)
  final_field_pending    final placings; the full finishing order is still being collected
  final_field_unavailable final placings; the full field's source is refusing or unavailable
                         (completeness.source_refused_since, field_status "unavailable")
  final_no_field_source  final placings; no supported source publishes this code's full field
  full_field_complete    final, and every runner's finish is in `runners`
  not_run                abandoned, postponed or transferred
"Source unavailable" is not "no result": the placings and dividends of such a race are still final.

New fields the API adds later are ignored, never an error. Rows from before `completeness` existed
are classified from `status` and `field_status` alone.
"""
from __future__ import annotations

from typing import Any

TERMINAL = frozenset({"full_field_complete", "not_run", "final_no_field_source"})


def _placings(row: dict) -> tuple:
    return tuple(sorted((p.get("position"), p.get("number")) for p in (row.get("placings") or [])
                        if isinstance(p, dict)))


def classify(row: dict) -> dict:
    c = row.get("completeness") if isinstance(row.get("completeness"), dict) else {}
    status = row.get("status")
    fs = row.get("field_status")
    state = c.get("state")
    refused = c.get("source_refused_since")
    if status == "abandoned" or state == "not_run":
        phase = "not_run"
    elif status != "final" or state == "provisional":
        phase = "interim"
    elif state == "complete_full_field" or fs == "complete":
        phase = "full_field_complete"
    elif refused or fs == "unavailable":
        phase = "final_field_unavailable"
    elif fs in ("unsupported", "not_applicable"):
        phase = "final_no_field_source"
    else:
        phase = "final_field_pending"           # pending, overdue, or not stated yet
    div = row.get("dividends") if isinstance(row.get("dividends"), dict) else {}
    return {
        "race_id": row.get("race_id"),
        "phase": phase,
        "status": status,
        "field_status": fs,
        "placings": _placings(row),
        "dividends": bool(div.get("straight")),
        "exotics": bool(div.get("exotics")),
        "source_refused_since": refused,
        "retrying": c.get("retrying"),
        "retry_until": c.get("retry_until"),
        "field_due_by": c.get("field_due_by"),
    }


def is_terminal(info: dict) -> bool:
    """Nothing more will arrive for this race: stop polling for it."""
    if info["phase"] in TERMINAL:
        return True
    # A final race whose field the collector has stopped retrying will not fill in.
    return info["phase"] in ("final_field_pending", "final_field_unavailable") and info.get("retrying") is False


def from_webhook(payload: dict) -> dict:
    """A race.result webhook body as a result-shaped row. It is sent once, when the race goes final,
    and carries no field status: the full field (if one is coming) still needs a results poll."""
    return {"race_id": payload.get("race_id"), "venue": payload.get("venue"),
            "race_number": payload.get("race_number"), "start_time": payload.get("start_time"),
            "status": payload.get("status"), "placings": payload.get("placings") or [],
            "dividends": payload.get("dividends") or {}, "field_status": None, "completeness": None}
