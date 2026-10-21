// Odds comparison website starter. Run: cp .env.example .env, set the key, npm start.
//
// Request flow: visitor -> this server -> SharedBoard (one copy for everyone) -> PuntersEdge, at
// most once per PE_POLL_SECONDS and only while someone is looking. The key stays in this process.

import { readFileSync, existsSync } from 'node:fs';
import { createServer } from 'node:http';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { SharedBoard } from './lib/cache.mjs';
import { fetchDemo, fetchNextToGo } from './lib/client.mjs';
import { CATEGORIES } from './lib/board.mjs';
import { boardFragment, page } from './lib/render.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));

export function loadEnv(file = join(HERE, '.env')) {
  if (!existsSync(file)) return;
  for (const line of readFileSync(file, 'utf8').split('\n')) {
    const m = /^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/.exec(line);
    if (m && !line.trim().startsWith('#') && process.env[m[1]] === undefined) process.env[m[1]] = m[2];
  }
}

export function config(env = process.env) {
  const key = (env.PUNTERSEDGE_API_KEY || '').trim();
  const fixtures = env.PE_FIXTURES === '1';
  const placeholder = !key || key === 'replace-with-your-key';
  return {
    apiKey: placeholder ? '' : key,
    mode: fixtures ? 'fixture' : (placeholder ? 'demo' : 'live'),
    country: /^[A-Z]{2}$/.test(env.PE_COUNTRY || '') ? env.PE_COUNTRY : 'AU',
    numRaces: Math.min(200, Math.max(1, parseInt(env.PE_NUM_RACES || '20', 10) || 20)),
    pollSeconds: Math.max(20, parseInt(env.PE_POLL_SECONDS || '60', 10) || 60),
    idleSeconds: Math.max(60, parseInt(env.PE_IDLE_SECONDS || '600', 10) || 600),
    port: parseInt(env.PORT || '8080', 10) || 8080,
  };
}

export function loaderFor(cfg, { fetchImpl = fetch } = {}) {
  if (cfg.mode === 'fixture') {
    const fx = JSON.parse(readFileSync(join(HERE, 'fixtures', 'next-to-go.json'), 'utf8'));
    return async () => ({ races: fx.races, etag: null });
  }
  if (cfg.mode === 'demo') return async () => fetchDemo({ fetchImpl });
  return async ({ etag }) => fetchNextToGo({ apiKey: cfg.apiKey, country: cfg.country, numRaces: cfg.numRaces,
                                              etag, fetchImpl });
}

export function filtersFrom(url) {
  const c = url.searchParams.get('category') || '';
  const v = (url.searchParams.get('venue') || '').slice(0, 60);
  return { category: CATEGORIES.includes(c) ? c : '', venue: v };
}

const STATIC = {
  '/static/app.js': ['application/javascript; charset=utf-8', join(HERE, 'public', 'app.js')],
  '/static/style.css': ['text/css; charset=utf-8', join(HERE, 'public', 'style.css')],
};
const HEADERS = {
  'Content-Security-Policy': "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'",
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
};

export function makeServer(cfg, board) {
  return createServer(async (req, res) => {
    const url = new URL(req.url, 'http://localhost');
    const send = (status, type, body, extra = {}) => {
      res.writeHead(status, { 'Content-Type': type, ...HEADERS, ...extra });
      res.end(body);
    };
    try {
      if (req.method !== 'GET' && req.method !== 'HEAD') return send(405, 'text/plain', 'Method not allowed');
      if (STATIC[url.pathname]) {
        const [type, file] = STATIC[url.pathname];
        return send(200, type, readFileSync(file), { 'Cache-Control': 'public, max-age=300' });
      }
      if (url.pathname === '/healthz') {
        const s = board.snapshot();
        return send(200, 'application/json', JSON.stringify({ state: s.state, fetched_at: s.fetchedAt,
          stopped: s.stopped, upstream_calls: board.upstreamCalls, mode: cfg.mode }));
      }
      const filters = filtersFrom(url);
      const opts = { country: cfg.country, mode: cfg.mode, refreshSeconds: cfg.pollSeconds };
      if (url.pathname === '/board') {
        const snap = await board.view({ wait: false });
        return send(200, 'text/html; charset=utf-8', boardFragment(snap, filters, opts), { 'Cache-Control': 'no-store' });
      }
      if (url.pathname === '/') {
        const snap = await board.view({ wait: true });
        return send(200, 'text/html; charset=utf-8', page(snap, filters, opts), { 'Cache-Control': 'no-store' });
      }
      return send(404, 'text/plain', 'Not found');
    } catch (e) {
      return send(500, 'text/plain', 'Something went wrong rendering the page.');
    }
  });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  loadEnv();
  const cfg = config();
  const board = new SharedBoard({ load: loaderFor(cfg), pollSeconds: cfg.pollSeconds, idleSeconds: cfg.idleSeconds });
  setInterval(() => { board.tick().catch(() => {}); }, 5000).unref();
  makeServer(cfg, board).listen(cfg.port, () => {
    console.log(`odds site on http://localhost:${cfg.port} (${cfg.mode} mode, ${cfg.country}, refresh every ${cfg.pollSeconds}s while viewed)`);
  });
}
