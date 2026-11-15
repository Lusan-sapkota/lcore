Source: https://lcore.lusansapkota.com.np/advanced.html

# Advanced Features

Dependency injection, module mounting, templates, security hardening, and production deployment.

## Dependency Injection

Lcore has a built-in dependency injection system with three lifetimes:

| Lifetime | Behavior | Use Case |
|---|---|---|
| `singleton` | One instance for the entire app lifetime | Redis connection, config cache |
| `scoped` | One instance per request, auto-cleaned | DB sessions, auth context |
| `transient` | New instance every access | Loggers, unique ID generators |

```python
from lcore import Lcore, ctx

app = Lcore()

# Singleton: created once, shared everywhere
class RedisCache:
    def __init__(self):
        self.store = {}
    def get(self, key):
        return self.store.get(key)
    def set(self, key, value):
        self.store[key] = value

app.inject('cache', RedisCache, lifetime='singleton')

# Scoped: one per request, .close() called automatically
class DBSession:
    def __init__(self):
        self.conn = create_connection()
    def query(self, sql):
        return self.conn.execute(sql)
    def close(self):
        self.conn.close()

app.inject('db', DBSession, lifetime='scoped')

# Transient: new each time
import uuid
app.inject('trace_id', lambda: str(uuid.uuid4()), lifetime='transient')

# Access in handlers via ctx
@app.route('/users')
def list_users():
    users = ctx.db.query('SELECT * FROM users')
    ctx.cache.set('last_query', 'users')
    return {'users': users, 'trace_id': ctx.trace_id}
```

> **Reserved names**
> `app.inject()` rejects a name that shadows a built-in `RequestContext` attribute or method (`request`, `response`, `app`, `route`, `request_id`, `user`, `state`, `lazy`, ...) — `ctx.<name>` would silently resolve to the built-in instead of your dependency. Pick a different name, as above.

> **Auto-Cleanup**
> Scoped dependencies with a `close()` method are automatically closed at the end of each request, even if an error occurs. This prevents resource leaks.

## Module Mounting

Build modular applications by mounting sub-apps under URL prefixes:

```python
# users.py
from lcore import Lcore

users_app = Lcore()

@users_app.route('/')
def list_users():
    return {'users': []}

@users_app.route('/<id:int>')
def get_user(id):
    return {'id': id}

@users_app.hook('before_request')
def auth_check():
    # Only runs for /api/users/* requests
    pass
```

```python
# app.py
from lcore import Lcore
from users import users_app
from products import products_app

app = Lcore()

# Mount sub-applications
app.mount('/api/users/', users_app)
app.mount('/api/products/', products_app)

# Mount hooks fire when sub-apps are mounted
@app.hook('on_module_mount')
def on_mount(prefix, child):
    print(f'Mounted {child} at {prefix}')

# Module-specific hooks from parent
@app.module_hook('/api/users/', 'after_request')
def log_user_api():
    log(f'User API: {request.path}')

app.run(port=8080)
```

### Mounting WSGI Apps

Mount any WSGI application, not just Lcore apps:

```python
# Mount a Flask app
from flask import Flask
flask_app = Flask(__name__)

app.mount('/legacy/', flask_app)
```

## Templates

### Built-in SimpleTemplate

```python
from lcore import template, view, TEMPLATE_PATH

# Add template search paths
TEMPLATE_PATH.insert(0, './templates')

@app.route('/hello/<name>')
def hello(name):
    return template('hello', name=name)

# Or use the @view decorator
@app.route('/page')
@view('page')
def page():
    return {'title': 'My Page', 'items': [1, 2, 3]}
```

SimpleTemplate syntax (`templates/hello.tpl`):

```python
<html>
<body>
  <h1>Hello, {{name}}!</h1>

  % for item in items:
    <p>Item: {{item}}</p>
  % end

  {{!raw_html}}  <!-- Unescaped output -->

  % include('footer')
</body>
</html>
```

### Jinja2 Integration

```python
from lcore import jinja2_template, jinja2_view

@app.route('/page')
def page():
    return jinja2_template('page.html',
        title='My Page',
        items=['a', 'b', 'c']
    )

# Or with decorator
@app.route('/dashboard')
@jinja2_view('dashboard.html')
def dashboard():
    return {'stats': get_stats()}
```

### Supported Engines

| Engine | Template Function | View Decorator | Requires |
|---|---|---|---|
| SimpleTemplate | `template()` | `@view()` | Built-in |
| Jinja2 | `jinja2_template()` | `@jinja2_view()` | `pip install jinja2` |
| Mako | `mako_template()` | `@mako_view()` | `pip install mako` |
| Cheetah | `cheetah_template()` | `@cheetah_view()` | `pip install cheetah3` |

## Request Context

The `ctx` object carries state across middleware and handlers for the current request:

```python
from lcore import ctx

@app.route('/info')
def info():
    return {
        'request_id': ctx.request_id,   # Set by RequestIDMiddleware
        'user': ctx.user,               # Set by auth middleware
        'method': ctx.request.method,
        'state': ctx.state,             # Arbitrary state dict
    }
```

### RequestContext Attributes

| Attribute | Type | Description |
|---|---|---|
| `ctx.request` | `BaseRequest` | Current request object |
| `ctx.response` | `BaseResponse` | Current response object |
| `ctx.app` | `Lcore` | Application instance |
| `ctx.route` | `Route` | Matched route object |
| `ctx.request_id` | `str` | Unique request ID |
| `ctx.user` | `any` | Authenticated user info |
| `ctx.state` | `dict` | Arbitrary per-request state |

### Lazy Attributes

```python
# Register a lazy-loaded attribute (computed on first access)
ctx.lazy('expensive_data', lambda: compute_expensive_thing())
```

## Built-in API Documentation

Lcore can serve auto-generated API documentation at any path, similar to FastAPI's `/docs`. The docs page lists all registered routes with their methods, parameters, types, and docstrings.

### Auto-enabled in Debug Mode

When you run with `debug=True`, the `/docs` and `/docs/json` endpoints are automatically available:

```python
from lcore import Lcore

app = Lcore()

@app.route('/users/<id:int>')
def get_user(id):
    '''Fetch a user by their numeric ID.'''
    return {'id': id}

@app.route('/users', method='POST')
def create_user():
    '''Create a new user account.'''
    return {'status': 'created'}

# debug=True auto-enables /docs
app.run(port=8080, debug=True)
```

### Explicit Enable (Production)

In production (`debug=False`), API docs are disabled by default for security. To explicitly enable them:

```python
# Enable at /docs (default)
app.enable_docs()

# Or use a custom path
app.enable_docs('/api-docs')
```

This creates two routes:

| Path | Description |
|---|---|
| `/docs` | Interactive HTML documentation page |
| `/docs/json` | Raw JSON API schema |

### Docstrings and Type Hints

The docs page automatically extracts information from your handler functions:

```python
@app.route('/items/<id:int>', method='GET')
def get_item(id: int) -> dict:
    '''Retrieve an item by its ID.

    Returns the full item object including metadata.'''
    return {'id': id, 'name': 'Widget'}

@app.route('/search')
def search(q: str = '', page: int = 1):
    '''Search items by keyword.'''
    return {'query': q, 'page': page, 'results': []}
```

The generated docs will display the method badges (GET, POST, PUT, DELETE), route patterns, parameter names with types and defaults, return types, and docstrings.

### Programmatic Access

```python
# Get docs data as a Python dict
docs = app.api_docs()

# Get as JSON string
json_str = app.api_docs_json()
```

> **Tip**
> The `/docs` and `/docs/json` routes are automatically hidden from the API docs output, so they won't clutter your documentation.

> **Security**
> API docs expose your route structure, parameter names, and docstrings. In production, only enable them behind authentication or on internal-facing ports. By default, they are only active when `debug=True`.

## Security

### HTTP Basic Authentication

The `@auth_basic` decorator protects routes with HTTP Basic Auth. It parses the `Authorization` header and calls your check function:

```python
from lcore import auth_basic

def check_credentials(username, password):
    # Return True to allow access, False to deny
    return username == 'admin' and password == 's3cret'

@app.route('/admin')
@auth_basic(check_credentials, realm='Admin Area')
def admin():
    return 'Welcome, admin!'

# With a database check
def db_check(username, password):
    user = db.find_user(username)
    return user and user.verify_password(password)

@app.route('/dashboard')
@auth_basic(db_check, realm='Dashboard')
def dashboard():
    return {'status': 'authenticated'}
```

| Parameter | Type | Description |
|---|---|---|
| `check` | `callable` | Function `(username, password) -> bool` |
| `realm` | `str` | Authentication realm shown in browser dialog |
| `text` | `str` | Custom error message for unauthorized access |

On failure, the decorator returns **401 Unauthorized** with a `WWW-Authenticate` header that prompts the browser for credentials.

### Rate Limiting

The `@rate_limit` decorator limits requests per client IP using a token bucket algorithm:

```python
from lcore import rate_limit

# 100 requests per 60 seconds per IP
@app.route('/api/data')
@rate_limit(100, per=60)
def data():
    return {'data': 'value'}

# Strict limit for expensive operations
@app.route('/api/search')
@rate_limit(20, per=60, max_buckets=10000)
def search():
    return {'results': []}

# Very strict for auth endpoints
@app.post('/api/login')
@rate_limit(5, per=300)  # 5 attempts per 5 minutes
def login():
    return {'token': 'abc'}
```

| Parameter | Type | Description |
|---|---|---|
| `limit` | `int` | Maximum requests allowed in the time window |
| `per` | `int` | Time window in seconds |
| `max_buckets` | `int` | Maximum tracked IPs before oldest are evicted (in-process mode). Default: 10000 |
| `backend` | `RateLimitBackend or None` | Pass a `RedisRateLimitBackend` (or any `RateLimitBackend` subclass) for cross-worker enforcement. Default: `None` (in-process token bucket). |

When the limit is exceeded, the client receives **429 Too Many Requests**. The in-process backend uses a token bucket with automatic stale-entry cleanup and **64-stripe locking** to minimise thread contention.

> **Multi-worker deployment warning**
> Running a single worker? Pass `rate_limit(5, single_process=True)` to silence the startup warning. Counters live in memory, so a restart resets them; use `RedisRateLimitBackend` if limits must survive restarts.
> The default in-process backend stores token buckets in **process memory**. Under a multi-worker server (e.g. `gunicorn -w 4`), each worker has its own independent buckets. A single client can make `N × limit` requests before being blocked (N = number of workers), making per-process limiting ineffective for abuse prevention.   
>   
>  **Fix:** Lcore ships a built-in `RedisRateLimitBackend` that is shared across all workers via Redis. Install the Redis client, then wire it in:
> ```bash
> uv add redis
> ```
> ```python
> from lcore import RedisRateLimitBackend, rate_limit
>
> # Create once at module level  the connection pool is reused.
> _rl = RedisRateLimitBackend(
>     redis_url='redis://localhost:6379/0',  # or rediss:// for TLS
>     prefix='myapp:rl:',
> )
>
> # Now the limit is enforced across every worker process.
> @app.post('/api/login')
> @rate_limit(5, per=300, backend=_rl)   # 5 per 5 min, shared
> def login():
>     ...
>
> # Works on any endpoint  each endpoint gets its own Redis keys.
> @app.post('/api/register')
> @rate_limit(10, per=3600, backend=_rl)
> def register():
>     ...
> ```
> The backend uses an atomic Lua script (Redis `INCR` + `EXPIRE` in one round-trip), so there are no race conditions between workers. If Redis is temporarily unavailable it **fails open** (allows the request) and logs a warning so a Redis outage does not take your app down.   
>   
>  **Temporary workaround** (no Redis): divide your intended limit by the number of workers: `@rate_limit(5 // num_workers, per=300)`.

### Custom Rate-Limit Backends

You can implement any storage back-end by subclassing `RateLimitBackend`. Only one method is required:

```python
from lcore import RateLimitBackend, rate_limit

class MemcacheRateLimitBackend(RateLimitBackend):
    def __init__(self, client):
        self._mc = client

    def consume(self, key, limit, per):
        """Atomic increment. Return True = allow, False = block."""
        full_key = 'rl:' + key
        count = self._mc.incr(full_key, noreply=False)
        if count is None:  # key did not exist
            self._mc.set(full_key, 1, expire=int(per))
            count = 1
        return count <= limit

    def close(self):
        self._mc.close()

mc_backend = MemcacheRateLimitBackend(my_memcache_client)

@app.post('/api/login')
@rate_limit(5, per=300, backend=mc_backend)
def login():
    ...
```

### Request Validation

The `@validate_request` decorator validates incoming request data against a schema. v0.0.4 adds `Optional[type]` support, automatic type coercion, whitespace stripping, and structured JSON error responses.

#### Basic body validation

```python
from lcore import validate_request

@app.post('/api/users')
@validate_request(body={'name': str, 'email': str, 'age': int})
def create_user():
    data = request.json       # guaranteed valid and stripped
    return {'created': True, 'name': data['name']}
```

#### Optional fields (v0.0.4)

Use `Optional[type]` from `typing` for fields that may be absent. Required fields raise 422 when missing; optional ones are silently skipped:

```python
from typing import Optional

@app.post('/api/profile')
@validate_request(body={
    'name': str,              # required
    'email': str,             # required
    'bio': Optional[str],     # optional  no error if absent
    'age': Optional[int],     # optional, coerced to int if present
})
def update_profile():
    data = request.json
    return {'updated': True}
```

#### Auto-coercion and whitespace stripping (v0.0.4)

Values are automatically coerced and cleaned. No more `int(data['age'])` or `.strip()` boilerplate in every handler:

```python
# Client sends: {"name": "  Alice  ", "age": "42", "active": "true"}
@validate_request(body={'name': str, 'age': int, 'active': bool})
def handler():
    data = request.json
    # data['name'] is "Alice" (stripped)
    # data['age'] is 42 (int, coerced from string)
    # data['active'] is True (bool, from "true" / "1" / "yes")
    return {'ok': True}
```

#### Structured error responses (v0.0.4)

Validation failures return a JSON body with per-field error messages instead of a flat semicolon-separated string:

```python
# When validation fails, the client gets:
# HTTP 422
# {
#   "error": "Validation failed",
#   "fields": {
#     "email": "email is required",
#     "age": "age must be int"
#   }
# }
```

#### Query parameter validation

```python
@app.get('/api/search')
@validate_request(query={'q': str, 'page': int, 'limit': int})
def search():
    q = request.query.get('q')
    page = int(request.query.get('page', 1))
    return {'query': q, 'page': page}

# Validate both body and query
@app.post('/api/items')
@validate_request(
    body={'name': str, 'price': float},
    query={'category': str}
)
def create_item():
    return {'created': True}
```

Error status codes:

| Error | Status | When |
|---|---|---|
| Missing query param | `400 Bad Request` | Required query parameter is absent |
| Invalid body | `422 Unprocessable Entity` | Body fields missing or wrong type |
| Invalid JSON | `400 Bad Request` | Body is not valid JSON |

### Security Middleware Stack

```python
from lcore import (
    ProxyFixMiddleware, TimeoutMiddleware,
    SecurityHeadersMiddleware, CSRFMiddleware,
    CORSMiddleware, BodyLimitMiddleware
)

# Recommended production security stack (order matters  lower order = earlier)
app.use(ProxyFixMiddleware(trusted_proxies=['10.0.0.1']))  # MUST be first
app.use(TimeoutMiddleware(timeout=30))                     # 503 after 30 s
app.use(BodyLimitMiddleware(max_size=10 * 1024 * 1024))
app.use(SecurityHeadersMiddleware(hsts=True))
app.use(CORSMiddleware(
    allow_origins=['https://myapp.com'],
    allow_credentials=True
))
app.use(CSRFMiddleware(secret='your-csrf-secret'))
```

### Security Features Summary

| Feature | Protection |
|---|---|
| Signed cookies | HMAC-SHA256 + JSON (no pickle) |
| Timing-safe comparison | `hmac.compare_digest` |
| Path traversal | v0.0.4: file opened before checks, real path resolved from fd via `/proc/self/fd` on Linux TOCTOU-safe |
| Dotenv injection | Regex validation of env var key names; quote stripping uses pair-matching only |
| Dynamic loading | Safe `getattr` chain with `isidentifier()` |
| Security headers | X-Frame-Options, CSP, HSTS, XSS protection |
| Trusted proxy headers | `ProxyFixMiddleware` only trusts X-Forwarded-For / X-Forwarded-Proto from whitelisted proxy IPs; prevents IP spoofing and URL manipulation |
| Request timeouts | `TimeoutMiddleware` persistent thread pool returns 503 after deadline; protects workers from slow-client exhaustion |
| CSRF tokens | HMAC-signed double-submit cookie; signing prevents subdomain cookie-tossing bypass |
| Body limits | 413 error on oversized requests via `BodyLimitMiddleware`. v0.0.4: multipart `disk_limit` tied to same limit no separate ceiling |
| Rate limiting | Token bucket with memory cleanup. Per-process by default pass `backend=` for cross-worker enforcement |
| Slow-loris mitigation | v0.0.4: chunked transfer parser uses buffered reads no byte-by-byte header scanning |
| Cookie defaults | v0.0.4: `set_cookie()` defaults to `samesite='Lax'`, `httponly=True`. Override for JS-readable cookies like CSRF tokens |
| File upload safety | v0.0.4: `FileUpload.save()` uses atomic `'x'` exclusive-create mode (no TOCTOU). Multipart filenames sanitized at parse time with `os.path.basename` |
| ETag hashing | SHA256 (not SHA1) |
| Password hashing | PBKDF2-SHA256 with random salt |
| Header injection | Newlines stripped from Content-Disposition filenames; CRLF rejected in all header/cookie setters |
| Form field DoS | Max 1,000 fields per request (prevents memory exhaustion) |
| CORS validation | `allow_credentials=True` rejects wildcard origins |
| Graceful shutdown | SIGTERM handled for container/orchestrator compatibility |
| Thread-safe singletons | DependencyContainer uses locking for singleton resolution |

### Password Hashing

Lcore provides secure password hashing using PBKDF2-SHA256 with automatic random salting. Zero external dependencies:

```python
from lcore import hash_password, verify_password

# Hash a password (during registration)
hashed = hash_password('user_password_123')
# Output: 'pbkdf2:sha256:600000$a1b2c3...$d4e5f6...'

# Verify a password (during login)
if verify_password(request.json['password'], stored_hash):
    return {'token': generate_token(user)}

# Custom iteration count (higher = slower but more secure)
hashed = hash_password('password', iterations=800000)

# In tests only: a low count keeps the suite fast (default 600000 takes ~0.3s per call)
hashed = hash_password('password', iterations=1000)
```

| Function | Signature | Description |
|---|---|---|
| `hash_password` | `(password, iterations=600000)` | Hash password with PBKDF2-SHA256. Returns formatted hash string with embedded salt. |
| `verify_password` | `(password, hash_string)` | Verify password against stored hash. Timing-safe comparison. |

> **Storage Format**
> `pbkdf2:sha256:iterations$salt_hex$hash_hex` each hash includes its own random 32-byte salt, so identical passwords produce different hashes.

## Testing

Lcore includes a built-in WSGI test client for unit and integration testing without starting a live server:

```python
from lcore import Lcore, TestClient

app = Lcore()

@app.route('/api/users/<id:int>')
def get_user(id):
    return {'id': id, 'name': 'Alice'}

# Create test client
client = TestClient(app)

# GET request
resp = client.get('/api/users/1')
assert resp.status_code == 200
assert resp.json['name'] == 'Alice'

# POST with JSON body
resp = client.post('/api/items', json={'name': 'Widget', 'price': 9.99})
assert resp.status_code == 200

# Custom headers
resp = client.get('/api/data', headers={'Authorization': 'Bearer token123'})

# Query strings
resp = client.get('/search', query_string='q=hello&page=1')
```

`TestClient(app)` keeps a cookie jar (`client.cookies`): a login's `Set-Cookie` is sent on later calls automatically. Use `TestClient(app, cookies=False)` to turn it off, and `TestClient(app, follow_redirects=True)` to follow redirects (up to 10, same app only). `resp.get_all('Set-Cookie')` returns every repeated header value.

### TestClient Methods

| Method | Description |
|---|---|
| `client.get(path, **kw)` | Send GET request |
| `client.post(path, json=None, body=b'', **kw)` | Send POST request (auto-sets Content-Type for JSON) |
| `client.put(path, **kw)` | Send PUT request |
| `client.patch(path, **kw)` | Send PATCH request |
| `client.delete(path, **kw)` | Send DELETE request |
| `client.head(path, **kw)` | Send HEAD request |
| `client.options(path, **kw)` | Send OPTIONS request |

### TestResponse Properties

| Property | Type | Description |
|---|---|---|
| `.status` | `str` | Full status line, e.g. `"200 OK"` |
| `.status_code` | `int` | HTTP status code, e.g. `200` |
| `.headers` | `dict` | Response headers |
| `.body` | `bytes` | Raw response body |
| `.text` | `str` | Response body decoded as UTF-8 |
| `.json` | `dict/list` | Response body parsed as JSON |

## Background Tasks

Lcore includes a thread-pool for running work in the background without blocking requests:

```python
from lcore import Lcore, BackgroundTaskPool, on_shutdown

app = Lcore()
tasks = BackgroundTaskPool(max_workers=4)

def send_welcome_email(email):
    import time; time.sleep(2)  # Simulate slow SMTP
    print(f"Email sent to {email}")

@app.post('/api/users')
def create_user():
    data = request.json
    user_id = db.insert('users', data)

    # Fire-and-forget: returns immediately
    tasks.submit(send_welcome_email, data['email'])

    return {'id': user_id, 'created': True}

# Graceful shutdown
@on_shutdown
def cleanup():
    tasks.shutdown(wait=True)
```

### BackgroundTaskPool API

| Method / Property | Description |
|---|---|
| `BackgroundTaskPool(max_workers=4)` | Create a pool with the given number of worker threads |
| `.submit(fn, *args, **kwargs)` | Queue a function for background execution. Returns `concurrent.futures.Future` |
| `.pending` | Number of tasks still running or queued |
| `.shutdown(wait=True)` | Shut down the pool. If `wait=True`, blocks until all tasks complete |

> **Thread Safety**
> Background tasks run in separate threads. Ensure database connections and shared state are thread-safe. Create new DB connections inside task functions rather than sharing request-scoped ones.

## Production Deployment

```python
from lcore import (
    Lcore, request, response, ctx, on_shutdown,
    RequestIDMiddleware, RequestLoggerMiddleware,
    SecurityHeadersMiddleware, CORSMiddleware,
    BodyLimitMiddleware
)
import logging

app = Lcore()

# Load config from environment
app.config.load_env('MYAPP_', strip_prefix=True)

# Production middleware stack
app.use(BodyLimitMiddleware(max_size=5 * 1024 * 1024))
app.use(RequestIDMiddleware())
app.use(RequestLoggerMiddleware(logger=logging.getLogger('http')))
app.use(SecurityHeadersMiddleware(hsts=True))
app.use(CORSMiddleware(
    allow_origins=app.config.get('cors_origins', 'https://myapp.com').split(','),
    allow_credentials=True
))

# Dependency injection
app.inject('db', create_session, lifetime='scoped')
app.inject('cache', create_redis, lifetime='singleton')

# Lifecycle hooks
@app.hook('on_request_start')
def set_timer():
    import time
    ctx.state['start_time'] = time.time()

@app.hook('on_response_send')
def log_duration():
    import time
    duration = time.time() - ctx.state.get('start_time', 0)
    response.set_header('X-Response-Time', f'{duration*1000:.1f}ms')

# Graceful shutdown
@on_shutdown
def cleanup():
    close_db_pool()
    flush_cache()

# Routes
@app.route('/health', skip=True)
def health():
    return {'status': 'ok'}

@app.route('/api/data')
def data():
    return ctx.db.query('SELECT * FROM data')

# Run with Gunicorn
app.run(server='gunicorn', host='0.0.0.0', port=8080)
```

> **Production Checklist**
> 1. Use a production server (Gunicorn, Waitress, Gevent)  
>  2. Set `debug=False` (default) debug mode exposes tracebacks to users  
>  3. Add `ProxyFixMiddleware(trusted_proxies=[...])` when behind a reverse proxy prevents IP spoofing and wrong-scheme URLs  
>  4. Prefer your process manager and reverse proxy for request timeouts (Gunicorn's `timeout`, nginx's `proxy_read_timeout`) see [Request Timeouts](https://lcore.lusansapkota.com.np/#request-timeouts) below. Reach for `TimeoutMiddleware(timeout=30)` only for per-route limits or when nothing in front of the app enforces one  
>  5. Enable HSTS and security headers via `SecurityHeadersMiddleware`  
>  6. Configure CORS with **explicit origins** never use `'*'` with `allow_credentials=True`  
>  7. Set body size limits via `BodyLimitMiddleware`  
>  8. Register shutdown hooks with `@on_shutdown` for cleanup  
>  9. Use signed cookies with a strong secret  
>  10. Load config from environment variables, not hardcoded  
>  11. Use `hash_password()` / `verify_password()` never store plaintext passwords  
>  12. Set `secure=True` on CSRF cookies when serving over HTTPS  
>  13. Enable gzip compression via `CompressionMiddleware`  
>  14. Enable request ID tracking via `RequestIDMiddleware`  
>  15. **Multi-worker rate limiting:** pass a shared `backend=` to `@rate_limit` (e.g. Redis) the default in-process store gives each worker its own buckets, making the effective limit `N × limit`

> **Zero Dependencies**
> Lcore is built entirely on Python's standard library. No `pip install` required beyond Lcore itself. Every module it uses `hashlib`, `gzip`, `json`, `concurrent.futures`, `threading`, `asyncio`, `logging` ships with Python 3.8+. It works anywhere Python runs: containers, serverless, air-gapped networks.

## Request Timeouts

`TimeoutMiddleware` (see [Middleware](https://lcore.lusansapkota.com.np/middleware.html#timeoutmiddleware)) runs each request in a thread pool and can't actually kill a stuck handler — Python can't kill a thread — so on timeout it hands the client a 503 while the original thread keeps running to completion in the background. It also has a measured per-request cost (roughly 30µs vs. a ~9µs bare route), because `request`/`response` have to be marshaled across the thread boundary on every call, timed out or not. For most deployments, two things outside the Python process do this job better:

### Gunicorn's own `timeout`

Gunicorn's master process watches each worker and **kills and restarts the OS process** — not just abandons a thread — if it goes silent longer than `timeout` seconds (default 30). That's a real fix for a truly stuck handler, which `TimeoutMiddleware` cannot provide on its own.

```python
# CLI
gunicorn -w 4 --timeout 30 -b 0.0.0.0:8080 myapp:app

# Or via app.run()
app.run(server='gunicorn', host='0.0.0.0', port=8080, workers=4, timeout=30)
```

### Your reverse proxy's timeout

nginx, Caddy, Traefik, an ALB, or whatever sits in front of the app closes the client-facing connection on its own schedule, independent of what the Python process is doing, at zero per-request cost to your app. For nginx:

```python
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_connect_timeout 5s;
    proxy_send_timeout    30s;
    proxy_read_timeout    30s;
}
```

### Async, for I/O-bound handlers

If handlers spend most of their time waiting on I/O (a slow upstream API, a database), an async-capable server adapter (`gevent`, `eventlet`) lets many in-flight requests share a worker instead of blocking one thread each — a concurrency fix, not a timeout mechanism, but it addresses the same "slow client/slow backend" problem from a different angle and pairs well with a Gunicorn/proxy timeout instead of `TimeoutMiddleware`.

> **When TimeoutMiddleware still earns its cost**
> Reach for it when you need a limit tighter than the process-manager/proxy timeout for one specific route (e.g. a route calling a flaky third-party API that should fail fast at 5s while the rest of the app keeps a 30s ceiling), or when the app is exposed directly with no reverse proxy and no process manager providing one. Scope it with `routes=` rather than installing it globally, and treat Gunicorn's `timeout` and your proxy's read timeout as the backstop either way — they're what actually reclaims a truly stuck worker.

## Hot Reload

### Built-in Reloader

```python
# Polls files for changes (no dependencies required)
app.run(reloader=True, interval=1)
```

### WatchdogReloader

```python
from lcore import WatchdogReloader

reloader = WatchdogReloader(
    app,
    paths=['./'],       # Directories to watch
    interval=1,         # Check interval (seconds)
    callback=None       # Optional callback on change
)
reloader.start()
# ... later
reloader.stop()
```

### AsyncReloader

```python
from lcore import AsyncReloader
import asyncio

reloader = AsyncReloader(
    app,
    paths=['./'],
    interval=1.0,
    callback=lambda: print('File changed!')
)

loop = asyncio.get_event_loop()
reloader.start(loop=loop)
```

## Server Adapters

Lcore includes 20+ server adapters. Use the `server` parameter to select one:

| Name | Package | Features |
|---|---|---|
| `wsgiref` | Built-in | Development only, single-threaded |
| `gunicorn` | `gunicorn` | Production, multi-worker, pre-fork |
| `waitress` | `waitress` | Production, Windows-compatible, multi-threaded |
| `gevent` | `gevent` | Async via coroutines, high concurrency |
| `eventlet` | `eventlet` | Async via green threads |
| `cheroot` | `cheroot` | CherryPy's production server |
| `tornado` | `tornado` | Async I/O server |
| `twisted` | `twisted` | Event-driven networking |
| `meinheld` | `meinheld` | Ultra-fast C-based WSGI |
| `bjoern` | `bjoern` | Ultra-fast C-based WSGI |
| `aiohttp` | `aiohttp` | asyncio-based |
| `paste` | `paste` | Multi-threaded |
| `auto` | Any available | Auto-selects best available adapter |

```python
# Auto-select best available server
app.run(server='auto', host='0.0.0.0', port=8080)

# Gunicorn with workers
app.run(server='gunicorn', host='0.0.0.0', port=8080, workers=4)

# Gevent with high concurrency
app.run(server='gevent', host='0.0.0.0', port=8080)

# Or run directly with gunicorn CLI
# gunicorn -w 4 -b 0.0.0.0:8080 myapp:app
```
