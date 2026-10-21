// npm test  (node --test test/*.test.mjs; no dependencies)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { filterRaces, raceGrid, freshness, venuesOf, ageText } from '../lib/board.mjs';
import { SharedBoard } from '../lib/cache.mjs';
import { ApiError, fetchNextToGo } from '../lib/client.mjs';
import { boardFragment, esc, page } from '../lib/render.mjs';
import { config, filtersFrom, loaderFor, makeServer } from '../server.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..');
const FX = JSON.parse(readFileSync(join(ROOT, 'fixtures', 'next-to-go.json'), 'utf8'));
const CONTRACT = JSON.parse(readFileSync(join(ROOT, '..', 'contract', 'openapi-subset.json'), 'utf8'));

// ── board ──────────────────────────────────────────────────────────────────────────────────
test('best price is the highest win price, ties keep every book', () => {
  const g = raceGrid(FX.races[0]);
  const alpha = g.rows.find((r) => r.number === 1);
  assert.equal(alpha.best, 3.8);
  assert.deepEqual(alpha.bestBooks, ['ladbrokes_au', 'sportsbet']);
  assert.deepEqual(g.columns, ['ladbrokes_au', 'pointsbetau', 'sportsbet', 'tab']);
});

test('a runner with no prices has no best price, not a zero', () => {
  const delta = raceGrid(FX.races[0]).rows.find((r) => r.number === 4);
  assert.equal(delta.best, null);
  assert.equal(delta.quotes, 0);
});

test('freshness comes from the API fields, stale books named', () => {
  const f = freshness(FX.races[0]);
  assert.equal(f.oldest, 95);
  assert.equal(f.stale, true);
  assert.deepEqual(f.staleBooks, ['pointsbetau']);
  assert.match(f.text, /newest price 6s old, oldest 2 min old; behind: pointsbetau/);
  assert.equal(ageText(null), 'age unknown');
});

test('filters by code and venue (case-insensitive), venues listed once', () => {
  assert.equal(filterRaces(FX.races, { category: 'greyhound' }).length, 1);
  assert.equal(filterRaces(FX.races, { venue: 'flemington' }).length, 1);
  assert.deepEqual(venuesOf(FX.races), ['Flemington', 'Menangle', 'Sandown Park']);
});

// ── shared cache ───────────────────────────────────────────────────────────────────────────
function clock(start = 1_000_000) {
  let t = start;
  return { now: () => t, advance: (ms) => { t += ms; } };
}

test('one upstream call for many simultaneous visitors (single-flight)', async () => {
  let calls = 0;
  const b = new SharedBoard({ load: async () => { calls += 1; await new Promise((r) => setTimeout(r, 20)); return { races: FX.races }; } });
  await Promise.all(Array.from({ length: 25 }, () => b.view()));
  assert.equal(calls, 1);
  await b.view();
  assert.equal(calls, 1, 'inside the poll interval nobody triggers another call');
});

test('refreshes at most once per poll interval and stops when nobody is looking', async () => {
  const c = clock();
  let calls = 0;
  const b = new SharedBoard({ load: async () => { calls += 1; return { races: FX.races }; }, pollSeconds: 60, idleSeconds: 120, now: c.now });
  await b.view();
  c.advance(30_000); await b.tick(); assert.equal(calls, 1);
  c.advance(31_000); await b.tick(); assert.equal(calls, 2);
  c.advance(200_000); await b.tick(); assert.equal(calls, 2, 'idle: no visitor for 200 s, no credits spent');
});

test('a 304 keeps the board and costs nothing new', async () => {
  const c = clock();
  const seen = [];
  let n = 0;
  const b = new SharedBoard({ now: c.now, pollSeconds: 20, load: async ({ etag }) => { seen.push(etag); n += 1; return n === 1 ? { races: FX.races, etag: 'W/"abc"' } : { notModified: true }; } });
  await b.view();
  c.advance(21_000); await b.view(); await b.inflight;
  assert.deepEqual(seen, [null, 'W/"abc"']);
  assert.equal(b.snapshot().races.length, 3);
  assert.equal(b.snapshot().state, 'fresh');
});

test('an error keeps the last good board, marks it stale and backs off', async () => {
  const c = clock();
  let fail = false;
  const b = new SharedBoard({ now: c.now, pollSeconds: 60, load: async () => { if (fail) throw new ApiError(503, 'upstream', { code: 'server' }); return { races: FX.races }; } });
  await b.view();
  fail = true;
  c.advance(61_000); await b.view(); await b.inflight;
  const s = b.snapshot();
  assert.equal(s.state, 'stale');
  assert.equal(s.races.length, 3);
  assert.ok(b.nextAllowedAt - c.now() >= 60_000, 'backed off at least one interval');
  c.advance(70_000); await b.tick();          // past the first backoff and its jitter (<= 10%)
  assert.ok(b.nextAllowedAt - c.now() >= 120_000, 'second failure doubles the wait');
});

test('Retry-After is honoured', async () => {
  const c = clock();
  const b = new SharedBoard({ now: c.now, pollSeconds: 20, load: async () => { throw new ApiError(429, 'slow down', { code: 'rate_limited', retryAfter: 300 }); } });
  await b.view();
  assert.ok(b.nextAllowedAt - c.now() >= 300_000);
});

test('a bad key stops refreshing instead of burning requests', async () => {
  const c = clock();
  let calls = 0;
  const b = new SharedBoard({ now: c.now, load: async () => { calls += 1; throw new ApiError(401, 'Invalid API key.', { code: 'auth' }); } });
  await b.view();
  c.advance(10 * 60_000); await b.tick(); await b.view();
  assert.equal(calls, 1);
  assert.equal(b.snapshot().stopped, true);
  assert.equal(b.snapshot().state, 'error');
});

// ── client ─────────────────────────────────────────────────────────────────────────────────
function fakeFetch(status, body, headers = {}) {
  return async (url, init) => {
    fakeFetch.last = { url, init };
    return new Response(body === null ? null : JSON.stringify(body), { status, headers: { 'content-type': 'application/json', ...headers } });
  };
}

test('client sends the key in a header, never the URL, and maps refusals', async () => {
  const f = fakeFetch(200, FX.races, { etag: 'W/"1"', 'x-credits-cost': '2' });
  const out = await fetchNextToGo({ apiKey: 'k-123', country: 'AU', numRaces: 20, fetchImpl: f });
  assert.equal(out.races.length, 3);
  assert.equal(fakeFetch.last.init.headers['X-API-Key'], 'k-123');
  assert.ok(!fakeFetch.last.url.includes('k-123'));
  assert.match(fakeFetch.last.url, /country=AU/);
  for (const [status, code, fatal] of [[401, 'auth', true], [402, 'credits', true], [403, 'plan', true],
                                       [422, 'invalid', true], [429, 'rate_limited', false], [503, 'server', false]]) {
    await assert.rejects(fetchNextToGo({ apiKey: 'k', numRaces: 1, fetchImpl: fakeFetch(status, { detail: `msg ${status}` }, { 'retry-after': '7' }) }),
      (e) => e.status === status && e.code === code && e.fatal === fatal && e.message === `msg ${status}`);
  }
});

test('a 304 is reported as not modified', async () => {
  const out = await fetchNextToGo({ apiKey: 'k', numRaces: 1, etag: 'W/"1"', fetchImpl: fakeFetch(304, null) });
  assert.deepEqual(out, { notModified: true });
});

// ── render ─────────────────────────────────────────────────────────────────────────────────
const snap = (over = {}) => ({ state: 'fresh', races: FX.races, fetchedAt: Date.UTC(2026, 9, 24, 3, 0), error: null, stopped: false, ...over });

test('page carries the attribution, the 18+ notice, labelled best prices and escapes API text', () => {
  const evil = structuredClone(FX.races);
  evil[0].venue = '<script>alert(1)</script>';
  const html = page(snap({ races: evil }), { category: '', venue: '' });
  assert.match(html, /Prices by <a href="https:\/\/puntersedge\.online\//);
  assert.match(html, /18\+ only/);
  assert.match(html, /<span class="best-label">best<\/span>/);
  assert.ok(!html.includes('<script>alert(1)</script>'));
  assert.ok(html.includes(esc('<script>alert(1)</script>')));
});

test('loading, empty, filtered-empty, error and stale states all say something useful', () => {
  assert.match(boardFragment(snap({ state: 'loading', races: [] }), {}), /Loading prices/);
  assert.match(boardFragment(snap({ state: 'empty', races: [] }), {}), /No AU races in the next 24 hours/);
  assert.match(boardFragment(snap(), { category: 'harness', venue: 'Flemington' }), /No races match these filters/);
  const err = new ApiError(401, 'Invalid API key.', { code: 'auth' });
  assert.match(boardFragment(snap({ state: 'error', races: [], error: err }), {}), /Prices are unavailable right now\..*Invalid API key/s);
  const stale = boardFragment(snap({ state: 'stale', error: new ApiError(503, 'upstream', { code: 'server' }) }), {});
  assert.match(stale, /Showing prices from 03:00 UTC\. The last refresh failed: upstream/);
});

test('fixture and demo modes are labelled as such', () => {
  assert.match(boardFragment(snap(), {}, { mode: 'fixture' }), /Fixture data\./);
  assert.match(boardFragment(snap(), {}, { mode: 'demo' }), /Demo data\./);
});

// ── config and server ──────────────────────────────────────────────────────────────────────
test('config: placeholder key means demo mode; bounds are enforced', () => {
  assert.equal(config({ PUNTERSEDGE_API_KEY: 'replace-with-your-key' }).mode, 'demo');
  assert.equal(config({ PUNTERSEDGE_API_KEY: 'abc', PE_POLL_SECONDS: '1' }).pollSeconds, 20);
  assert.equal(config({ PE_FIXTURES: '1' }).mode, 'fixture');
  assert.equal(config({ PE_COUNTRY: 'au; drop' }).country, 'AU');
  assert.deepEqual(filtersFrom(new URL('http://x/?category=<x>&venue=Flemington')), { category: '', venue: 'Flemington' });
});

test('server serves the page and fragment in fixture mode without a key', async () => {
  const cfg = config({ PE_FIXTURES: '1' });
  const board = new SharedBoard({ load: loaderFor(cfg) });
  const srv = makeServer(cfg, board).listen(0);
  const port = srv.address().port;
  try {
    const html = await (await fetch(`http://127.0.0.1:${port}/?category=greyhound`)).text();
    assert.match(html, /Sandown Park/);
    assert.ok(!html.includes('Flemington R4 <span'), 'filtered out');
    const res = await fetch(`http://127.0.0.1:${port}/board`);
    assert.equal(res.headers.get('content-security-policy').startsWith("default-src 'self'"), true);
    const health = await (await fetch(`http://127.0.0.1:${port}/healthz`)).json();
    assert.equal(health.upstream_calls, 1);
  } finally {
    srv.close();
  }
});

// ── contract and secrets ───────────────────────────────────────────────────────────────────
test('fixture fields are a subset of the live schema (contract/openapi-subset.json)', () => {
  const c = CONTRACT.paths['/v1/racing/next-to-go'];
  for (const race of FX.races) {
    for (const k of Object.keys(race)) assert.ok(c.fields.includes(k), `race.${k} not in the schema`);
    for (const r of race.runners) {
      for (const k of Object.keys(r)) assert.ok(c.nested['runners'].includes(k), `runner.${k}`);
      for (const b of r.bookmakers) for (const k of Object.keys(b)) {
        assert.ok(c.nested['runners[].bookmakers'].includes(k) || k === 'refresh_tier', `bookmaker.${k}`);
      }
    }
  }
  for (const q of ['country', 'num_races', 'include_unresolved']) assert.ok(c.query.includes(q), q);
});

test('no key-like string anywhere in the project, and .env is ignored', () => {
  const files = [];
  const walk = (d) => { for (const n of readdirSync(d, { withFileTypes: true })) { if (n.name === 'node_modules') continue; const p = join(d, n.name); n.isDirectory() ? walk(p) : files.push(p); } };
  walk(ROOT);
  for (const f of files) {
    const s = readFileSync(f, 'utf8');
    assert.ok(!/\bpe_[0-9a-f]{20,}\b/.test(s), f);
    assert.ok(!/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/.test(s), f);
  }
  assert.match(readFileSync(join(ROOT, '.gitignore'), 'utf8'), /^\.env$/m);
  assert.match(readFileSync(join(ROOT, '.env.example'), 'utf8'), /PUNTERSEDGE_API_KEY=replace-with-your-key/);
});
