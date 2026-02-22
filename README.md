<p align="center">
  <img src="docs/lcore.png" alt="Lcore" width="80">
</p>

<h1 align="center">Lcore</h1>

<p align="center">
  A fast, lightweight, single-file Python WSGI framework with zero dependencies.<br>
  Inspired by the simplicity of <a href="https://bottlepy.org">Bottle</a>.
</p>

<p align="center">
  <a href="https://lcore.lusansapkota.com.np">Documentation</a> &bull;
  <a href="https://play.lcore.lusansapkota.com.np">Live Playground</a> &bull;
  <a href="https://lcore.lusansapkota.com.np/getting-started.html">Getting Started</a> &bull;
  <a href="https://lcore.lusansapkota.com.np/api-reference.html">API Reference</a>
</p>

---

## Installation

```bash
pip install lcore
```

> **Note:** `pip install lcore` pulls the latest **stable, tagged release** and is the recommended way to install.
>
> Copying `lcore.py` directly from the `main` branch may include unreleased or experimental changes. If you prefer copying the file, always use a **tagged release** (e.g. `v0.0.1`) from the [Releases](https://github.com/Lusan-sapkota/lcore/releases) page to ensure stability.

## Quick Start

```python
from lcore import Lcore

app = Lcore()

@app.route('/hello')
def hello():
    return {'message': 'Hello, World!'}

app.run(host='0.0.0.0', port=8080)
```

## Features

- **Single file, zero dependencies** -- drop `lcore.py` into any project
- **Full WSGI compliance** -- works with Gunicorn, uWSGI, Waitress, Gevent, and 17 more server adapters
- **Async/await** -- `async def` route handlers are accepted; note that the worker thread is blocked for the duration (WSGI constraint). See [async caveat](https://lcore.lusansapkota.com.np/routing.html#async-routes).
- **7 built-in middleware** -- CORS, CSRF, security headers, gzip compression, body limits, request ID, structured logging
- **Security** -- PBKDF2 password hashing, HMAC-SHA256 signed cookies, rate limiting, timing-safe comparison
- **Dependency injection** -- singleton, scoped, and transient lifetimes
- **Plugin system** -- JSON serialization, template rendering, and custom plugins with setup/apply lifecycle
- **Request validation** -- JSON body and query parameter validation with type checking
- **Built-in test client** -- `TestClient` for unit testing routes without starting a server
- **Background tasks** -- `BackgroundTaskPool` for fire-and-forget work (emails, cleanup, analytics)
- **4 template engines** -- built-in SimpleTemplate, plus Jinja2, Mako, and Cheetah adapters
- **12 lifecycle hooks** -- request start, auth, handler enter/exit, response build/send, and more
- **Module mounting** -- compose sub-applications with isolated routes and middleware
- **21 server adapters** -- use `server='auto'` to auto-select the best available

## Live Demo & Playground

| Link | Description |
|------|-------------|
| [play.lcore.lusansapkota.com.np](https://play.lcore.lusansapkota.com.np) | Interactive playground -- test routes, middleware, auth flows, and API endpoints live |
| [lcore.lusansapkota.com.np](https://lcore.lusansapkota.com.np) | Full documentation with guides, API reference, and real-world example |

The playground runs the TaskFlow demo backend -- a complete project management API (like Trello/Jira) that demonstrates every Lcore feature: token auth, RBAC, CRUD, file uploads, SMTP email, async handlers, middleware stack, dependency injection, plugins, and a full SPA frontend.

**Demo credentials:**

| Username | Password | Role |
|----------|----------|------|
| admin | admin123 | admin |
| alice | alice123 | member |
| bob | bob123 | member |

## Production Example

```python
from lcore import (
    Lcore, request, response, ctx, on_shutdown,
    CORSMiddleware, SecurityHeadersMiddleware,
    BodyLimitMiddleware, CompressionMiddleware,
    hash_password, verify_password,
    BackgroundTaskPool, TestClient,
    rate_limit, validate_request,
)

app = Lcore()

# Middleware stack
app.use(BodyLimitMiddleware(max_size=10 * 1024 * 1024))
app.use(SecurityHeadersMiddleware(hsts=True))
app.use(CORSMiddleware(allow_origins=['https://myapp.com']))
app.use(CompressionMiddleware())

# Background tasks
tasks = BackgroundTaskPool(max_workers=4)

# Secure password hashing (PBKDF2-SHA256)
@app.post('/register')
@validate_request(body={'username': str, 'password': str})
def register():
    data = request.json
    hashed = hash_password(data['password'])
    # store hashed in database...
    return {'created': True}

@app.post('/login')
@rate_limit(5, per=300)  # NOTE: per-process — see "Multi-worker" note below
def login():
    data = request.json
    user = db.find_user(data['username'])
    if user and verify_password(data['password'], user['password_hash']):
        return {'token': generate_token(user)}
    return {'error': 'Invalid credentials'}

# Graceful shutdown
@on_shutdown
def cleanup():
    tasks.shutdown(wait=True)

app.run(server='gunicorn', host='0.0.0.0', port=8080, workers=4)
```

## Production Notes

### Rate limiter is per-process
`@rate_limit` uses an in-process token bucket with 64-stripe locking. Under a
multi-worker server (e.g. `gunicorn -w 4`) each worker has its own independent
bucket store, so the effective per-client rate limit is `N × limit`.
**Lcore ships a built-in `RedisRateLimitBackend` — no extra code required:**

```bash
pip install redis
```

```python
from lcore import RedisRateLimitBackend, rate_limit

_rl = RedisRateLimitBackend('redis://localhost:6379/0')

@app.post('/api/login')
@rate_limit(5, per=300, backend=_rl)   # enforced across all workers
def login(): ...
```

If Redis is unavailable the backend **fails open** (allows the request) and logs
a warning so a Redis outage does not take down your application.

Temporary workaround (no Redis): `@rate_limit(5 // num_workers, per=300)`.

### Reverse proxies — always use ProxyFixMiddleware
Without it, `request.remote_addr` returns the proxy's IP, not the real client, and
`request.url` may use the wrong scheme (`http` instead of `https`). Add it first:

```python
app.use(ProxyFixMiddleware(trusted_proxies=['10.0.0.1']))  # your proxy's IP(s)
```

### Request timeouts
`TimeoutMiddleware` uses a **persistent thread pool** (not per-request), so it is safe to use
under load. It returns 503 to the client when the deadline is exceeded, but the handler thread
continues running in the background — Python has no safe way to kill a thread. Avoid handlers
that block indefinitely.

```python
app.use(TimeoutMiddleware(timeout=30))
```

## Testing

```python
from lcore import Lcore, TestClient

app = Lcore()

@app.route('/api/users/<id:int>')
def get_user(id):
    return {'id': id, 'name': 'Alice'}

client = TestClient(app)

resp = client.get('/api/users/1')
assert resp.status_code == 200
assert resp.json['name'] == 'Alice'

resp = client.post('/api/items', json={'name': 'Widget'})
assert resp.status_code == 200
```

## Project Structure

```
Lcore/
  lcore.py              # The framework (single file)
  backend/              # TaskFlow demo -- real-world example using every feature
    app.py              # Main entry point
    config.py           # Multi-source config + validation
    models.py           # SQLite database layer
    modules/            # Auth, users, projects, notifications, plugins
    templates/          # Welcome page, frontend SPA, error page
  tests/                # 449 tests (unittest)
  docs/                 # Documentation site (hosted at lcore.lusansapkota.com.np)
  benchmarks/           # Performance benchmarks
```

## Documentation

Full documentation at **[lcore.lusansapkota.com.np](https://lcore.lusansapkota.com.np)**

- [Getting Started](https://lcore.lusansapkota.com.np/getting-started.html) -- installation, first app, core concepts
- [Routing](https://lcore.lusansapkota.com.np/routing.html) -- typed parameters, groups, async handlers
- [Request/Response](https://lcore.lusansapkota.com.np/request-response.html) -- JSON, files, cookies, headers
- [Middleware](https://lcore.lusansapkota.com.np/middleware.html) -- built-in and custom middleware
- [Plugins](https://lcore.lusansapkota.com.np/plugins.html) -- plugin system and lifecycle
- [Advanced](https://lcore.lusansapkota.com.np/advanced.html) -- DI, security, testing, background tasks, production deployment
- [API Reference](https://lcore.lusansapkota.com.np/api-reference.html) -- complete class and function reference
- [Real-World Example](https://lcore.lusansapkota.com.np/real-world-example.html) -- TaskFlow backend walkthrough

## License

MIT -- see [LICENSE](LICENSE) for details.

---

<p align="center">
  Built by <a href="https://lusansapkota.com.np">Lusan Sapkota</a> &bull; Inspired by <a href="https://bottlepy.org">Bottle</a>
</p>
