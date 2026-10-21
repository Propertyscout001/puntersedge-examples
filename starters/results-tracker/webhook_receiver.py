#!/usr/bin/env python3
"""Receive race.result webhooks instead of polling for final results (Plus and above).

    PE_WEBHOOK_SECRET=... python webhook_receiver.py            # listens on PE_WEBHOOK_PORT (8787)

Create the subscription once with POST /v1/webhooks {"url": "https://<you>/webhook",
"events": ["race.result"]}; the response holds the signing secret, shown only once. Put this behind
HTTPS (a reverse proxy) before giving the API its URL.

Every delivery is checked before anything is trusted:
  * X-PuntersEdge-Signature: t=<unix seconds>,v1=<hex>, the HMAC-SHA256 of "<t>.<raw body>" with
    your secret (PE_WEBHOOK_SECRET, or PE_WEBHOOK_SECRET_PREVIOUS during a rotation), compared in
    constant time; a t more than 300 s from now is refused (replays).
  * Delivery is at-least-once: duplicates are dropped on event_id (also sent as X-PuntersEdge-Id and
    Idempotency-Key), recorded in the same SQLite store the poller uses.
  * The answer is fast: 2xx for anything verified (including events this receiver ignores), 401 for
    a bad signature, 413 for an oversized body.

race.result fires once per race when it goes final. It carries placings (and dividends where
declared) but no field status: a full finishing order, if one is coming, still needs a results poll
(tracker.py --race-id <id>).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pe_results.classify import from_webhook
from pe_results.state import Store

MAX_BODY = 65536
TOLERANCE_S = 300


def verify(header: str, body: bytes, secrets: list, now: float | None = None) -> bool:
    """True when `header` (t=..,v1=..[,v1=..]) signs `body` with one of `secrets` within tolerance."""
    if not header or not secrets:
        return False
    parts = [p.strip().split("=", 1) for p in header.split(",") if "=" in p]
    t = next((v for k, v in parts if k == "t"), None)
    sigs = [v for k, v in parts if k == "v1"]
    if not t or not t.isdigit() or not sigs:
        return False
    if abs((now if now is not None else time.time()) - int(t)) > TOLERANCE_S:
        return False
    signed = t.encode() + b"." + body
    for secret in secrets:
        mac = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        if any(hmac.compare_digest(mac, s) for s in sigs):
            return True
    return False


def handle(store: Store, headers: dict, body: bytes, secrets: list, now: float | None = None) -> tuple:
    """(status, events). Pure enough to test without a socket."""
    if len(body) > MAX_BODY:
        return 413, []
    if not verify(headers.get("x-puntersedge-signature", ""), body, secrets, now):
        return 401, []
    try:
        payload = json.loads(body)
    except ValueError:
        return 400, []
    event_id = payload.get("event_id") or headers.get("x-puntersedge-id") or headers.get("idempotency-key")
    if store.seen_delivery(event_id):
        return 200, []                                   # duplicate delivery: already handled
    if payload.get("event") != "race.result":
        return 200, []                                   # verified, but not something we track
    return 200, store.apply(from_webhook(payload))


def main() -> None:
    secrets = [s for s in (os.environ.get("PE_WEBHOOK_SECRET", ""), os.environ.get("PE_WEBHOOK_SECRET_PREVIOUS", "")) if s]
    if not secrets:
        raise SystemExit("Set PE_WEBHOOK_SECRET (returned once when you created the subscription).")
    store = Store(os.environ.get("PE_DB", "results-tracker.sqlite3"))

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):                                   # noqa: N802
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(min(n, MAX_BODY + 1))
            status, events = handle(store, {k.lower(): v for k, v in self.headers.items()}, body, secrets)
            self.send_response(status)
            self.end_headers()
            for ev in events:
                print(json.dumps(ev, default=str), flush=True)

        def log_message(self, *a):                          # quiet: never log bodies or headers
            pass

    port = int(os.environ.get("PE_WEBHOOK_PORT", "8787"))
    print(f"listening on :{port} for race.result", flush=True)
    ThreadingHTTPServer(("", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
