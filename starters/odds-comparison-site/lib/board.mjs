// Turn the API's next-to-go races into what the page shows: filters, a bookmaker grid per race,
// the best price per runner, and how fresh each price is, all from fields the API sends.
//
// Freshness fields read (GET /v1/racing/next-to-go):
//   race.data_age_seconds        age of the OLDEST price on the race
//   race.freshest_age_seconds    age of the newest
//   race.stale / stale_bookmakers   the API's own judgement of which books are behind
//   bookmaker.age_seconds / .stale  per price
// Scratched runners are not in `runners`; they arrive separately in `race.scratchings`.

export const CATEGORIES = ['horse', 'greyhound', 'harness'];

export function filterRaces(races, { category = '', venue = '' } = {}) {
  const v = venue.trim().toLowerCase();
  return races.filter((r) => (!category || r.category === category) &&
                             (!v || String(r.venue || '').toLowerCase() === v));
}

export function venuesOf(races) {
  return [...new Set(races.map((r) => r.venue).filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

function priceOk(p) {
  return typeof p === 'number' && Number.isFinite(p) && p > 1;
}

/** { columns: [book keys], rows: [{number, name, prices: {key: {price, age, stale}}, best, bestBooks}] } */
export function raceGrid(race) {
  const columns = new Set();
  const rows = (race.runners || []).map((runner) => {
    const prices = {};
    for (const b of runner.bookmakers || []) {
      if (!b || !b.key) continue;
      columns.add(b.key);
      if (priceOk(b.win_price)) {
        prices[b.key] = { price: b.win_price, age: b.age_seconds ?? null, stale: !!b.stale };
      }
    }
    const vals = Object.values(prices).map((x) => x.price);
    const best = vals.length ? Math.max(...vals) : null;
    const bestBooks = best === null ? [] : Object.keys(prices).filter((k) => prices[k].price === best).sort();
    return { number: runner.number ?? null, name: runner.name || '', prices, best, bestBooks,
             quotes: vals.length };
  });
  rows.sort((a, b) => (a.number ?? 999) - (b.number ?? 999));
  return { columns: [...columns].sort(), rows };
}

export function ageText(seconds) {
  if (seconds === null || seconds === undefined || !Number.isFinite(Number(seconds))) return 'age unknown';
  const s = Math.max(0, Math.round(Number(seconds)));
  if (s < 90) return `${s}s old`;
  if (s < 5400) return `${Math.round(s / 60)} min old`;
  return `${Math.round(s / 3600)} h old`;
}

/** One line per race: how old its prices are, in the API's words. */
export function freshness(race) {
  const stale = Array.isArray(race.stale_bookmakers) ? race.stale_bookmakers : [];
  return {
    oldest: race.data_age_seconds ?? null,
    newest: race.freshest_age_seconds ?? null,
    stale: !!race.stale,
    staleBooks: stale,
    text: (race.freshest_age_seconds != null ? `newest price ${ageText(race.freshest_age_seconds)}, ` : '') +
          `oldest ${ageText(race.data_age_seconds)}` +
          (stale.length ? `; behind: ${stale.join(', ')}` : ''),
  };
}

export function scratched(race) {
  return (race.scratchings || []).map((s) => ({ number: s.number ?? null, name: s.name || '' }));
}
