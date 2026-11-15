Source: https://lcore.lusansapkota.com.np/routing.html

# Routing

Map URLs to handler functions using expressive route patterns with typed parameters, wildcards, and regex filters.

## Basic Routing

Routes map URL patterns to Python functions. Use the `@app.route()` decorator to register a handler:

```python
from lcore import Lcore

app = Lcore()

@app.route('/')
def index():
    return 'Welcome home'

@app.route('/about')
def about():
    return 'About page'
```

### Return Types

Handlers can return various types, and Lcore handles them automatically:

| Return Type | Behavior |
|---|---|
| `str` | Sent as `text/html` response |
| `bytes` | Sent as raw bytes |
| `dict` / `list` | Serialized as JSON with `application/json` Content-Type |
| `HTTPResponse` | Sent as-is with custom status/headers |
| File-like object | Streamed to client |
| `None` | Empty 200 response |

### Named Routes

```python
@app.route('/users/<id:int>', name='user_detail')
def user_detail(id):
    return {'id': id}

# Build URL from name
url = app.get_url('user_detail', id=42)
# -> '/users/42'
```

## HTTP Methods

By default, routes respond to `GET` requests. Specify other methods with the `method` parameter:

```python
@app.route('/items', method='POST')
def create_item():
    return {'created': True}

# Multiple methods on one route
@app.route('/items/<id:int>', method=['GET', 'PUT', 'DELETE'])
def item(id):
    if request.method == 'GET':
        return get_item(id)
    elif request.method == 'PUT':
        return update_item(id)
    elif request.method == 'DELETE':
        return delete_item(id)
```

### Shorthand Decorators

| Decorator | Method | Example |
|---|---|---|
| `@app.get(path)` | GET | Retrieve resources |
| `@app.post(path)` | POST | Create resources |
| `@app.put(path)` | PUT | Replace resources |
| `@app.delete(path)` | DELETE | Remove resources |
| `@app.patch(path)` | PATCH | Partial updates |

```python
@app.get('/users')
def list_users():
    return {'users': []}

@app.post('/users')
def create_user():
    data = request.json
    return {'id': 1, **data}

@app.put('/users/<id:int>')
def replace_user(id):
    return {'id': id, 'replaced': True}

@app.delete('/users/<id:int>')
def remove_user(id):
    return {'deleted': True}
```

> **Tip**
> `HEAD` requests are automatically handled for any `GET` route. The response body is stripped, but headers (including `Content-Length`) are preserved.

If a URL matches a route but not the HTTP method, Lcore returns **405 Method Not Allowed** with an `Allow` header listing valid methods.

## Dynamic Routes

Capture URL segments as parameters using angle brackets. Parameters are passed as keyword arguments to your handler:

```python
@app.route('/hello/<name>')
def hello(name):
    return f'Hello, {name}!'

# GET /hello/Alice -> "Hello, Alice!"
```

### Typed Parameters

Add a filter to constrain and convert parameter types:

| Filter | Pattern | Python Type | Description |
|---|---|---|---|
| `<name>` | `[^/]+` | `str` | Matches one path segment (default) |
| `<name:int>` | `\d+` | `int` | Matches digits, converts to integer |
| `<name:float>` | `\d+\.\d+` | `float` | Matches decimal numbers |
| `<name:path>` | `.+` | `str` | Matches multiple segments (including `/`) |
| `<name:re:pattern>` | Custom regex | `str` | Matches custom regex pattern |

```python
# Integer parameter
@app.route('/users/<id:int>')
def get_user(id):
    return {'id': id, 'type': type(id).__name__}
# GET /users/42 -> {"id": 42, "type": "int"}
# GET /users/abc -> 404

# Float parameter
@app.route('/coords/<lat:float>/<lon:float>')
def location(lat, lon):
    return {'lat': lat, 'lon': lon}

# Path parameter (matches slashes)
@app.route('/files/<filepath:path>')
def serve_file(filepath):
    return static_file(filepath, root='./public')
# GET /files/docs/guide/intro.pdf -> serves the file

# Regex parameter
@app.route('/api/v<version:re:[0-9]+>/status')
def api_status(version):
    return {'api_version': version}

# Multiple parameters
@app.route('/<year:int>/<month:int>/<slug>')
def article(year, month, slug):
    return {'year': year, 'month': month, 'slug': slug}
```

## Async Routes

> **Critical: Async Handlers Block the Worker Thread**
> Lcore is a **synchronous WSGI framework**. WSGI (PEP 3333) is a synchronous protocol by design. Each request occupies exactly one OS thread from start to finish. This is *not* a flaw in Lcore; it is a hard constraint of the WSGI specification itself.
> When you write an `async def` handler, Lcore accepts it and executes it by calling `asyncio.run()` inside a dedicated thread, which **blocks that thread** until the coroutine finishes. Consequences:
> - **No concurrency benefit.** `await asyncio.sleep(1)` blocks the worker thread for 1 second, identical to `time.sleep(1)`. Under gunicorn with 4 threads, 4 concurrent async handlers bring the server to a halt.
> - **No persistent event loop.** Each handler invocation gets a brand-new event loop that is destroyed on return. Loop-bound libraries such as `httpx`, `aiohttp`, `asyncpg`, `motor`, `redis.asyncio`, and `tortoise-orm` **will not work correctly** inside Lcore async handlers because they require a single long-lived event loop and connection pools that persist across calls.
> - **Higher overhead.** Every async route invocation spawns a new thread and a new event loop, adding roughly 0.5 to 2 ms per request versus a plain sync handler.
> Lcore emits a `UserWarning` naming the route the first time each `async def` route is actually invoked (immediately, at reset, if running with `debug=True`; otherwise on that route's first request), so you are always informed.

> **What you probably actually want: gevent or eventlet, not async def**
> If the goal is "don't let one slow request block everything else," that's not what `async def` gives you here — but Lcore already solves it, with zero handler changes. Write completely ordinary, blocking-looking synchronous code, and run the app under the `gevent` or `eventlet` server adapter instead of a plain threaded one. Both monkey-patch the standard library so a blocking call (`socket`, `time.sleep`, most DB drivers) cooperatively yields to other in-flight requests instead of blocking a real OS thread — the actual "start a slow task and move on to other work" behavior, delivered by the runtime, not by rewriting handlers as coroutines.
> Measured directly: 200 concurrent requests to a handler that sleeps 0.2s each. A threaded server with 20 threads (200 connections into 20 workers) took **2.07s** — linear backlog, exactly 10×0.2s. The identical app and handler under `gevent` took **0.58s**. At a concurrency level a fixed thread pool comfortably covers, they're roughly equal (0.23s vs. 0.22s at 20 concurrent requests / 20 threads) — the advantage shows up specifically once concurrency outgrows the thread pool, which is exactly the "many slow requests at once" scenario this section is about.
> ```python
> # No code changes to handlers needed:
> app.run(server='gevent', host='0.0.0.0', port=8080)
> # or: app.run(server='eventlet', host='0.0.0.0', port=8080)
> ```
> This isn't the same thing as an event loop with `async`/`await` and async-native libraries (`asyncpg`, `httpx`) — for that, see `lcore-asgi` below or an ASGI framework. But for "many concurrent slow requests," which is what most people mean by wanting async, this is the WSGI-native answer and it's available today.

### When async def is acceptable in Lcore

There is one scenario where using `async def` in Lcore is harmless: calling an async helper that is **pure CPU work wrapped in a coroutine** with no I/O and no loop-bound state. In practice this is rare. For everything else, prefer sync equivalents.

```python
import asyncio
from lcore import Lcore

app = Lcore()  # Lcore will emit a UserWarning for each async route below

# OK: works, but provides NO concurrency advantage.
# The worker thread is blocked for the duration of the coroutine.
@app.route('/ok-simple')
async def simple():
    # Fine: fast pure-Python computation inside a coroutine.
    return {'result': sum(range(1000))}

# INCORRECT: asyncio.gather() does run both coroutines, but the entire
# gather() blocks the worker thread until both complete. No parallelism.
@app.route('/broken-parallel')
async def broken_parallel():
    # Not concurrent in a WSGI context. Both still run sequentially
    # from the perspective of the OS thread scheduler.
    users, products = await asyncio.gather(fetch_users(), fetch_products())
    return {'users': users, 'products': products}

# INCORRECT: async libraries that require a persistent event loop will
# fail or silently misbehave because each request gets a brand-new loop.
# import httpx
# import asyncpg
# async def broken_db():
#     conn = await asyncpg.connect(...)  # new loop every call, pool unusable
#     ...

# CORRECT: write synchronous handlers.
# Use requests, psycopg2, redis-py, etc.
@app.route('/correct')
def sync_handler():
    # Fast, no overhead, works correctly with every WSGI server.
    return {'type': 'sync'}
```

> **Coming Soon: `lcore-asgi`**
> A companion library, **`lcore-asgi`**, is currently in development. It will bring full ASGI support to the Lcore ecosystem, including:
> - **WebSockets** - bidirectional real-time connections
> - **True async concurrency** - non-blocking I/O with a persistent event loop
> - **Async-native libraries** - full compatibility with `httpx`, `asyncpg`, `aiohttp`, `motor`, and others
> - **HTTP/2 and Server-Sent Events**
> - **Familiar Lcore API** - same routing, middleware, and plugin model you already know
> Until `lcore-asgi` is released, async workloads should use a dedicated ASGI framework (see below).

> **Need genuine async concurrency right now?**
> If your use case requires concurrent async I/O such as WebSockets, many simultaneous outbound HTTP calls, streaming, or async database drivers, use an **ASGI framework** in the meantime. Lcore does not currently provide an ASGI interface.
> - **FastAPI** - async-first, automatic OpenAPI, Pydantic validation
> - **Starlette** - lightweight ASGI toolkit, full async support
> - **Quart** - Flask-compatible async WSGI/ASGI hybrid

### Async Middleware

Middleware can also be async:

```python
from lcore import Middleware

class AsyncTimingMiddleware(Middleware):
    name = 'async_timing'
    order = 2

    async def __call__(self, ctx, next_handler):
        import time
        start = time.time()
        result = next_handler(ctx)
        duration = time.time() - start
        ctx.response.set_header('X-Time', f'{duration:.4f}s')
        return result
```

## Route Filters

Create custom route filters for reusable parameter validation and conversion:

```python
# Custom UUID filter
import re

app.add_route_filter(
    'uuid',
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
    to_python=lambda val: val,
    to_url=lambda val: str(val)
)

@app.route('/items/<item_id:uuid>')
def get_item(item_id):
    return {'item_id': item_id}
# GET /items/550e8400-e29b-41d4-a716-446655440000 -> matches
# GET /items/invalid -> 404
```

The `add_route_filter` method accepts:

| Parameter | Type | Description |
|---|---|---|
| `name` | `str` | Filter name used in route patterns |
| `pattern` | `str` | Regex pattern to match |
| `to_python` | `callable` | Convert matched string to Python type |
| `to_url` | `callable` | Convert Python value back to URL string |

## Route Groups

Group routes under a common prefix using the `app.group()` context manager. Register routes on the group object (`as api`); decorators on `app` are not prefixed:

```python
with app.group('/api/v1') as api:
    @api.route('/users')
    def list_users():
        return {'users': []}

    @api.route('/users/<id:int>')
    def get_user(id):
        return {'id': id}

    @api.route('/products')
    def list_products():
        return {'products': []}

# Routes registered:
#   /api/v1/users
#   /api/v1/users/<id:int>
#   /api/v1/products
```

Groups can share common configuration:

```python
with app.group('/admin', auth_required=True) as admin:
    @admin.route('/dashboard')
    def dashboard():
        return 'Admin Dashboard'
```

## Error Routes

Define custom error pages with the `@app.error()` decorator:

```python
@app.error(404)
def not_found(error):
    return {'error': 'Not found', 'path': request.path}

@app.error(500)
def server_error(error):
    return {'error': 'Internal server error'}

# The error handler receives an HTTPError object with:
#   error.status_code  - HTTP status code
#   error.body         - Error message
#   error.exception    - Original exception (if any)
#   error.traceback    - Traceback string (if debug)
```

### Raising Errors

```python
from lcore import abort, HTTPError

@app.route('/protected')
def protected():
    # Quick abort
    abort(403, 'Access denied')

    # Or raise with more control
    raise HTTPError(
        status=422,
        body='Invalid input',
        headers={'X-Error': 'validation'}
    )
```

## URL Building

Build URLs from route names to avoid hardcoding paths:

```python
@app.route('/users/<id:int>', name='user_detail')
def user_detail(id):
    return {'id': id}

@app.route('/users/<id:int>/posts/<post_id:int>', name='user_post')
def user_post(id, post_id):
    return {'user': id, 'post': post_id}

# Build URLs
app.get_url('user_detail', id=42)
# -> '/users/42'

app.get_url('user_post', id=42, post_id=7)
# -> '/users/42/posts/7'
```

> **Note**
> If a route has no explicit `name`, it defaults to `None` and cannot be used for URL building. Always name routes you intend to reference.

## Route Inspection

### List Routes

Use `app.show_routes()` to get a structured list of all registered routes:

```python
routes = app.show_routes()
for r in routes:
    print(f"{r['method']:6s} {r['rule']:30s} {r['name'] or '-'}")

# GET    /                              index
# GET    /users                         list_users
# POST   /users                         create_user
# GET    /users/<id:int>                user_detail
```

Each route dict contains: `method`, `rule`, `name`, `callback`, `plugins`.

### Auto-Generated API Docs

Generate API documentation automatically from your routes, docstrings, and parameter types:

```python
@app.route('/api/users/<id:int>', method='GET', name='get_user')
def get_user(id):
    """Fetch a single user by their unique ID."""
    return {'id': id}

# Get docs as dict
docs = app.api_docs()
print(docs['routes'][0])
# {'method': 'GET', 'rule': '/api/users/<id:int>',
#  'name': 'get_user', 'docstring': 'Fetch a single user...',
#  'parameters': [{'name': 'id', 'type': 'int'}], ...}

# Get docs as JSON string
json_docs = app.api_docs_json()

# Serve docs as an endpoint
@app.route('/docs')
def docs():
    return app.api_docs()
```
