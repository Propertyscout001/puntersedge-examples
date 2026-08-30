<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/logo-dark.svg">
  <img alt="PuntersEdge API" src="docs/logo-light.svg" width="400">
</picture>

# PuntersEdge API examples — Australian racing & sports odds in Python

Six small, runnable scripts against the [PuntersEdge Odds API](https://puntersedge.online/api?utm_source=github_examples&utm_medium=cookbook_readme):
live win/place prices for Australian horse, greyhound and harness racing across
[14 bookmakers, measured live](https://puntersedge.online/coverage-report.json), plus
head-to-head sports odds.

Each script is standalone — read it top to bottom, run it, adapt it. No framework,
no shared helpers, no magic.

## Run something in 30 seconds (no key needed)

```
git clone https://github.com/Propertyscout001/puntersedge-examples
cd puntersedge-examples
pip install -r requirements.txt
python examples/01_next_to_go.py
```

Without a key, scripts 01 and 06 hit the keyless demo sandbox (real data, truncated).
For the full feed, [grab a free key](https://puntersedge.online/api?utm_source=github_examples&utm_medium=cookbook_readme#signup)
— 1,500 credits/month, no card — and:

```
export PUNTERSEDGE_API_KEY=your_key_here
```

## The examples

| script | what it shows | endpoint | credits/call* |
|---|---|---|---|
| [01_next_to_go.py](examples/01_next_to_go.py) | upcoming races, favourite per race | `/v1/racing/next-to-go` | 2 |
| [02_best_odds_board.py](examples/02_best_odds_board.py) | best win/place price per runner across books | `/v1/racing/best-odds` | 3 |
| [03_movers.py](examples/03_movers.py) | firmers and drifters before the jump | `/v1/racing/movers` | 3 |
| [04_results_to_csv.py](examples/04_results_to_csv.py) | settled results → CSV | `/v1/racing/results` | 2 |
| [05_price_history_to_csv.py](examples/05_price_history_to_csv.py) | open/close/high/low per runner-book → CSV | `/v1/racing/price-history` | 5 |
| [06_sports_best_odds.py](examples/06_sports_best_odds.py) | best head-to-head price per team (NRL, AFL, …) | `/v1/best-odds/{sport}` | 3 |

\* measured against production on 2026-08-30. Your `/v1/usage` endpoint and the
`X-Credits-*` response headers always show the live numbers.

## Credit budgeting, honestly

The free tier is 1,500 credits/month. That is roughly **750 next-to-go calls** —
hourly polling all month with room to spare — but it is *not* enough for a
60-second live scanner (that's ~86,000 credits/month; the Standard plan's 75,000
credits at A$29/mo is built for that shape). Poll at the cadence your use case
actually needs, not the fastest one that works.

01 and 06 use only the Python standard library in demo mode; the keyed paths use the
official [`puntersedge` SDK](https://github.com/Propertyscout001/puntersedge-python)
(`pip install puntersedge`). 03–05 deliberately use plain `requests` so you can see
the raw REST calls — everything here ports directly to any language.

For arbitrage scanning specifically, don't reinvent it from these examples: the SDK
ships a `puntersedge.arb` toolkit with the freshness/coverage gates that make naive
scanners misfire, and a `puntersedge-arb` CLI.

## Notes

- Docs: [api.puntersedge.online/docs](https://api.puntersedge.online/docs) ·
  [OpenAPI](https://api.puntersedge.online/openapi.json)
- Coverage is measured, not promised: [coverage-report.json](https://puntersedge.online/coverage-report.json)
  is recomputed from the production ingest store over a trailing 7-day window.
- Odds data is for research and tooling. **Nothing here is betting advice, and no
  strategy shown is a claim that it makes money.**
- 18+. Gamble responsibly — in Australia: 1800 858 858, [gamblinghelponline.org.au](https://www.gamblinghelponline.org.au).

MIT licensed — use it in anything.
