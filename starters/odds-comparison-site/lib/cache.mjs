// One shared copy of the board for every visitor.
//
// The page never calls the API itself. A visitor reads whatever this cache holds; the cache refreshes
// on its own timer, at most once per `pollSeconds`, and only while someone has viewed the page within
// `idleSeconds` (no visitors, no credits). Concurrent refreshes collapse into one request
// ("single-flight"). On a failure the last good board is kept and marked stale, and the next attempt
// backs off exponentially (honouring Retry-After); a refusal that retrying cannot fix (bad key, plan,
// credits) stops refreshing until the process restarts, so a misconfiguration never burns requests.

export class SharedBoard {
  constructor({ load, pollSeconds = 60, idleSeconds = 600, maxBackoffSeconds = 600, now = () => Date.now() }) {
    this.load = load;                       // async ({ etag }) -> { races, etag } | { notModified: true }
    this.pollMs = Math.max(20, pollSeconds) * 1000;
    this.idleMs = Math.max(60, idleSeconds) * 1000;
    this.maxBackoffMs = maxBackoffSeconds * 1000;
    this.now = now;
    this.races = null;                      // last good board (null until the first success)
    this.etag = null;
    this.fetchedAt = null;                  // ms of the last successful (200 or 304) refresh
    this.error = null;                      // last ApiError, cleared on success
    this.failures = 0;
    this.nextAllowedAt = 0;                 // no refresh before this (poll interval / backoff)
    this.stopped = false;                   // a fatal refusal: no more refreshes
    this.inflight = null;
    this.lastViewAt = 0;
    this.upstreamCalls = 0;
  }

  /** Called on every page view. Returns the current snapshot; may start a refresh, never awaits it
   *  unless there is nothing to show yet. */
  async view({ wait = true } = {}) {
    this.lastViewAt = this.now();
    if (this.due()) {
      const p = this.refresh();
      if (wait && this.races === null) await p;
    }
    return this.snapshot();
  }

  due() {
    return !this.stopped && !this.inflight && this.now() >= this.nextAllowedAt;
  }

  idle() {
    return this.now() - this.lastViewAt > this.idleMs;
  }

  /** Background tick: refresh only if due and someone has looked recently. */
  async tick() {
    if (!this.idle() && this.due()) await this.refresh();
  }

  refresh() {
    if (this.inflight) return this.inflight;
    this.inflight = (async () => {
      this.upstreamCalls += 1;
      try {
        const out = await this.load({ etag: this.etag });
        if (!out.notModified) {
          this.races = out.races;
          this.etag = out.etag || null;
        }
        this.fetchedAt = this.now();
        this.error = null;
        this.failures = 0;
        this.nextAllowedAt = this.now() + this.pollMs;
      } catch (e) {
        this.error = e;
        this.failures += 1;
        if (e && e.fatal) {
          this.stopped = true;
        } else {
          const backoff = Math.min(this.maxBackoffMs, this.pollMs * 2 ** Math.min(this.failures - 1, 6));
          const ra = e && e.retryAfter ? e.retryAfter * 1000 : 0;
          const jitter = Math.floor(backoff * 0.1 * Math.random());
          this.nextAllowedAt = this.now() + Math.max(backoff, ra) + jitter;
        }
      } finally {
        this.inflight = null;
      }
    })();
    return this.inflight;
  }

  snapshot() {
    let state;
    if (this.races === null) state = this.error ? 'error' : 'loading';
    else if (this.error) state = 'stale';
    else state = this.races.length ? 'fresh' : 'empty';
    return { state, races: this.races || [], fetchedAt: this.fetchedAt, error: this.error,
             stopped: this.stopped, nextRefreshAt: this.stopped ? null : this.nextAllowedAt };
  }
}
