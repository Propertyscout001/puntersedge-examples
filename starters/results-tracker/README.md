# Starter: results tracker

Follows chosen races until their results are final, and until the full finishing order is in or
known not to be coming, and prints each change **once**. It tells interim placings from final ones,
final placings from a complete field, and "the source is refusing" from "there is no result". Python
3.9 or later, one dependency (`requests`).

```bash
cd starters/results-tracker
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
export PUNTERSEDGE_API_KEY=...

python tracker.py --date 2026-10-24 --venue Flemington              # every race at a meeting
python tracker.py --date 2026-10-24 --country AU --category greyhound
python tracker.py --date 2026-10-24 --race-id <id> --race-id <id>   # specific races
python tracker.py --replay fixtures/ --venue "Fixture Park"         # offline, synthetic data
```

Tests: `pip install -r requirements-dev.txt && pytest -q` (21 tests, no network).

Every change is one JSON line on stdout. Example from the offline replay (**synthetic fixtures**):
[`docs/example-output-replay.jsonl`](docs/example-output-replay.jsonl).

## What it reports

| Event | Meaning (from the result row's fields) |
|---|---|
| `result_interim` / `placings_changed` | `status: interim`: placings published, can still change. Do not settle on these. |
| `result_final` | `status: final` (placings stable for 30 minutes). Settle on this. |
| `dividends_declared` / `exotics_declared` | `dividends.straight` / `dividends.exotics` appeared; exotics follow the placings by a few minutes |
| `full_field_complete` | `completeness.state: complete_full_field`: every runner's finish is in `runners` |
| `field_source_unavailable` | `completeness.source_refused_since` set, or `field_status: unavailable`: the full field's source is refusing us. **The placings and dividends are still final.** |
| `no_full_field_source` | `field_status: unsupported` / `not_applicable`: no supported source publishes this code's full field |
| `full_field_not_coming` | the collector stopped retrying (`completeness.retrying: false`) without a full field |
| `race_not_run` | `status: abandoned` / `completeness.state: not_run` (abandoned, postponed, transferred): a void, not a result |
| `result_without_race_id` | a result row whose `race_id` is null: reported, **never matched to a race by venue and number** |

Rows from before `completeness` existed (20 Oct 2026) are classified from `status` and
`field_status`; fields the API adds later are ignored, never an error.

## Polling, retries, de-duplication

* Races are selected with `GET /v1/racing/events?date=&country=&category=` (1 credit), filtered to
  the venue here (events takes no venue parameter), or from the race ids you give.
* Each cycle is one `GET /v1/racing/results?date=&venue=&country=&category=` (2 credits a page of up
  to 200 races; paged by `X-Limit-Applied`), every `--interval` seconds (default 120, floor 60).
* It stops when every tracked race has nothing more to come, when `--max-requests` is spent (default
  300), or after `--max-hours` (default 8).
* Retries only what retrying can fix: `429` (honouring `Retry-After`), `5xx` and network errors, with
  exponential backoff and jitter. `401`, `402`, `403` and `422` stop the run with the API's own
  explanation and what to do. Every request is a GET, so a retry can never double anything.
* State (which races are tracked, their phase, and every event already reported) lives in SQLite
  (`PE_DB`). Events are keyed on race, kind and content: re-polling the same data, a retried request,
  a duplicate webhook delivery or a restart reports nothing twice. A race never moves backwards.

## Webhooks instead of polling for "final" (Plus and above)

`webhook_receiver.py` accepts `race.result` deliveries, which fire once per race when it goes final.
It verifies `X-PuntersEdge-Signature: t=<unix seconds>,v1=<hex>` (HMAC-SHA256 of `<t>.<raw body>`
with your subscription secret; the previous secret is accepted during a rotation), refuses a
timestamp more than 300 s old, drops duplicate deliveries on `event_id`, and feeds the same state
store. The webhook carries placings and dividends but no field status, so for a full finishing order
keep polling those races (`tracker.py --race-id`). Put the receiver behind HTTPS before registering it.

## Usage estimate

```
credits ~= 1 (selection) + 2 x pages per poll x polls
polls   ~= (from the first race until the last race is final, plus the time a full field takes) / interval
```

* One meeting of 10 races over about 4 hours, polling every 120 s until results are final: about
  120 polls, roughly **240 credits**.
* Waiting for full fields as well: AU thoroughbred fields can take hours after the race
  (`completeness.field_due_by` says when); the 8-hour cap bounds it at about **480 credits** a meeting.
* A whole day across a country (`--country AU`, no venue): one or two pages a poll, so 2-4 credits
  a poll.

Assumptions: results come one page per poll at a single venue; refused calls cost nothing. Compare
with the allowances on [the pricing page](https://puntersedge.online/api/pricing?utm_source=github_examples&utm_medium=starter_results_tracker).
Credit costs are as published on 22 Oct 2026; the API's `X-Credits-Cost` header is authoritative,
and the tracker prints its own tally at the end.

## Plans and licence

* Results and events: every plan, Free included.
* `race.result` webhooks: Plus and above (`GET /v1/webhooks` stays readable on any plan; creating one
  needs Plus).
* Licence (Terms 8.1): following results for your own betting and research is personal use, on every
  plan (*"You may use the data for yourself: your own betting decisions, your own models, research,
  backtesting and dashboards you look at."*). For any use inside a business or in front of other
  people, read [section 8.1](https://puntersedge.online/terms#data-licence) and choose the rung that
  matches: it is the authority, not this README.

## Coverage notes

* Victorian greyhound full fields: the source has refused our collector since 13 Oct 2026, so those
  races report `field_source_unavailable`; their placings and dividends are unaffected.
* Some codes and countries have no full-field source (`no_full_field_source`).
* The [status page](https://puntersedge.online/status) and `/v1/racing/results/coverage` say which
  lanes are complete today.

## Verified, and not

* Verified: 21 tests (every phase, de-duplication across re-polls and restarts, no backwards moves,
  retries with `Retry-After`, fatal refusals, the request budget, the 60 s floor, webhook
  signatures, replays, tampering, duplicates and rotation, fixture field names against
  `../contract/openapi-subset.json`), and the offline replay end to end.
* Not verified live: an authenticated poll or a real webhook delivery. Field names and parameters
  were checked against the live published schema on 22 Oct 2026, but no authenticated request was
  made when this starter was written.

18+ only. Gambling Help: 1800 858 858, [gamblinghelponline.org.au](https://www.gamblinghelponline.org.au/).
