# Changelog

All notable changes to Lcore will be documented here.

---

## [0.0.5] — 2026-09-22

### Added
- **Server-side sessions.** `SessionMiddleware` stores session state in a backend and puts only a signed session id in the cookie, so a session can be revoked after it is issued. Signed cookies alone cannot be taken back, which ruled out forced logout, sign-out-everywhere after a password reset, and server-side cart invalidation.
- **Three session backends.** `MemorySessionBackend` for development (warns that it is per-process), `SQLiteSessionBackend` for single-server production (stdlib only, and WAL journalling plus a busy timeout make it safe across worker processes, so the zero-dependency promise holds), and `RedisSessionBackend` for multi-server deployments. `SessionBackend` is a documented ABC with seven methods for custom stores.
- **Two independent revocation mechanisms**, implemented by every backend. A per-user index of live session ids powers `list_sessions()` for an active-devices page and `revoke_other_sessions()`. A per-user epoch counter, stamped into a session when it is bound to a user, invalidates every session issued before a `bump_epoch()` without walking the index. `revoke_all()` does both, and is what a password reset should call.
- **Session fixation protection.** `session.bind_user()` regenerates the session id by default, so an id planted before login does not survive it.

- **Per-process epoch caching.** Checking the revocation epoch on every authenticated request meant a second backend round trip on top of loading the session. Backends now cache it for `epoch_cache_ttl` seconds (default 5), which removes that read almost entirely: ten authenticated requests cost one lookup instead of ten. A bump in the same process drops the cached entry immediately, so local revocation stays instant; only another worker's bump waits out the TTL, and `revoke_all()` deletes those sessions through the index anyway. Set `epoch_cache_ttl = 0` to read through.
- **`SessionMiddleware(on_backend_error=...)`.** Sessions cannot fail open the way rate limiting does, since ignoring the store means ignoring revocation. The default `'unavailable'` raises 503, so a login that could not be stored never sets a cookie or reports success. `'anonymous'` keeps the site up with users signed out, and `'raise'` defers to your own error handler. A failed idle-TTL refresh is logged and ignored, because the session is valid until its existing TTL expires.
- **`__all__`.** `from lcore import *` previously exported 214 names including 28 stdlib modules, shadowing the caller's `os`, `re`, `time`, `sys` and `hashlib`. It now exports 163 names, grouped by area, including the module-level routing shortcuts (`get`, `post`, `route`, `mount`, `hook`, `use`, ...), the `Request`/`Response` aliases, the template shortcuts (`jinja2_template`, `jinja2_view`, `mako_template`, ...), `ext`, `json_dumps`/`json_loads` and `server_names`, so `from lcore import *` still works for the classic single-file style. The guard that checks `__all__` against every public definition (`tests/test_api_surface.py`) now also walks module-level assignments, not just `def`/`class`, since the template shortcuts are `functools.partial(...)` assignments and the first cut of the guard couldn't see those.

### Fixed
- **`CompressionMiddleware` streams large bodies instead of buffering them.** An iterable body was collected in full before compressing, so a 20MB streamed response cost about 40MB of RAM per concurrent request and gave up the benefit of streaming entirely. Bodies over `stream_threshold` (default 256KB) are now compressed incrementally with `zlib.compressobj`, holding memory flat: the same 20MB response measured 40.5MB peak before and 0.6MB after. Everything smaller is unchanged, including its `Content-Length`, and the `str`/`bytes` path that ordinary responses take is byte-for-byte what it was. A streamed body drops `Content-Length`, since the compressed size is not known until it ends. The streamed body's source is now closed even if the wrapping generator is discarded before it is ever iterated (a bare generator's own `finally` never runs in that case), which previously leaked a file/cursor handle whenever a later middleware discarded the response before the WSGI layer touched it.
- **`TimeoutMiddleware` no longer breaks every handler that touches `request`.** It runs the handler in a thread pool, but `request`, `response` and `ctx` are thread-locals bound in the serving thread, so a pool thread had none of them. Any handler reading `request` died with `RuntimeError: Request context not initialized` and returned 500, which is close to every handler that does real work. The worker's response is now seeded with a snapshot of whatever pre-phase middleware (CORS, CSRF, ...) already set, so a handler can read, overwrite or delete it exactly as it would in a single unthreaded response — an early version of this fix merged the worker's response back additively, which meant a handler deleting a pre-phase-set header crashed with `KeyError` and installing `TimeoutMiddleware` alone could silently change which of two conflicting header values (e.g. compression's own `Vary: Accept-Encoding` vs. CORS's `Vary: Origin`) survived. `ctx.state` and `ctx._lazy` are shared dicts, so sessions and dependency-injection scope survive the hop for free, and `ctx.user`/`ctx.route`/`ctx.request_id` (thread-local `__slots__`, not part of those dicts) are copied back explicitly once the worker finishes. The middleware previously had no tests at all; it now has 18, including the header-delete and raising-handler cases above.
- **`ProxyFixMiddleware(num_proxies=N)` now does something.** The parameter was accepted and stored but never read, so the documented call silently fell back to trusting loopback addresses only. It now enables hop-count trust: the last N `X-Forwarded-For` entries are trusted regardless of peer IP, matching Werkzeug's `ProxyFix` model, falling back to `REMOTE_ADDR` when the chain is shorter than N. `remote_addr` and `urlparts` both honour it. The default changed from `1` to `None`, so zero-argument behaviour is unchanged.
- **`set_cookie()` no longer emits attributes that have no value.** Passing `domain=None` rendered the literal string `Domain=None` into the `Set-Cookie` header, which browsers reject. Attributes whose value is `None` are now omitted, except `samesite`, where `None` is a meaningful explicit value (`SameSite=None`, the cross-site opt-in) rather than "omit this attribute". `delete_cookie()` is unaffected: its `expires=0` and `max_age=-1` are still emitted.
- **`load()` no longer accepts a `**namespace` it ignores.** The parameter was the globals dict for an `eval()` that has since been replaced by a safe `getattr` chain, so it could not affect the result. Passing one now raises `TypeError` instead of being silently discarded.
- **A freshly bound-in session is no longer deleted by another worker's stale epoch cache.** `SessionMiddleware` compared a session's stamped epoch to the cached epoch with `!=` instead of `<`. Epochs only increase, so a session stamped moments after `revoke_all()` on one worker could be stamped with epoch 1 while a second worker's 5-second epoch cache still held 0; `1 != 0` rejected the brand-new, fully valid session and `_open()` deleted it, repeating on every request from that worker for up to `epoch_cache_ttl` seconds. Now `<`, which only rejects sessions stamped *before* the current epoch.
- **A concurrent revoke could no longer be undone by its own cache.** `cached_epoch()` is deliberately unlocked, but a thread already blocked in a backend read for the old epoch could still write it into the cache *after* a same-process `bump_epoch()`/`_forget_epoch()` had already run and found nothing to invalidate, silently reviving a just-revoked epoch for up to `epoch_cache_ttl` seconds in the very process that performed the revoke. A generation counter, bumped alongside the cache invalidation, now detects that race and skips caching the possibly-stale read.
- **`Session.bind_user(regenerate=False)` no longer leaves a session cross-linked to the wrong user.** Rebinding an existing sid to a different user without regenerating it left the old user's index still pointing at a session that now belonged to someone else, so `list_sessions()` could show another user's device and `revoke_all()`/`revoke_other_sessions()` could revoke another user's live session. `bind_user()` now unindexes the sid from its previous user before rebinding it; `MemorySessionBackend` and `RedisSessionBackend` implement the new `unindex()` hook, `SQLiteSessionBackend` needs no override since its `uid` column is the source of truth.
- **`MemorySessionBackend(max_sessions=N)` is now actually enforced.** It only evicted *expired* sessions when at capacity, so a flood of still-live sessions (e.g. one per anonymous visit) grew the store past `max_sessions` without bound. It now falls back to evicting the oldest-inserted sessions when nothing has expired.
- **`RedisSessionBackend`'s per-user index can no longer expire out from under a live session.** `save()` unconditionally reset the index key's TTL to whatever `ttl` that particular save used, so a shorter-lived save (or a plain `backend.touch(sid, short_ttl)`) after a long-lived one could shrink the whole index's expiry below a co-existing longer-lived session's — `list_user()`/`revoke_user()`/`revoke_all()` would then silently see zero sessions for that user while the session itself was still valid. A small Lua script now extends the index's TTL but never shrinks it.
- **`SQLiteSessionBackend.revoke_user()` no longer overcounts.** It deleted and counted every row for a uid with no `expires > now` filter, unlike `list_user()`'s equivalent query, so an account page could report "signed out of 4 devices" when `list_user()` had only ever shown 1 live one — the extra 3 were rows that had expired but not yet been swept.
- **`Session.pop()`/`setdefault()`/`clear()` no longer mark the session dirty on a no-op.** All three set the dirty flag unconditionally, so the common flash-message idiom `request.session.pop('flash', None)` cost a backend write and a fresh `Set-Cookie` on every request that merely checked for one, defeating the "reads are free" design this feature is built on. They're now dirty only when something actually changed.
- **A dependency named `'session'` no longer silently collides with `SessionMiddleware`.** Both `app.inject('session', ...)` and `SessionMiddleware` publish through `ctx.session`; depending on the dependency's lifetime, one would silently shadow the other with no error. `SessionMiddleware` now raises a clear `RuntimeError` if a `'session'` dependency is already registered. Separately, `DependencyContainer.register()` rejects any name that resolves through a `RequestContext`/`LocalContext` attribute or method (`user`, `route`, `request_id`, `lazy`, ...), since those are found before `ctx.__getattr__` ever runs and a same-named dependency was silently unreachable via `ctx.<name>`.
- **`TestClient`'s `wsgi.errors` stream no longer crashes on an unhandled exception.** It was a `BytesIO`, but the framework's own error logging (and WSGI generally) writes `str` to `wsgi.errors`; any exception in a handler tested through `TestClient` raised `TypeError: a bytes-like object is required, not 'str'` instead of turning into the 500 response the app actually produced. Now a `StringIO`, matching `tests/helpers.py`'s existing (correct) setup.
- **The `async def` route warning now actually fires.** `Route._make_callback()` checked `_is_async()` on the callback *after* the plugin loop, but `JSONPlugin` (auto-installed on every app) already wraps every callback in a plain sync function before that point, so the check only ever saw JSONPlugin's wrapper — the warning was dead code except on a route that explicitly did `skip=['json']`. It now checks the route's own callback before plugins touch it, so every `async def` route warns as documented, naming the route, the first time it's invoked.

### Internal
- **Added an API surface guard** (`tests/test_api_surface.py`). Three shipped bugs shared one shape: a parameter accepted but never read. None of them raised, none failed a test, and all were invisible with default arguments. The suite now walks lcore's AST and fails if any public parameter is ignored, or stored on `self` and never consulted, with an allowlist for contract signatures such as the WSGI and importlib protocols. Cookie attributes and the CSRF and session cookie options are now exercised at non-default values.
- **Session backend round trips and lock time reduced.** `MemorySessionBackend` stores each session's uid alongside its record instead of inside the JSON blob, so dropping or listing a session no longer parses it just to find who owns it. `RedisSessionBackend.delete()` no longer does a `GET`+parse purely to locate the per-user index entry to prune (the index already tolerates and lazily prunes dead members on read); it's a single `DEL`. `SQLiteSessionBackend.bump_epoch()` is one `INSERT ... ON CONFLICT DO UPDATE` instead of an `UPDATE` plus a conditional `INSERT` plus a re-read, and its periodic cleanup sweep is now bounded (`cleanup_batch`, default 1000 rows) instead of a single unbounded `DELETE` over every session that expired since the last sweep, which could turn one unlucky request into a full-table scan holding a write transaction. `RedisRateLimitBackend` and `RedisSessionBackend` now share one internal helper for constructing and closing the redis-py client instead of duplicating the import guard and `from_url()` call.
- **Measured `TimeoutMiddleware`'s per-request cost, and trimmed the avoidable part of it.** It had never been benchmarked: on a trivial handler it costs roughly 30µs/request versus a bare route (~9µs), against a ~7-8µs floor for the `ThreadPoolExecutor` submit/result round trip alone. The gap was partly a redundant `ctx.bind()` inside the worker — reallocating `state={}`/`_lazy={}` and zeroing `route`/`user`/`request_id` only to overwrite all of it two lines later — which is now a single direct assignment per slot instead. The remaining gap (response snapshot in, response snapshot out) is inherent: `request`/`response` are `threading.local()`-backed singletons, so some copying across the thread boundary is unavoidable without going back to the blank-worker-response design that caused the header-delete crash above. Apply `TimeoutMiddleware` to specific slow/unpredictable routes via `app.use(TimeoutMiddleware(...), routes='/slow/*')` rather than globally if this matters for your workload.

### Changed
- **`CSRFMiddleware` warns when `secret=` is omitted.** A random per-process secret means that under multi-worker deployment a token cookie signed by one worker fails verification on another, so legitimate submissions are rejected with 403. `SessionMiddleware` carries the same warning, where the symptom is users being logged out at random.

---

## [0.0.4] — 2026-05-22

### Fixed
- **HTTPError.apply() now merges headers** instead of replacing them. Headers set by a handler before raising `HTTPError` are preserved. This means `response.set_header('Content-Type', 'application/json')` followed by `raise HTTPError(401)` now correctly returns JSON instead of HTML.
- **`request.json` and URL-encoded POST body no longer have a silent 100KB limit.** They now use `self.body.read()` which respects `BodyLimitMiddleware` and spills to disk for large payloads. Previously, a JSON body >100KB was rejected with 413 even when `BodyLimitMiddleware` allowed it.
- **Multipart `disk_limit` now respects `BodyLimitMiddleware`.** The multipart parser's disk limit is set from the body max size in environ (default 1GB), so configuring `BodyLimitMiddleware(max_size=50*1024*1024)` also limits multipart uploads.
- **`skip` parameter now works for middleware**, not just plugins. `app.post('/login', skip=['csrf'])` correctly exempts the route from `CSRFMiddleware`.

### Added
- **Pre-routing middleware phase.** Middleware classes can now set `phase = 'pre'` to run *before* route matching. This fixes CORS preflight (`OPTIONS` requests no longer get 405), CSRF cookie setting, and body limit enforcement all running before the router. `CORSMiddleware`, `CSRFMiddleware`, `BodyLimitMiddleware`, and `ProxyFixMiddleware` default to `phase = 'pre'`.
- **`error.format` config key.** Set `app.config['error.format'] = 'json'` to make all error responses return JSON instead of HTML. No more per-status-code error handlers needed for JSON APIs.
- **`HTTPError` now accepts `content_type` parameter.** `raise HTTPError(401, body=json_dumps({"error": "Unauthorized"}), content_type='application/json')` sets the correct Content-Type in one line.
- **`load_dotenv()` function.** Loads `.env` files into `os.environ` with zero dependencies. Called automatically by `app.run()`. Also available as `from lcore import load_dotenv`.
- **`app.config['proxy.trusted']` config key.** Set it to a list of trusted proxy IPs (or comma-separated string) to auto-enable proxy header trust without needing `ProxyFixMiddleware`. `request.remote_addr` and `request.urlparts` will trust `X-Forwarded-*` headers from these IPs.

### Changed
- **`validate_request` decorator improved.** Now supports `Optional[type]` for optional fields, auto-coerces types (e.g. string to int), strips whitespace from strings, and returns structured JSON errors with `{"error": "Validation failed", "fields": {...}}` format.
- **`set_cookie` now defaults to `samesite='Lax'` and `httponly=True`.** Secure by default; override with explicit keyword arguments when you need JS-readable cookies (e.g. CSRF tokens).

### Security
- **Chunked transfer parser hardened against slow-loris DoS.** Previously read chunk headers one byte at a time with no timeout; now uses buffered reads with a configurable cap.
- **`static_file()` TOCTOU fix.** The file is now opened before symlink and path-traversal checks, pinning the inode. On Linux, the real path is resolved through `/proc/self/fd/<n>` for an atomic check.
- **`FileUpload.save()` TOCTOU fix.** Uses Python's `'x'` exclusive-create mode instead of `os.path.exists()` + `open()`, eliminating the race between the existence check and the file write.
- **Multipart filename sanitization added at parse time.** The raw `_MultipartPart.filename` now strips directory separators via `os.path.basename()` as defense-in-depth, before `FileUpload.filename` does its full sanitization pass.
- **Error page template no longer uses `repr()` in HTML context.** The auto-escaping `{{ }}` template expression handles URL escaping directly.
- **`.env` quote stripping fixed.** Only strips matching quote pairs (`"..."` or `'...'`) rather than all leading/trailing quote characters, preventing mangling of values like `"it's"`.

---

## [0.0.2] — 2026-02-23

### Fixed
- PyPI project page logo not rendering (relative path → absolute URL in README)

---

## [0.0.1] — 2026-02-23 — Initial Release

First public release of Lcore. 🎉

### Framework Core
- Full **WSGI compliance** — works with Gunicorn, uWSGI, Waitress, Gevent, and 21 server adapters
- `server='auto'` auto-selects the best available server at startup
- Single-file distribution (`lcore.py`) — zero external dependencies, pure Python 3.8+ standard library
- **Route decorator API** — `@app.route`, `@app.get`, `@app.post`, `@app.put`, `@app.delete`, `@app.patch`
- **Typed URL parameters** — `<name:int>`, `<name:float>`, `<name:path>`, `<name:uuid>`, `<name:slug>`
- Route groups with shared prefix and middleware
- `async def` route handler support (WSGI-constrained — worker thread is blocked; documented caveat)

### Request / Response
- `request.json`, `request.form`, `request.files`, `request.query`, `request.headers`, `request.cookies`
- `request.remote_addr` with `ProxyFixMiddleware` support
- Fluent response builder — `response.set_header()`, `response.set_cookie()`, `response.set_status()`
- Built-in JSON serialization via `json` (optional `ujson` drop-in)
- Streaming and file responses

### Middleware (7 built-in)
- `CORSMiddleware` — configurable origins, methods, headers, credentials
- `CSRFMiddleware` — double-submit cookie pattern
- `SecurityHeadersMiddleware` — HSTS, X-Frame-Options, CSP, X-Content-Type-Options
- `CompressionMiddleware` — gzip response compression
- `BodyLimitMiddleware` — max request body size enforcement
- `RequestIDMiddleware` — unique request ID header injection
- `LoggingMiddleware` — structured request/response logging
- `TimeoutMiddleware` — per-request deadline with persistent thread pool
- `ProxyFixMiddleware` — trusted reverse proxy IP and scheme fix

### Security
- `hash_password` / `verify_password` — PBKDF2-SHA256 with per-password salt
- HMAC-SHA256 signed cookies
- `@rate_limit(n, per=seconds)` — in-process token bucket with 64-stripe locking
- `RedisRateLimitBackend` — cross-worker rate limiting; fails open on Redis outage
- Timing-safe string comparison utilities

### Dependency Injection
- `@app.provide` — singleton, scoped, and transient lifetimes
- Constructor and parameter injection

### Plugin System
- `setup` / `apply` plugin lifecycle
- Built-in JSON plugin, template plugin
- Custom plugin support

### Request Validation
- `@validate_request(body={...}, query={...})` — type-checked JSON body and query params

### Templates (4 engines)
- Built-in `SimpleTemplate` (no deps)
- Adapters for Jinja2, Mako, and Cheetah

### Lifecycle Hooks (12 hooks)
- `on_request`, `on_auth`, `before_handler`, `after_handler`, `on_response`, `on_send`, `on_error`, `on_shutdown`, and more

### Background Tasks
- `BackgroundTaskPool` — fire-and-forget task pool with configurable worker count and graceful shutdown

### Module Mounting
- `app.mount(prefix, sub_app)` — compose sub-applications with isolated routes and middleware

### Testing
- `TestClient` — in-process test client, no server required
- 449 tests using only `unittest` from the standard library

### Performance
Benchmarked at 100,000 iterations × 3 runs (pure framework overhead, single process):

| Test           | Lcore req/s | Flask req/s | vs Flask |
|----------------|-------------|-------------|----------|
| Plaintext      | 122,715     | 30,500      | 4.0x     |
| JSON           | 95,910      | 26,403      | 3.6x     |
| Route Params   | 90,332      | 24,784      | 3.6x     |
| Middleware     | 53,113      | 24,261      | 2.2x     |
| 404 Miss       | 37,191      | 16,802      | 2.2x     |
| Multi-Route    | 96,812      | 27,488      | 3.5x     |
| POST JSON      | 62,963      | 21,149      | 3.0x     |

### Compatibility
- Python 3.8, 3.9, 3.10, 3.11, 3.12, 3.13
- Linux, macOS, Windows
- All standard WSGI servers

### Links
- **PyPI:** https://pypi.org/project/lcore/
- **Docs:** https://lcore.lusansapkota.com.np
- **Playground:** https://play-lcore.lusansapkota.com.np
- **Source:** https://github.com/Lusan-sapkota/lcore

---

_Lcore follows [Semantic Versioning](https://semver.org). During the `0.x` series, minor versions may include breaking changes._
