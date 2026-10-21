"""Offline replay for `tracker.py --replay fixtures/`: serves the synthetic fixture polls in order.

fixtures/events.json      what /v1/racing/events returns for the demo meeting
fixtures/poll_*.json      successive /v1/racing/results answers, as a live meeting would progress
All SYNTHETIC: invented races and runners, not real results.
"""
from __future__ import annotations

import glob
import json
import os


def _load(path):
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    return doc["data"] if isinstance(doc, dict) and "_fixture" in doc else doc


class ReplayClient:
    def __init__(self, directory: str):
        self.events = _load(os.path.join(directory, "events.json"))
        self.polls = [_load(p) for p in sorted(glob.glob(os.path.join(directory, "poll_*.json")))]
        self.date = (self.events[0]["start_time"][:10]) if self.events else None
        self.requests = 0
        self.credits = 0

    def get(self, path, **params):
        self.requests += 1
        if path == "/v1/racing/events":
            return self.events, {}
        if path == "/v1/racing/results":
            i = min(self._i, len(self.polls) - 1)
            self._i += 1
            return self.polls[i], {"x-limit-applied": "200"}
        raise KeyError(path)

    _i = 0
