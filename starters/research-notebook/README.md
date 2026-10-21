# Starter: racing research notebook

A Jupyter notebook that pulls one day of Australian racing from the PuntersEdge API, joins every
bookmaker's opening and closing win price to the official result **on the API's own race
identifier**, reports exactly what did not join, and describes the result: price movement by
finishing position, bookmakers' closing market percentages, and who held the best closing price.

It is descriptive. Nothing here predicts results or claims that a way of betting makes money.

## Run it

```bash
cd starters/research-notebook
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export PUNTERSEDGE_API_KEY=...          # or PE_USE_FIXTURES=1 to run on synthetic data
jupyter lab research.ipynb
```

Tests (no network, no key): `pip install -r requirements-dev.txt && pytest -q` (22 tests, including
running the notebook top to bottom on the fixtures).

Settings (environment variables, see `.env.example`): `PE_SAMPLE_DATE` (default: yesterday,
Australian Eastern), `PE_COUNTRY` (AU), `PE_CATEGORY` (horse, greyhound, harness or empty for all),
`PE_MAX_CALLS` (hard cap on API calls per run, default 40), `PE_USE_FIXTURES`.

## What it does

1. **Coverage** from the API itself (`/v1/racing/closing-lines/coverage`, `/v1/racing/results/coverage`),
   so the dates printed are today's, not the day this was written.
2. **Sample**: `/v1/racing/closing-lines?date=` (one row per runner per bookmaker: first and last
   captured win price, `is_closing_line`, `scratched`, the archive's `finish_position`), paged with
   `limit`/`offset`; and `/v1/racing/results?date=`, paged by `X-Limit-Applied`.
3. **Join** on `race_id`, runners on `runner_number`. Never on venue and start time: a priced race
   with no result under its race_id is **listed, not merged**. The report separates:
   matched races; priced races without a result; results without prices; scratched runners
   (excluded from movement); races that are not final (`provisional`, `not_run`); finals with
   placegetters only (`final_placings`: unplaced positions unknown); runners whose archive finish
   position disagrees with the result.
4. **Describe**: median open-to-close move by finishing position (winner / placed / unplaced);
   closing market percentage per bookmaker (only for books that priced every starter); share of
   runners where each bookmaker held the best closing price.

Example output from a fixture run: [`docs/example-output-fixture.md`](docs/example-output-fixture.md)
(**synthetic data**, labelled as such).

## Plan and cost

| Path | Plan | Calls and credits for one day |
|---|---|---|
| Closing-line archive (default) | Standard and above (Plus and above for dates beyond the rolling window Standard holds) | 2 coverage calls (1 credit each) + closing-lines pages (5 credits each, up to 5,000 rows a page; one Australian thoroughbred day is typically one to a few pages) + results pages (2 credits each, 200 races a page) |
| Every plan (automatic fallback on a plan refusal) | Free and above | 1 results call (2 credits) + price history for up to 5 races (5 credits each): about 30 credits |

A refused call (`403` on Free or Hobby for the archive) costs nothing; the notebook prints the API's
explanation and switches to the fallback. The final cell prints the calls made and the credits
charged (from `X-Credits-Cost`). Credit costs and plan gates are as published on 22 Oct 2026; the
[pricing page](https://puntersedge.online/api/pricing?utm_source=github_examples&utm_medium=starter_notebook)
is authoritative.

Licence: your own research, models and backtesting are personal use, covered by every plan
(Terms 8.1, "Personal use": *"You may use the data for yourself: your own betting decisions, your
own models, research, backtesting and dashboards you look at."*). Using the data in a business,
client work or a product you sell needs a commercial licence: read
[section 8.1](https://puntersedge.online/terms#data-licence) before you do.

## Limitations of the data

* Prices are captured, not official. Capture starts about an hour before the jump, so a "first
  captured" price is not always the market's opening price; `open_is_baseline` and
  `close_secs_to_jump` say how far to trust each series. The notebook uses only rows whose last
  price was within 300 s of the jump.
* Results are stored from the date printed in section 1; earlier races have prices but no results.
* Harness and NZ result rows do not name scratchings (`scratched=false` there means not known).
* A final result can carry placegetters only; unplaced positions are then unknown and left out.
* Unmatched races are left out, not guessed. They are listed so they can be checked against the
  [data quality page](https://puntersedge.online/data-quality?utm_source=github_examples&utm_medium=starter_notebook).
* One day is a small sample.

## Files

| File | What it does |
|---|---|
| `research.ipynb` | the notebook (committed without outputs) |
| `pe_research/client.py` | key from the environment, retries for 429/5xx with backoff and `Retry-After`, a call cap, credit tally |
| `pe_research/sample.py` | coverage, closing lines, results, and the every-plan fallback |
| `pe_research/join.py` | the race_id join and the report |
| `pe_research/analysis.py` | the three descriptive tables |
| `fixtures/*.json` | SYNTHETIC fixtures: fictional races and invented prices, built to exercise every report line |

## Verified, and not

* Verified: 22 tests (join rules and report, analysis, client retries and refusals, paging, the
  fallback, fixture field names against `../contract/openapi-subset.json`, the notebook executing
  end to end on the fixtures).
* Not verified live: an authenticated run against the API. Field names and parameters were checked
  against the live published schema on 22 Oct 2026, but no authenticated request was made when this
  starter was written.

18+ only. Gambling Help: 1800 858 858, [gamblinghelponline.org.au](https://www.gamblinghelponline.org.au/).
