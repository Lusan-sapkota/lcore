Source: https://lcore.lusansapkota.com.np/middleware.html

# Middleware & Hooks

Intercept and transform requests and responses with composable middleware and lifecycle hooks.

## Overview

Middleware wraps the request pipeline. Each middleware receives a `ctx` (RequestContext) and a `next_handler` callable, and can inspect, modify, or short-circuit the request.

### Pre-Routing vs Post-Routing (v0.0.4)

Middleware runs in two phases controlled by the `phase` attribute:

- **Pre-routing** (`phase = 'pre'`) runs *before* the router matches a URL. Use for CORS preflight, CSRF token setup, and body size enforcement. Can short-circuit the entire request.
- **Post-routing** (`phase = 'post'`, the default) wraps the matched handler. Use for compression, logging, security headers.

```python
from lcore import Lcore, CORSMiddleware, SecurityHeadersMiddleware

app = Lcore()

app.use(CORSMiddleware(allow_origins='*'))      # phase='pre'  runs before routing
app.use(SecurityHeadersMiddleware(hsts=True))     # phase='post'  wraps handler
```

Execution order within each phase is controlled by `order` (lowest first).

## Built-in Middleware

| Middleware | Order | Phase | Purpose |
|---|---|---|---|
| `ProxyFixMiddleware` | -10 | pre | Trust X-Forwarded-* from reverse proxies |
| `BodyLimitMiddleware` | 0 | pre | Enforce request body size limit |
| `RequestIDMiddleware` | 1 | post | Add unique request ID header |
| `RequestLoggerMiddleware` | 2 | post | Structured JSON request logging |
| `CORSMiddleware` | 3 | pre | Cross-origin resource sharing (preflight before routing) |
| `SecurityHeadersMiddleware` | 5 | post | Security headers to every response |
| `CSRFMiddleware` | 10 | pre | CSRF token generation and validation |
| `SessionMiddleware` | 20 | post | Server-side sessions with a signed id cookie |
| `TimeoutMiddleware` | -5 | post | Enforce per-request time limit |
| `CompressionMiddleware` | 90 | post | Gzip response compression |

### RequestIDMiddleware

Adds a unique `X-Request-ID` header to every response and sets `ctx.request_id`:

```python
from lcore import RequestIDMiddleware
app.use(RequestIDMiddleware())
```

### RequestLoggerMiddleware

Logs every request as structured JSON with method, path, status, and duration:

```python
from lcore import RequestLoggerMiddleware
import logging

logger = logging.getLogger('myapp')
app.use(RequestLoggerMiddleware(logger=logger))
```

### CORSMiddleware

Full CORS support with origin validation and preflight handling:

```python
from lcore import CORSMiddleware

# Allow all origins
app.use(CORSMiddleware(allow_origins='*'))

# Restrict to specific origins
app.use(CORSMiddleware(
    allow_origins=['https://myapp.com', 'https://admin.myapp.com'],
    allow_methods=['GET', 'POST', 'PUT', 'DELETE'],
    allow_headers=['Content-Type', 'Authorization'],
    expose_headers=['X-Request-ID'],
    allow_credentials=True,
    max_age=86400
))
```

| Parameter | Default | Description |
|---|---|---|
| `allow_origins` | `'*'` | Allowed origins: `'*'`, single string, or list |
| `allow_methods` | `['GET','POST','PUT','DELETE','PATCH','OPTIONS']` | Allowed HTTP methods |
| `allow_headers` | `['Content-Type','Authorization','X-Requested-With']` | Allowed request headers |
| `expose_headers` | `[]` | Headers visible to the browser |
| `allow_credentials` | `False` | Allow cookies/auth headers. **Cannot be used with `allow_origins='*'`** specify explicit origins instead. |
| `max_age` | `86400` | Preflight cache duration (seconds) |

### SecurityHeadersMiddleware

Adds best-practice security headers to every response:

```python
from lcore import SecurityHeadersMiddleware

app.use(SecurityHeadersMiddleware(hsts=True, hsts_max_age=31536000))

# Override specific headers
app.use(SecurityHeadersMiddleware(
    hsts=True,
    **{'Content-Security-Policy': "default-src 'self'"}
))
```

Default headers set: `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `X-XSS-Protection: 0`, `Referrer-Policy: strict-origin-when-cross-origin`, `Content-Security-Policy: default-src 'self'`.

### CSRFMiddleware

Validates CSRF tokens on state-changing requests. Tokens are checked in the header first, then in form data:

```python
from lcore import CSRFMiddleware

app.use(CSRFMiddleware(
    secret='my-csrf-secret',
    cookie_name='_csrf_token',
    header_name='X-CSRF-Token',
    form_field='_csrf_token',
    safe_methods=('GET', 'HEAD', 'OPTIONS'),
    secure=True   # Set cookie with Secure flag (HTTPS only)
))
```

| Parameter | Default | Description |
|---|---|---|
| `secret` | `None` | HMAC secret. If not set, a random secret is generated per process and a `UserWarning` is raised — with multiple worker processes (e.g. `gunicorn -w N`) each gets its own secret, so tokens signed by one worker fail verification on another. Always pass a fixed secret in multi-process deployments. |
| `cookie_name` | `'_csrf_token'` | Cookie name for the CSRF token. |
| `header_name` | `'X-CSRF-Token'` | Header to check for the token (AJAX). |
| `form_field` | `'_csrf_token'` | Form field name to check for the token. |
| `safe_methods` | `('GET','HEAD','OPTIONS')` | HTTP methods that skip CSRF validation. |
| `secure` | `False` | Set `Secure` flag on cookie (requires HTTPS). |

### BodyLimitMiddleware

Rejects requests with bodies exceeding the limit (returns 413):

```python
from lcore import BodyLimitMiddleware

# Limit request bodies to 5MB
app.use(BodyLimitMiddleware(max_size=5 * 1024 * 1024))
```

### CompressionMiddleware

Gzip-compresses responses when the client accepts it:

```python
from lcore import CompressionMiddleware

app.use(CompressionMiddleware(
    min_size=256,               # Don't compress small responses
    level=6,                    # Compression level (1-9)
    content_types=None,         # Compress all content types
    stream_threshold=256*1024   # Buffer limit before streaming
))
```

A `str` or `bytes` body is compressed in one call and gets a `Content-Length`. An iterable body is buffered up to `stream_threshold`; if it fits, it is compressed whole and also keeps its `Content-Length`, so ordinary responses are unaffected.

A body that outgrows the buffer switches to incremental gzip and is sent in chunks. Memory then stays flat instead of tracking the response size: a 20MB streamed body used to be buffered in full, costing roughly 40MB per concurrent request and removing the benefit of streaming in the first place. The trade is that `Content-Length` is dropped, because the compressed size is not known until the body ends. Raise `stream_threshold` if you would rather buffer more and keep the header.

### ProxyFixMiddleware

Tells `request.remote_addr` and `request.urlparts` to trust `X-Forwarded-*` headers from known reverse proxies. v0.0.4 alternative: set `app.config['proxy.trusted']` instead. Two independent modes — pass one or the other, not both:

- `trusted_proxies=[...]` — IP allowlist. Forwarded headers are only trusted when the directly-connecting peer's address is in the list. Works for multi-hop chains as long as every proxy's IP is known.
- `num_proxies=N` — hop-count trust. Blindly trusts the last `N` entries of `X-Forwarded-For`, no IP check (same model as Werkzeug's `ProxyFix`). Use this when the proxy's IP isn't fixed, but your network guarantees exactly `N` proxies sit in front of the app.

```python
from lcore import ProxyFixMiddleware

app.use(ProxyFixMiddleware(trusted_proxies=['127.0.0.1', '10.0.0.1']))
app.use(ProxyFixMiddleware(num_proxies=1))  # trust the nearest proxy hop, any IP
```

### TimeoutMiddleware

Runs the handler in a thread pool, returning 503 if it exceeds the deadline. v0.0.4 moves it to post-routing phase.

```python
from lcore import TimeoutMiddleware

app.use(TimeoutMiddleware(timeout=30))       # 30 second limit
app.use(TimeoutMiddleware(timeout=10, max_workers=8))
```

> **Scope it to the routes that need it**
> The thread-pool hop has a real, measured cost — roughly 30µs/request on a trivial handler versus a ~9µs bare route, most of it inherent to marshaling `request`/`response` across the thread boundary (they're `threading.local()`-backed). Python also can't actually kill the stuck thread on timeout, so it keeps running in the background after the client gets its 503. For most deployments, Gunicorn's own `timeout` and your reverse proxy's read timeout handle this better — see [Request Timeouts](https://lcore.lusansapkota.com.np/advanced.html#request-timeouts). Reach for this middleware for per-route limits tighter than your infra timeout, and scope it with `routes=` (e.g. `app.use(TimeoutMiddleware(timeout=30), routes='/slow/*')`) rather than installing it globally.

### SessionMiddleware

Server-side sessions. The cookie carries a signed session id and nothing else, so session state can be revoked from the server. See [Sessions](https://lcore.lusansapkota.com.np/#sessions) for the full API.

```python
from lcore import SessionMiddleware, SQLiteSessionBackend

app.use(SessionMiddleware(
    backend=SQLiteSessionBackend('var/sessions.db'),
    secret=os.environ['SESSION_SECRET'],
))
```

Installing `SessionMiddleware` costs something on every request even on a route that never touches `request.session` — roughly 25-30% versus no session middleware at all in measurements, mostly the cookie-signing setup and the lazy accessor registration that run regardless. That's the price of it being available; routes that actually read or write the session pay more on top for the backend round trip and, when dirty, the write and re-signed cookie.

## Sessions

> **Concurrent requests**
> Session changes are merged into the stored record on save, key by key, so two requests that set different keys at the same time both keep their changes (atomically in the Memory, SQLite and Redis backends). If the session was revoked or expired meanwhile, the write is dropped instead of bringing it back. Two requests that set the *same* key still race: the later write wins. Changes made by mutating a nested value in place (`session['cart'].append(x)`) are not tracked; assign the key again.

Lcore's signed cookies are fine for carrying a few bytes of state, but they cannot be taken back: once issued, a signed cookie stays valid until it expires. Anything that needs to be revocable, which means logins, carts and anything tied to a password, needs server-side state. `SessionMiddleware` stores the record in a backend and puts only a signed session id in the cookie.

```python
import os
from lcore import Lcore, SessionMiddleware, SQLiteSessionBackend, request

app = Lcore()
app.use(SessionMiddleware(
    backend=SQLiteSessionBackend('var/sessions.db'),
    secret=os.environ['SESSION_SECRET'],
    ttl=14 * 24 * 3600,      # idle timeout
    absolute_ttl=30 * 24 * 3600,  # hard cap regardless of activity
    secure=True,             # HTTPS only
))

@app.post('/cart/add')
def add_to_cart():
    cart = request.session.setdefault('cart', [])
    cart.append(request.forms.get('sku'))
    request.session['cart'] = cart     # assignment marks it dirty
    return {'items': len(cart)}
```

The session is loaded lazily and written back only when it changes, so anonymous browsing costs no backend writes and sets no cookie. It is reachable as both `request.session` and `ctx.session`. `pop()`, `setdefault()` and `clear()` only mark it dirty when they actually change something — the common flash-message idiom `request.session.pop('flash', None)` is a free read on a request that has nothing to pop, not a guaranteed write.

### Choosing a backend

| Backend | Dependencies | Use when |
|---|---|---|
| `MemorySessionBackend` | None | Development only. Sessions die on restart, and each worker process has its own store, so users appear logged in on one worker and out on the next. It warns when constructed. |
| `SQLiteSessionBackend` | None (stdlib) | Single-server production. Uses WAL journalling and a busy timeout, so it is safe across worker processes on one machine. Keeps the zero-dependency promise. |
| `RedisSessionBackend` | `uv add redis` | Multiple application servers, or when sessions should outlive the machine. |

Write your own by subclassing `SessionBackend` and implementing seven methods: `load`, `save`, `delete`, `list_user`, `revoke_user`, `get_epoch` and `bump_epoch`. An optional eighth, `merge(sid, ops, seen, ttl)`, applies a request's key changes to the stored record; the base class provides a non-atomic load-apply-save version, so override it if your store can do better. `revoke_all()` and `touch()` are provided by the base class. Records must stay JSON-serialisable: every shipped backend round-trips them through JSON, so development behaviour matches production.

> **unindex()**
> If your backend keeps its own per-user index (as `MemorySessionBackend` and `RedisSessionBackend` do, for `list_sessions()`/`revoke_other_sessions()`), also override `unindex(sid, user_key)`. It's called when `bind_user(regenerate=False)` reassigns an existing session to a different user, so the old user's index doesn't keep pointing at a session that now belongs to someone else. The base implementation is a no-op, which is correct only for a backend like `SQLiteSessionBackend` whose membership comes structurally from a `uid` column rather than a separate index.

### Logging in and out

`bind_user()` attaches the session to a user and regenerates the session id. That regeneration is what closes session fixation, where an attacker plants a known session id before login and still holds a valid session afterwards:

```python
@app.post('/login')
def login():
    user = authenticate(request.forms.get('email'),
                        request.forms.get('password'))
    if not user:
        raise HTTPError(401, 'Invalid credentials')
    request.session.bind_user(user.id)   # regenerates the id
    request.session['name'] = user.name
    redirect('/account')

@app.post('/logout')
def logout():
    request.session.destroy()   # deleted server-side, not just in this browser
    redirect('/')
```

### Revoking sessions

Two independent mechanisms, both implemented by every backend:

- **Index** — a per-user set of live session ids. Powers `list_sessions()` for an "active devices" page and revoking one device without the others.
- **Epoch** — a per-user counter stamped into a session when it is bound to a user. Bump it and every session issued before the bump dies on its next load, without walking the index.

`revoke_all()` does both, and is what a password reset should call. The index pass kills every session the backend knows about; the epoch bump catches any it does not, such as one written by another worker while the revoke was in flight.

```python
@app.post('/account/password')
def change_password():
    save_new_password(...)
    # Sign out everywhere, including this browser.
    request.session.revoke_all_sessions()
    redirect('/login')

@app.post('/account/sessions/revoke-others')
def revoke_others():
    n = request.session.revoke_other_sessions()   # keeps the current device
    return {'revoked': n}

@app.get('/account/sessions')
def active_sessions():
    return {'sessions': [
        {'current': sid == request.session.sid,
         'ip': rec['ip'], 'user_agent': rec['ua'], 'since': rec['created']}
        for sid, rec in request.session.list_sessions()
    ]}
```

Outside a request, for example from an admin tool or a background job, call the backend directly:

```python
sessions = SQLiteSessionBackend('var/sessions.db')
sessions.revoke_all(user_id)          # index and epoch
sessions.list_user(user_id)           # [(sid, record), ...]
sessions.bump_epoch(user_id)          # epoch only
```

### SessionMiddleware parameters

| Parameter | Default | Description |
|---|---|---|
| `backend` | `MemorySessionBackend()` | Where records are stored. Set this in production. |
| `secret` | `None` | HMAC secret for the session cookie. If unset, a random per-process secret is generated and a `UserWarning` is raised: every restart logs everyone out, and each worker rejects the others' cookies. Always set it in production. |
| `cookie_name` | `'lcore_session'` | Name of the session cookie. |
| `ttl` | `1209600` (14 days) | Idle timeout in seconds, refreshed as the session is used. |
| `absolute_ttl` | `None` | Hard lifetime cap from creation, regardless of activity. |
| `refresh_every` | `ttl // 10` | Minimum interval between idle-TTL refreshes, so a read-only request on an existing session does not cost a write. |
| `secure` | `False` | Set the `Secure` flag. Enable whenever you serve over HTTPS. |
| `httponly` | `True` | Keep the cookie out of reach of JavaScript. |
| `samesite` | `'Lax'` | `'Lax'`, `'Strict'` or `'None'`. |
| `path` / `domain` | `'/'` / `None` | Cookie scope. |
| `on_backend_error` | `'unavailable'` | What to do when the store is unreachable. See below. |

### When the session store is down

Rate limiting can fail open, because the worst case is that limits stop applying for a while. Sessions cannot: ignoring the store would mean ignoring revocation, and silently downgrading a signed-in customer to anonymous in the middle of a checkout loses their cart. So the default refuses the request instead.

| Value | Behaviour |
|---|---|
| `'unavailable'` (default) | Raise `503 Service Unavailable`. A login that cannot be stored never sets a cookie and never reports success. |
| `'anonymous'` | Treat the request as having no session. The site stays up, but signed-in users appear signed out for the duration of the outage. |
| `'raise'` | Let the backend exception propagate to your own error handler. |

A failed *idle TTL refresh* is the one exception: it is logged and ignored, because the session is still valid until its existing TTL runs out, and failing the request would gain nothing.

### Epoch caching

Checking the epoch on every authenticated request would mean a second round trip on top of loading the session. Backends cache it per process for `epoch_cache_ttl` seconds (default 5), which removes that read almost entirely:

```python
backend.epoch_cache_ttl = 5.0   # seconds; 0 disables the cache
backend.epoch_cache_max = 10000 # bound on cached users
```

Staleness costs very little here. `revoke_all()` deletes sessions through the index immediately, so the epoch is only the backstop for sessions the index did not reach, and a bump in *this* process drops the cached entry at once. Only a bump by another worker waits out the TTL. Set `epoch_cache_ttl = 0` if you need every revocation visible across all workers instantly and can afford the extra read.

### Session object

| Member | Description |
|---|---|
| dict API | `[]`, `get`, `pop`, `setdefault`, `update`, `clear`, `keys`, `values`, `items`, `in`, `len()`. Any mutation marks the session dirty. |
| `sid` | Current session id. |
| `user_id` | Bound user, or `None`. |
| `created_at` / `last_seen` | Unix timestamps. |
| `is_new` / `modified` | Whether this request created it, and whether it will be written back. |
| `regenerate()` | New session id, same data. Call on any privilege change. |
| `bind_user(user_id)` | Attach to a user, stamp the epoch, and regenerate the id. |
| `destroy()` | Delete server-side and clear the cookie. |
| `list_sessions()` | Every live session for this user. |
| `revoke_other_sessions()` | Sign out the user's other devices. |
| `revoke_all_sessions()` | Sign out everywhere including here. For password resets. |

Binding a session to a user means every authenticated request checks the epoch, but almost never against the backend: the [per-process cache](https://lcore.lusansapkota.com.np/#epoch-caching) above answers nearly all of them from memory, so this is not a second backend round trip per request in practice. Anonymous sessions skip the check entirely.

## Custom Middleware

Create custom middleware by subclassing `Middleware`. Set `phase = 'pre'` to run before routing (for auth, rate limiting, body inspection) or leave the default `'post'` to wrap the handler:

```python
from lcore import Middleware
import time

class TimingMiddleware(Middleware):
    name = 'timing'
    order = 2
    phase = 'post'        # v0.0.4: default, wraps the handler

    def __call__(self, ctx, next_handler):
        start = time.time()
        result = next_handler(ctx)
        duration = time.time() - start
        ctx.response.set_header('X-Response-Time',
            f'{duration*1000:.2f}ms')
        return result

app.use(TimingMiddleware())
```

### Short-Circuiting

Return a response early without calling `next_handler`:

```python
from lcore import Middleware, HTTPResponse

class AuthMiddleware(Middleware):
    name = 'auth'
    order = 5

    def __call__(self, ctx, next_handler):
        token = ctx.request.get_header('Authorization')
        if not token or not self.validate(token):
            ctx.response.status = 401
            return {'error': 'Unauthorized'}
        ctx.user = self.decode(token)
        return next_handler(ctx)

    def validate(self, token):
        return token.startswith('Bearer ')

    def decode(self, token):
        return {'sub': token.split(' ')[1]}
```

### Route-Specific Middleware

Apply middleware only to specific route patterns, or **skip** middleware on specific routes:

```python
# Only applies to /api/* routes
app.use(AuthMiddleware(), routes='/api/*')

# Multiple patterns
app.use(RateLimitMiddleware(), routes=['/api/*', '/webhook/*'])

# v0.0.4: skip middleware on a per-route basis
app.post('/api/login', callback=login, skip=['csrf'])
```

The `skip` parameter on routes now works for middleware (not just plugins). The route's `skiplist` is checked during post-routing middleware execution.

> **Security: be intentional about skip=['csrf']**
> CSRF exemption is appropriate for: webhooks from Stripe/GitHub (they can't send your CSRF token), login endpoints (the client doesn't have a token yet), and routes using Bearer token auth (not cookie-based, so CSRF is irrelevant). **Never** skip CSRF on state-changing endpoints that use cookie-based sessions those are exactly what CSRF protects. Audit your route table: if a route with `skip=['csrf']` transfers money, changes passwords, or modifies user data, you have a problem.

## Middleware Hooks

For a cleaner separation of concerns, use `MiddlewareHook` with explicit `pre()` and `post()` methods:

```python
from lcore import MiddlewareHook, HTTPResponse

class AuditHook(MiddlewareHook):
    name = 'audit'
    order = 3

    def pre(self, ctx):
        # Runs before the handler
        # Return HTTPResponse to short-circuit
        if ctx.request.path.startswith('/admin'):
            if not ctx.request.get_header('X-Admin-Key'):
                return HTTPResponse('Forbidden', status=403)

    def post(self, ctx, result):
        # Runs after the handler
        # Can modify and return the result
        log_access(ctx.request.path, ctx.response.status_code)
        return result

app.use(AuditHook())
```

| Method | Signature | Description |
|---|---|---|
| `pre(ctx)` | Returns `None` or `HTTPResponse` | Before handler. Return response to short-circuit. |
| `post(ctx, result)` | Returns the (possibly modified) result | After handler. Can transform the response. |

## Lifecycle Hooks

Hooks are lightweight callbacks fired at specific points during request processing:

```python
@app.hook('before_request')
def log_request():
    print(f'{request.method} {request.path}')

@app.hook('after_request')
def add_header():
    response.set_header('X-Powered-By', 'Lcore')
```

### All Hook Points

| Hook Name | Trigger Point | Direction |
|---|---|---|
| `before_request` | Before route matching | Forward |
| `after_request` | After response is built | Reversed |
| `on_request_start` | Very start of request handling | Forward |
| `on_auth_resolved` | After authentication resolves | Forward |
| `on_handler_enter` | Just before handler executes | Forward |
| `on_handler_exit` | Just after handler returns | Reversed |
| `on_response_build` | After response object is built | Reversed |
| `on_response_send` | Just before response is sent | Reversed |
| `on_module_mount` | When a sub-app is mounted | Forward |
| `on_module_request` | Request to a mounted module | Forward |
| `app_reset` | When app.reset() is called | Forward |
| `config` | When config changes | Forward |

> **Reversed Hooks**
> Hooks marked "Reversed" fire callbacks in reverse registration order (LIFO). This ensures cleanup hooks run in the opposite order of setup hooks.

### Programmatic Hook API

```python
# Register
app.add_hook('on_request_start', my_callback)

# Remove
app.remove_hook('on_request_start', my_callback)

# Trigger manually
results = app.trigger_hook('on_request_start')
```

### Module-Specific Hooks

Scope hooks to specific mounted sub-applications:

```python
# Fire only for requests to /api/* routes
app.add_module_hook('/api/', 'before_request', check_api_key)

# Decorator form
@app.module_hook('/admin/', 'after_request')
def admin_log():
    log_admin_action(request.path)
```

## Middleware Pipeline

The `MiddlewarePipeline` manages middleware execution order and caching:

- **Ordering**: Middleware is sorted by `order` attribute (lowest first)
- **Caching**: The global middleware chain is cached after first build and invalidated when middleware is added or removed
- **Route matching**: Middleware with `routes=` parameter is only included for matching paths

### Inspect the Stack

```python
for mw in app.show_middleware():
    print(f"[{mw['order']:3d}] {mw['name']:20s} {mw['type']}")

# [  0] body_limit           BodyLimitMiddleware
# [  1] request_id           RequestIDMiddleware
# [  3] cors                 CORSMiddleware
# [  5] security_headers     SecurityHeadersMiddleware
# [ 90] compression          CompressionMiddleware
```

### Remove Middleware

```python
# Remove by instance
cors = CORSMiddleware()
app.use(cors)
app.middleware.remove(cors)
```
