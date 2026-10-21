# Starter: racing odds comparison website

A small server-rendered website that compares bookmaker win prices on upcoming races, marks the
best price for each runner, says how fresh every price is, and shares **one** cached API response
between every visitor. Node 18 or later, no dependencies.

```
visitor ──> this server ──> one shared board (refreshed at most every PE_POLL_SECONDS,
                             only while someone is looking) ──> GET /v1/racing/next-to-go
```

The API key lives in this server's environment. It is never sent to the browser, put in a URL or
written to a log.

## Run it

```bash
cd starters/odds-comparison-site
cp .env.example .env          # then set PUNTERSEDGE_API_KEY (free key: https://puntersedge.online/api)
npm start                     # http://localhost:8080
npm test                      # 19 tests, no network
```

No key yet? `npm start` with the placeholder key runs in **demo mode** against the keyless sandbox
(`/v1/demo/racing/next-to-go`: a few races, the best three prices). `npm run demo` serves the
bundled **synthetic fixture** (`fixtures/next-to-go.json`, invented prices) with no network at all.
Both modes are labelled on the page.

Filters (`?category=horse|greyhound|harness&venue=<name>`) apply to the shared board, so changing
them costs nothing. `PE_COUNTRY` (AU, NZ, GB, IE, ZA) and `PE_NUM_RACES` choose what the board fetches.

## What it shows, and from which fields

| On the page | API field (`GET /v1/racing/next-to-go`) |
|---|---|
| Win price per bookmaker | `runners[].bookmakers[].win_price` (a missing or non-positive price shows as a dash) |
| Best price, with every book that offers it | the highest `win_price` per runner, computed here; ties keep all books |
| "newest price 6s old, oldest 2 min old" | `freshest_age_seconds`, `data_age_seconds` |
| "behind: pointsbetau", a "stale" label on a price | `stale_bookmakers`, `stale`, and each price's own `stale` / `age_seconds` |
| Scratched runners | `scratchings[]` (scratched runners are not in `runners`) |

States: **loading** (first fetch in progress), **empty** ("no races in the next 24 hours": Australian
racing runs roughly 00:00 to 14:00 UTC), **filtered empty**, **error** (no board yet: the API's own
message plus what to do), and **stale** (the last good board stays on screen with the time it was
fetched and why the refresh failed).

## Request limits and failure handling

* One refresh per `PE_POLL_SECONDS` (minimum 20), single-flight: 25 simultaneous visitors cause one
  upstream request (tested).
* No viewer for `PE_IDLE_SECONDS`: no refreshes, so the site spends nothing overnight.
* `If-None-Match` with the last `ETag`: an unchanged board comes back as `304` and costs 0 credits.
* Failures back off exponentially (doubling from the poll interval, capped at 10 minutes, with
  jitter) and honour `Retry-After`. A `401`, `402`, `403` or `422` stops refreshing until you fix
  the setting and restart, so a bad key or an exhausted month never burns requests in a loop.
* `GET /healthz` reports state, last fetch time and the number of upstream calls (never the key).

## Usage estimate

Each refresh is one next-to-go call. On keys issued from 22 September 2026 a response of up to 20
races costs 2 credits (more races cost more: see the API's `X-Credits-Cost` header); empty `[]`
responses and `304`s cost 0.

```
credits per month ~= 2 x (3600 / PE_POLL_SECONDS) x hours a day the page is viewed during racing x 30
```

| Poll | Viewed 14 h a day (a full Australian racing day) | Viewed 4 h a day |
|---|---|---|
| 60 s | 50,400 | 14,400 |
| 30 s | 100,800 | 28,800 |
| 20 s | 151,200 | 43,200 |

Assumptions: every refresh returns data (a quiet board answered with `304` costs less), 20 races or
fewer, the page viewed continuously in those hours. Compare with the monthly allowances on
[the pricing page](https://puntersedge.online/api/pricing?utm_source=github_examples&utm_medium=starter_odds_site);
the free allowance covers development and testing.

## Plan and licence

Any plan can call next-to-go. **Showing these prices to other people needs a plan whose licence
allows display.** The Plus licence, quoted from section 8.1 of
[the terms](https://puntersedge.online/terms#data-licence):

> You may show our odds to your own users, including your own paying subscribers, provided every
> surface that displays them carries a visible *Prices by PuntersEdge* credit linking to
> puntersedge.online. The commercial permission this carries is scoped to the product doing the
> displaying. It does not permit passing the data to a third party, or offering it as a feed, an
> export or an API of your own.

Free, Hobby and Standard are personal-use licences and do not cover showing prices to others. The
page footer carries the *Prices by PuntersEdge* credit; keep it on every surface that shows the
prices unless your plan is exempt from it (8.3). Read 8.1 in full before you launch; this README
quotes it but does not replace it.

The page carries an 18+ responsible-gambling notice. Keep one appropriate to where you publish.

## Files

| File | What it does |
|---|---|
| `server.mjs` | config from `.env`, routes (`/`, `/board`, `/healthz`, `/static/*`), security headers |
| `lib/client.mjs` | the one API call, timeouts, `ETag`, error mapping (`ApiError.fatal`) |
| `lib/cache.mjs` | the shared board: single-flight, poll interval, idle stop, backoff |
| `lib/board.mjs` | filters, bookmaker grid, best price, freshness text |
| `lib/render.mjs` | escaped HTML for the page and each state |
| `public/app.js` | re-fetches the board fragment from this server while the tab is visible |
| `fixtures/next-to-go.json` | SYNTHETIC fixture: fictional runners, invented prices |

## Verified, and not

* Verified: the 19 tests (board maths, cache behaviour, client error mapping, rendering of every
  state, the fixture against the live schema in `../contract/openapi-subset.json`, no key-like
  strings in the project); a live run in demo mode against the keyless sandbox on 22 Oct 2026.
* Not verified live: an authenticated run with a real key (the shape is the same `next-to-go`
  array, checked against the published schema, but no authenticated request was made when this
  starter was written).
