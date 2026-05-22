# Changelog

All notable changes to Lcore will be documented here.

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
