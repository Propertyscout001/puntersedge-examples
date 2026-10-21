// PuntersEdge API client for the odds site: server-side only, one endpoint, explicit errors.
//
// The key is read from the environment by the caller and sent in X-API-Key. It never goes to the
// browser, into a URL, or into a log line. Every refusal the API sends has a body that explains it;
// we keep that message so the page can show something useful.

export const API_BASE = 'https://api.puntersedge.online';
export const USER_AGENT = 'puntersedge-starter-odds-site/1.0';

export class ApiError extends Error {
  constructor(status, message, { retryAfter = null, code = null } = {}) {
    super(message);
    this.status = status;          // HTTP status, or 0 for a network failure / timeout
    this.retryAfter = retryAfter;  // seconds, from Retry-After on a 429
    this.code = code;              // auth | plan | credits | invalid | rate_limited | server | network
  }
  get fatal() {
    // Retrying will not fix these: the key, the plan or the month's credits has to change first.
    return this.code === 'auth' || this.code === 'plan' || this.code === 'credits' || this.code === 'invalid';
  }
}

const CODE = { 401: 'auth', 402: 'credits', 403: 'plan', 422: 'invalid', 429: 'rate_limited' };

function detailOf(body) {
  if (!body || typeof body !== 'object') return null;
  const d = body.detail ?? body.title;
  return typeof d === 'string' ? d : null;
}

/**
 * GET /v1/racing/next-to-go. Returns { notModified: true } on a 304 (no credits charged), or
 * { races, etag, creditsCost, creditsRemaining }. Throws ApiError.
 */
export async function fetchNextToGo({ apiKey, country, numRaces, etag = null, fetchImpl = fetch,
                                      base = API_BASE, timeoutMs = 15000 }) {
  const params = new URLSearchParams({ include_unresolved: 'true', num_races: String(numRaces) });
  if (country) params.set('country', country);
  const headers = { 'X-API-Key': apiKey, 'User-Agent': USER_AGENT, Accept: 'application/json' };
  if (etag) headers['If-None-Match'] = etag;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  let res;
  try {
    res = await fetchImpl(`${base}/v1/racing/next-to-go?${params}`, { headers, signal: ctrl.signal });
  } catch (e) {
    throw new ApiError(0, e?.name === 'AbortError' ? 'The API did not answer in time.' : 'Could not reach the API.',
                       { code: 'network' });
  } finally {
    clearTimeout(timer);
  }
  if (res.status === 304) return { notModified: true };
  if (!res.ok) {
    let body = null;
    try { body = await res.json(); } catch { /* not JSON */ }
    const ra = Number(res.headers.get('retry-after'));
    throw new ApiError(res.status, detailOf(body) || `The API answered ${res.status}.`,
                       { code: CODE[res.status] || (res.status >= 500 ? 'server' : 'invalid'),
                         retryAfter: Number.isFinite(ra) && ra > 0 ? ra : null });
  }
  const races = await res.json();
  if (!Array.isArray(races)) throw new ApiError(res.status, 'Unexpected response shape.', { code: 'server' });
  return { races, etag: res.headers.get('etag'), creditsCost: Number(res.headers.get('x-credits-cost') ?? NaN),
           creditsRemaining: res.headers.get('x-credits-remaining') };
}

/** The keyless sandbox (/v1/demo/racing/next-to-go): a small envelope, used when no key is set. */
export async function fetchDemo({ fetchImpl = fetch, base = API_BASE, timeoutMs = 15000 } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetchImpl(`${base}/v1/demo/racing/next-to-go`,
                                { headers: { 'User-Agent': USER_AGENT }, signal: ctrl.signal });
    if (!res.ok) throw new ApiError(res.status, `The demo endpoint answered ${res.status}.`,
                                    { code: res.status === 429 ? 'rate_limited' : 'server' });
    const body = await res.json();
    return { races: Array.isArray(body.races) ? body.races : [], demo: true };
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError(0, 'Could not reach the demo endpoint.', { code: 'network' });
  } finally {
    clearTimeout(timer);
  }
}
