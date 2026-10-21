// Server-side HTML. Everything from the API goes through esc(); the page works without JavaScript
// (the filter form is a plain GET) and public/app.js only re-fetches the board fragment.

import { CATEGORIES, ageText, filterRaces, freshness, raceGrid, scratched, venuesOf } from './board.mjs';

export function esc(v) {
  return String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

const GUIDANCE = {
  auth: 'Check PUNTERSEDGE_API_KEY in .env (the response says whether it is missing, mistyped or replaced), then restart.',
  plan: 'Your plan does not include this request. The message names the plans that do; upgrading keeps the same key.',
  credits: "This month's credits are used up. Requests resume at the reset (00:00 UTC on the 1st), or raise PE_POLL_SECONDS.",
  invalid: 'A setting sent an invalid parameter (check PE_COUNTRY and PE_NUM_RACES).',
  rate_limited: 'Too many requests a minute. The site backs off on its own.',
  server: 'A problem on the API side. The site retries with a growing delay; see https://puntersedge.online/status.',
  network: 'The API could not be reached. The site retries with a growing delay.',
};

function hhmm(ms) {
  return ms ? new Date(ms).toISOString().slice(11, 16) + ' UTC' : '';
}

export function statusBanner(snap, { mode = 'live' } = {}) {
  const parts = [];
  if (mode === 'fixture') parts.push('<p class="banner demo"><strong>Fixture data.</strong> Synthetic prices bundled with this starter for testing. Not real odds.</p>');
  if (mode === 'demo') parts.push('<p class="banner demo"><strong>Demo data.</strong> The keyless sandbox: a few races and the best three prices only. Set PUNTERSEDGE_API_KEY for every bookmaker.</p>');
  const e = snap.error;
  if (snap.state === 'stale' && e) {
    parts.push(`<p class="banner warn" role="alert">Showing prices from ${esc(hhmm(snap.fetchedAt))}. ` +
               (snap.stopped ? 'Refreshing has stopped: ' : 'The last refresh failed: ') +
               `${esc(e.message)} ${esc(GUIDANCE[e.code] || '')}</p>`);
  }
  return parts.join('\n');
}

function priceCell(p, isBest) {
  if (!p) return '<td class="none">&ndash;</td>';
  const label = isBest ? ' <span class="best-label">best</span>' : '';
  const stale = p.stale ? ' <span class="stale-label">stale</span>' : '';
  const cls = [isBest ? 'best' : '', p.stale ? 'is-stale' : ''].filter(Boolean).join(' ');
  return `<td class="${cls}" title="${esc(ageText(p.age))}">${isBest ? '<strong>' : ''}${p.price.toFixed(2)}${isBest ? '</strong>' : ''}${label}${stale}</td>`;
}

export function raceSection(race) {
  const g = raceGrid(race);
  const f = freshness(race);
  const scr = scratched(race);
  const start = esc(race.start_time || '');
  const head = `${esc(race.venue)} R${esc(race.race_number)}`;
  const rows = g.rows.map((r) => {
    const cells = g.columns.map((k) => priceCell(r.prices[k], r.bestBooks.includes(k))).join('');
    const best = r.best === null ? '&ndash;' : `${r.best.toFixed(2)} <span class="muted">${esc(r.bestBooks.join(', '))}</span>`;
    return `<tr><th scope="row">${esc(r.number ?? '')} ${esc(r.name)}</th>${cells}<td class="bestcol">${best}</td></tr>`;
  }).join('\n');
  return `<section class="race" aria-labelledby="r-${esc(race.race_id)}">
  <h2 id="r-${esc(race.race_id)}">${head} <span class="muted">${esc(race.category || '')}</span></h2>
  <p class="meta">Starts <time datetime="${start}">${start.replace('T', ' ').slice(0, 16)} UTC</time> &middot; ${esc(f.text)}${f.stale ? ' <span class="stale-label">some prices are behind</span>' : ''}</p>
  ${scr.length ? `<p class="meta">Scratched: ${esc(scr.map((s) => `${s.number ?? ''} ${s.name}`.trim()).join(', '))}</p>` : ''}
  <div class="scroll"><table>
    <caption class="sr-only">Win prices for ${head} by bookmaker; the best price per runner is labelled best.</caption>
    <thead><tr><th scope="col">Runner</th>${g.columns.map((k) => `<th scope="col">${esc(k)}</th>`).join('')}<th scope="col">Best</th></tr></thead>
    <tbody>${rows || '<tr><td>No runners priced yet.</td></tr>'}</tbody>
  </table></div>
</section>`;
}

export function boardFragment(snap, filters, { country = 'AU', mode = 'live' } = {}) {
  const banner = statusBanner(snap, { mode });
  if (snap.state === 'loading') {
    return `${banner}<p class="state" role="status">Loading prices&hellip;</p>`;
  }
  if (snap.state === 'error') {
    const e = snap.error || {};
    return `${banner}<div class="state error" role="alert"><p><strong>Prices are unavailable right now.</strong> ${esc(e.message || '')}</p><p>${esc(GUIDANCE[e.code] || '')}</p></div>`;
  }
  const races = filterRaces(snap.races, filters);
  if (!snap.races.length) {
    return `${banner}<p class="state" role="status">No ${esc(country)} races in the next 24 hours. Australian racing runs roughly 00:00 to 14:00 UTC; check back then.</p>`;
  }
  if (!races.length) {
    return `${banner}<p class="state" role="status">No races match these filters. <a href="/">Show all races</a>.</p>`;
  }
  const updated = snap.fetchedAt ? `<p class="meta" id="updated">Board refreshed ${esc(hhmm(snap.fetchedAt))}; each price shows its own age.</p>` : '';
  return `${banner}${updated}\n${races.map(raceSection).join('\n')}`;
}

export function page(snap, filters, { country = 'AU', mode = 'live', refreshSeconds = 60 } = {}) {
  const venues = venuesOf(snap.races);
  const opt = (v, cur, label) => `<option value="${esc(v)}"${v === cur ? ' selected' : ''}>${esc(label ?? v)}</option>`;
  return `<!doctype html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Racing odds comparison</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<a class="skip" href="#board">Skip to the odds</a>
<header>
  <h1>Racing odds comparison</h1>
  <form method="get" action="/" class="filters">
    <label>Code <select name="category">${opt('', filters.category, 'All')}${CATEGORIES.map((c) => opt(c, filters.category)).join('')}</select></label>
    <label>Venue <select name="venue">${opt('', filters.venue, 'All venues')}${venues.map((v) => opt(v, filters.venue)).join('')}</select></label>
    <button type="submit">Show</button>
  </form>
</header>
<main id="board" aria-live="polite" data-refresh="${esc(refreshSeconds)}">
${boardFragment(snap, filters, { country, mode })}
</main>
<footer>
  <p class="credit">Prices by <a href="https://puntersedge.online/?utm_source=github_examples&amp;utm_medium=starter_odds_site">PuntersEdge</a></p>
  <p>18+ only. Gamble responsibly. Gambling Help: <a href="tel:1800858858">1800 858 858</a>, <a href="https://www.gamblinghelponline.org.au/">gamblinghelponline.org.au</a>.</p>
</footer>
<script src="/static/app.js" defer></script>
</body>
</html>`;
}
