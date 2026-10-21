# Starter projects

| starter | for | runs without a key? |
|---|---|---|
| [odds-comparison-site](odds-comparison-site) | showing bookmaker prices to users | yes: demo mode (keyless sandbox) or `npm run demo` (fixture) |
| [research-notebook](research-notebook) | a personal model or research tool | yes: `PE_USE_FIXTURES=1` (synthetic fixture) |
| [results-tracker](results-tracker) | feeding results into your own systems | yes: `python tracker.py --replay fixtures/` (synthetic fixture) |

Every starter reads the key from `PUNTERSEDGE_API_KEY` (server side only), ships a `.env.example`
with placeholders, handles the API's refusals (`401`, `402`, `403`, `422`) without retrying them,
retries `429` and `5xx` with backoff, caps its own request volume, and labels fixture data as such.

`contract/openapi-subset.json` is the part of the live schema the starters depend on; each starter's
tests check its fixtures against it. Refresh it with `python3 contract/refresh.py` (reads the public
`https://api.puntersedge.online/openapi.json`, no key).
