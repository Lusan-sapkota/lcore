Source: https://lcore.lusansapkota.com.np/getting-started.html

# Getting Started

Everything you need to build your first Lcore microservice, from installation to deployment.

## Installation

Lcore requires **Python 3.8+** and has **zero required dependencies**. The entire framework is a single file you can drop into any project. Every module Lcore uses ships with Python itself no `pip install` needed beyond Lcore.

### Via uv (recommended)

```bash
uv add lcore          # add to project
uv pip install lcore  # install globally
```

### Via pip

```bash
pip install lcore
```

### Via curl (single file)

Since Lcore is a single Python file, you can simply copy `lcore.py` into your project directory:

```bash
curl -O https://raw.githubusercontent.com/Lusan-sapkota/lcore/main/lcore.py
```

### Standard Library Only

Lcore is built entirely on Python's standard library. Here's what powers it under the hood all included with every Python installation:

| Module | Used For |
|---|---|
| `hashlib`, `hmac` | Password hashing (PBKDF2-SHA256), cookie signing, CSRF tokens |
| `gzip` | Response compression middleware |
| `json` | JSON serialization/deserialization |
| `concurrent.futures` | Background task pool (ThreadPoolExecutor) |
| `threading` | Thread-local request/response, concurrency safety |
| `asyncio` | Async route handler support |
| `http.cookies` | Cookie parsing and formatting |
| `mimetypes` | Static file content type detection |
| `re` | Route pattern matching and URL parsing |
| `logging` | Structured request logging middleware |
| `os`, `sys`, `time`, `uuid` | Core utilities, request IDs, file serving |

This means Lcore works anywhere Python runs containers, serverless, air-gapped networks, embedded systems with zero network access needed for dependencies.

### Optional Dependencies

| Package | Purpose |
|---|---|
| `ujson` | Faster JSON parsing (auto-detected, falls back to stdlib `json`) |
| `watchdog` | Efficient file watching for hot reload |
| `jinja2` | Jinja2 template engine support |
| `mako` | Mako template engine support |
| `gunicorn` | Production WSGI server (Linux/macOS) |
| `waitress` | Production WSGI server (Windows-compatible) |
| `gevent` | Async WSGI server with coroutines |
| `eventlet` | Alternative async WSGI server |

## Your First App

### Hello World

```python
from lcore import Lcore

app = Lcore()

@app.route('/')
def index():
    return 'Hello, World!'

app.run(port=8080)
```

Save this as `app.py` and run it:

```bash
python app.py
```

Visit `http://localhost:8080` to see your app running.

### Classic single-file style

If you'd rather not create an `Lcore()` instance explicitly, `from lcore import *` exports the whole public API including `route`/`get`/`post`/`put`/`delete`/`patch`/`mount`/`hook`/`use` and `run` as shortcuts bound to a default app instance:

```python
from lcore import *

@route('/')
def index():
    return 'Hello, World!'

run(port=8080)
```

Both styles produce the same app; the explicit `app = Lcore()` form scales better once you have more than one app or need to mount sub-apps, but the shortcuts are there for small scripts. `__all__` lists exactly what a wildcard import brings in it deliberately excludes the stdlib modules (`os`, `re`, `time`, ...) that Lcore itself imports, so `from lcore import *` won't shadow your own.

### JSON API

Return a `dict` from any handler and Lcore automatically serializes it as JSON with the correct `Content-Type`:

```python
from lcore import Lcore, request, abort

app = Lcore()

users = {1: {'name': 'Alice'}, 2: {'name': 'Bob'}}

@app.route('/api/users/<id:int>')
def get_user(id):
    if id not in users:
        abort(404, 'User not found')
    return users[id]

@app.route('/api/users', method='POST')
def create_user():
    data = request.json
    new_id = max(users.keys()) + 1
    users[new_id] = data
    return {'id': new_id, 'created': True}

app.run(port=8080, debug=True)
```

> **Tip**
> The `debug=True` flag enables detailed error pages and auto-reloading. Never use it in production.

### What Happens Under the Hood

1. Lcore compiles your route patterns into an optimized regex-based router
2. A WSGI server (default: `wsgiref`) starts listening on the given host/port
3. For each request, the router matches the URL and dispatches to your handler
4. The response is processed through plugins (JSON serialization, templates) and middleware
5. The WSGI response is sent back to the client

## Core Concepts

### WSGI Application

Lcore is a standard **WSGI application**. The `Lcore` class is callable and can be used with any WSGI server:

```python
# Use with any WSGI server
from lcore import Lcore
app = Lcore()

# app is a WSGI callable: app(environ, start_response)
# Use with gunicorn: gunicorn app:app

# Note: async def handlers are accepted but block the worker thread. See warning below.
@app.route('/async')
async def async_handler():
    # Pure CPU-only coroutines are fine; any I/O await will deadlock or stall
    return {'result': 'ok'}
```

> **async def handlers - WSGI constraint**
> Lcore is a **WSGI** framework, not ASGI. When you use an `async def` route handler, Lcore calls `asyncio.run()` in a dedicated thread. This means:
> - **The worker thread is blocked** for the entire duration of the coroutine.
> - **No concurrency benefit.** Async I/O does not parallelize requests.
> - **Loop-bound libraries will not work:** `aiohttp`, `httpx`, `asyncpg`, `motor`, and similar libraries require a persistent event loop and will malfunction or deadlock inside Lcore handlers.
> Lcore emits a `UserWarning` naming the route the first time it's actually invoked. For genuine async I/O concurrency, see the note below or use an ASGI framework (FastAPI, Starlette, Quart) in the meantime. [Full details](https://lcore.lusansapkota.com.np/routing.html#async-routes)

> **Want concurrency, not necessarily async/await?**
> If what you actually need is "don't let one slow request block everything else" rather than event-loop syntax specifically, Lcore already provides that: run under the `gevent` or `eventlet` server adapter with completely ordinary synchronous handlers, no code changes. Measured: 200 concurrent 0.2s-each requests took 2.07s on a 20-thread server (linear backlog once concurrency outgrows the thread pool) vs. 0.58s under `gevent`, same app, same handler. [Details and numbers](https://lcore.lusansapkota.com.np/routing.html#async-routes)

> **Coming Soon: `lcore-asgi`**
> A new companion library, **`lcore-asgi`**, is in development and will unlock full ASGI support for the Lcore ecosystem:
> - **WebSockets** - real-time bidirectional communication
> - **True async concurrency** - persistent event loop, non-blocking I/O
> - **Async library compatibility** - `asyncpg`, `httpx`, `aiohttp`, `motor`, and others will work correctly
> - **HTTP/2 and Server-Sent Events**
> - **Familiar API** - same routing, middleware, hooks, and plugin model as Lcore WSGI

### Thread-Local Objects

Lcore provides thread-local proxy objects that are safe to use in multi-threaded servers:

```python
from lcore import request, response, ctx

@app.route('/example')
def example():
    # request - current HTTP request (read-only)
    method = request.method
    ip = request.remote_addr

    # response - outgoing HTTP response (writable)
    response.content_type = 'application/json'
    response.set_header('X-Custom', 'value')

    # ctx - request context (carries state across middleware)
    ctx.state['processed'] = True
    user = ctx.user  # set by auth middleware

    return {'method': method, 'ip': ip}
```

### Request Lifecycle

Every request flows through this pipeline. v0.0.4 introduces a **pre-routing middleware phase** that runs before the router:

```python
Incoming Request
    |
    v
on_request_start hook
    |
    v
Pre-routing Middleware (CORS, CSRF, body limits)
    |  Runs BEFORE the router  can short-circuit
    |  (e.g. CORS preflight returns 204 without hitting a route)
    v
Router matches URL -> Route
    |
    v
on_auth_resolved hook
    |
    v
on_handler_enter hook
    |
    v
Post-routing Middleware + Plugin chain + Handler
    |
    v
on_handler_exit hook
    |
    v
on_response_build hook
    |
    v
on_response_send hook
    |
    v
Response sent to client
```

### Plugins vs Middleware

| Feature | Plugins | Middleware |
|---|---|---|
| Scope | Wraps individual route callbacks | Wraps the entire request pipeline |
| Access | Route config, callback function | Full request context (`ctx`) |
| Use case | JSON serialization, template rendering | Auth, CORS, logging, rate limiting |
| Registration | `app.install(plugin)` | `app.use(middleware)` |

## Configuration

Every Lcore app has a `config` attribute backed by `ConfigDict`, a powerful configuration store with metadata, overlays, and validation.

### Basic Usage

```python
app = Lcore()

# Direct assignment
app.config['debug'] = True
app.config['my_app.db_url'] = 'sqlite:///data.db'
app.config['my_app.secret_key'] = 'change-me'
```

### Loading Configuration

```python
# From a Python dict
app.config.load_dict({
    'debug': True,
    'my_app': {
        'db_url': 'sqlite:///data.db',
        'secret_key': 'change-me'
    }
})

# From environment variables (MYAPP_DB_URL -> db_url)
app.config.load_env('MYAPP_', strip_prefix=True)

# From a .env file
app.config.load_dotenv('.env')

# From a JSON file
app.config.load_json('config.json')

# From an INI file
app.config.load_config('settings.ini')
```

### Config Validation

```python
from dataclasses import dataclass

@dataclass
class AppConfig:
    debug: bool = False
    db_url: str = 'sqlite:///data.db'
    max_upload: int = 10_000_000

app.config.load_dict({'debug': True, 'db_url': 'postgres://...'})
valid, errors = app.config.validate_config(AppConfig)
if not valid:
    print('Config errors:', errors)
```

> **Note**
> Configuration keys use dot notation for namespacing: `my_app.db_url`. When loading from dicts, nested dicts are flattened automatically.

### Automatic .env Loading

v0.0.4 auto-loads `.env` from the current directory when you call `app.run()`. No extra setup needed:

```python
# .env file in your project root
DB_PATH=./data.db
SECRET_KEY=super-secret
CORS_ORIGINS=https://myapp.com

# In your app  values are already in os.environ
import os
db_path = os.environ.get('DB_PATH')  # './data.db'
```

You can also call it explicitly: `from lcore import load_dotenv; load_dotenv()`

### Error Format

Set `error.format` to `'json'` and all errors return JSON instead of HTML. Perfect for pure API servers:

```python
app.config['error.format'] = 'json'
# Now 404, 500, 403, etc. all return:
# {"error": "Not found: '/x'", "status": 404}

# Even without this setting, requests sending Accept: application/json get
# JSON errors (404, 500 and abort() alike); browsers still get the HTML page.
```

### Proxy Trust

Behind nginx or a load balancer? Set `proxy.trusted` so `request.remote_addr` returns the real client IP:

```python
app.config['proxy.trusted'] = ['127.0.0.1', '10.0.0.1']
# or as a comma-separated string:
app.config['proxy.trusted'] = '127.0.0.1,10.0.0.1'
```

> **Security: only trust your actual proxy**
> `proxy.trusted` tells `request.remote_addr` to walk `X-Forwarded-For` from the right, skipping IPs in the trusted set. **Only list your upstream reverse proxy** Nginx on 127.0.0.1, Cloudflare's edge IPs, your AWS ALB. Never add arbitrary IPs. An attacker outside your trusted set who sends a fake `X-Forwarded-For: 1.1.1.1` will be ignored only the real `REMOTE_ADDR` is used for untrusted clients.

## Running Your App

### Development

```python
# Auto-reload on file changes + detailed error pages
app.run(host='localhost', port=8080, debug=True, reloader=True)
```

### Production

`app.run()` defaults to `wsgiref`, a single-threaded **development** server. `run()` refuses to serve it on a non-loopback host unless you pass `debug=True` or `dev_server_ok=True`. Do not expose it to the internet; use gunicorn or waitress behind a reverse proxy.

```python
# With Gunicorn (recommended for Linux/macOS)
app.run(server='gunicorn', host='0.0.0.0', port=8080)

# With Waitress (Windows-compatible)
app.run(server='waitress', host='0.0.0.0', port=8080)

# With Gevent (async)
app.run(server='gevent', host='0.0.0.0', port=8080)

# Or use gunicorn directly from CLI:
# gunicorn -w 4 -b 0.0.0.0:8080 app:app
```

### Server Adapters

Lcore supports **20+ server adapters** out of the box. Use `server='auto'` to automatically pick the best available:

```python
app.run(server='auto', host='0.0.0.0', port=8080)
```

> **Warning**
> The default `wsgiref` server is single-threaded and intended for development only. Always use a production server like Gunicorn or Waitress for deployment.

### Hot Reload

```python
from lcore import WatchdogReloader

# Watchdog-based (efficient, requires watchdog package)
reloader = WatchdogReloader(app, paths=['./'], interval=1)
reloader.start()

# Or use the built-in reloader flag
app.run(reloader=True)
```

## Command-Line Interface

Lcore can be run directly as a Python module with command-line options:

```python
# Basic usage
python -m lcore myapp

# With options
python -m lcore myapp -b 0.0.0.0:8080 -s gunicorn --debug --reload
```

### CLI Options

| Flag | Description |
|---|---|
| `--version` | Show Lcore version |
| `-b, --bind ADDRESS` | Bind address (host:port) |
| `-s, --server NAME` | WSGI server backend (default: wsgiref) |
| `-p, --plugin MODULE` | Load a plugin module |
| `-c, --conf FILE` | Load configuration from a config file |
| `-C, --param KEY=VALUE` | Override a config parameter |
| `--debug` | Enable debug mode |
| `--reload` | Auto-reload on file changes |
| `--docs` | Open documentation website in browser |

The CLI also accepts `.py` file paths directly:

```python
# All of these work
python -m lcore app
python -m lcore app.py
python -m lcore app:app
python -m lcore mypackage.app:application
```

### Built-in API Documentation

When running in debug mode, Lcore automatically serves interactive API documentation at `/docs`, similar to FastAPI:

```python
from lcore import Lcore

app = Lcore()

@app.route('/users/<id:int>')
def get_user(id):
    '''Fetch a user by ID.'''
    return {'id': id}

app.run(port=8080, debug=True)
# /docs and /docs/json are now available
```

Visit `http://localhost:8080/docs` to see the auto-generated API reference, or `/docs/json` for the raw JSON data.

> **Production**
> API docs are only auto-enabled in debug mode. In production, call `app.enable_docs()` explicitly if you want to expose them.

## Project Structure

### Simple Microservice

```python
my-service/
  app.py          # Main application
  lcore.py        # Framework (single file)
  config.json     # Configuration
  .env            # Environment variables
  tests/
    test_app.py   # Tests
```

### Multi-Module Service

```python
my-service/
  app.py              # App setup & middleware
  config.py           # Configuration loading
  lcore.py            # Framework
  modules/
    __init__.py
    users.py          # Users sub-app (mounted)
    products.py       # Products sub-app (mounted)
    auth.py           # Auth middleware
  templates/
    error.html
  tests/
    test_users.py
    test_products.py
```

With module mounting:

```python
# app.py
from lcore import Lcore
from modules.users import users_app
from modules.products import products_app

app = Lcore()
app.mount('/api/users/', users_app)
app.mount('/api/products/', products_app)

app.run(server='gunicorn', port=8080)

# modules/users.py
from lcore import Lcore, request

users_app = Lcore()

@users_app.route('/')
def list_users():
    return {'users': []}

@users_app.route('/<id:int>')
def get_user(id):
    return {'id': id}
```
