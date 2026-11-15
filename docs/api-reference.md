Source: https://lcore.lusansapkota.com.np/api-reference.html

# API Reference

Complete reference for all classes, functions, and constants in the Lcore framework.

## Lcore

The main application class. Creates a WSGI-compatible application.

### `Lcore(**kwargs)`

Create a new Lcore application. Keyword arguments are added to `app.config`.

### Routing Methods

| Method | Signature | Description |
|---|---|---|
| `route` | `(path=None, method='GET', callback=None, name=None, apply=None, skip=None, **config)` | Register a route. Use as decorator or direct call. |
| `get` | `(path=None, **options)` | Shorthand for `route(method='GET')` |
| `post` | `(path=None, **options)` | Shorthand for `route(method='POST')` |
| `put` | `(path=None, **options)` | Shorthand for `route(method='PUT')` |
| `delete` | `(path=None, **options)` | Shorthand for `route(method='DELETE')` |
| `patch` | `(path=None, **options)` | Shorthand for `route(method='PATCH')` |
| `error` | `(code=500, callback=None)` | Register error handler for HTTP status code. |
| `add_route` | `(route)` | Add a `Route` object directly. |
| `add_route_filter` | `(name, pattern, to_python=None, to_url=None)` | Register a custom URL filter. |

### Mounting & Merging

| Method | Signature | Description |
|---|---|---|
| `mount` | `(prefix, app, **options)` | Mount a sub-app or WSGI app under a prefix. |
| `merge` | `(routes)` | Merge routes from another app. |

### Hook System

| Method | Signature | Description |
|---|---|---|
| `add_hook` | `(name, func)` | Register a hook callback. |
| `remove_hook` | `(name, func)` | Remove a hook callback. |
| `trigger_hook` | `(__name, *args, **kwargs)` | Trigger all callbacks for a hook. Returns list of results. |
| `hook` | `(name)` | Decorator to register a hook callback. |
| `add_module_hook` | `(prefix, hook_name, func)` | Register hook for mounted module prefix. |
| `module_hook` | `(prefix, hook_name)` | Decorator for module-specific hooks. |
| `trigger_module_hooks` | `(prefix, hook_name, *args, **kwargs)` | Trigger module hooks. |

### Plugin System

| Method | Signature | Description |
|---|---|---|
| `install` | `(plugin)` | Install a plugin. Calls `setup(app)`. |
| `uninstall` | `(plugin)` | Uninstall by name or instance. |
| `reset` | `(route=None)` | Reset route cache. Re-applies plugins. |

### Middleware & DI

| Method | Signature | Description |
|---|---|---|
| `use` | `(middleware, routes=None, order=None)` | Register middleware. |
| `inject` | `(name, factory, lifetime='singleton')` | Register a dependency. Lifetimes: `singleton`, `scoped`, `transient`. |

### Utility Methods

| Method | Signature | Description |
|---|---|---|
| `match` | `(environ)` | Match a WSGI environ to a route. |
| `get_url` | `(routename, **kargs)` | Build URL from route name. |
| `group` | `(prefix, **common_config)` | Context manager for route grouping. |
| `show_routes` | `()` | List all routes as dicts. |
| `show_middleware` | `()` | List all middleware sorted by order. |
| `api_docs` | `()` | Generate API docs as dict. |
| `api_docs_json` | `()` | Generate API docs as JSON string. |
| `run` | `(**kwargs)` | Start server. Accepts `server`, `host`, `port`, `debug`, `reloader`. |
| `close` | `()` | Close app, trigger app_reset hooks. |

### Properties

| Property | Type | Description |
|---|---|---|
| `config` | `ConfigDict` | Application configuration. |
| `routes` | `list[Route]` | All registered routes. |
| `router` | `Router` | URL routing engine. |
| `plugins` | `list` | Installed plugins. |
| `middleware` | `MiddlewarePipeline` | Middleware pipeline. |
| `resources` | `ResourceManager` | File resource manager. |
| `catchall` | `bool` | Catch all exceptions (from config). |

### v0.0.4 Config Keys

| Key | Default | Description |
|---|---|---|
| `error.format` | `'html'` | Error response format: `'html'` or `'json'`. Set to `'json'` for pure API servers. |
| `proxy.trusted` | `None` | Trusted proxy IPs as list or comma-separated string. Makes `request.remote_addr` return real client IP behind nginx. |

## BaseRequest

### `BaseRequest(environ=None)`

HTTP request wrapper around WSGI environ dict. Thread-local via `request` proxy.

### Properties

| Property | Type | Description |
|---|---|---|
| `method` | `str` | HTTP method (GET, POST, etc.) |
| `path` | `str` | Request path |
| `url` | `str` | Full URL |
| `fullpath` | `str` | Path with script_name |
| `urlparts` | `SplitResult` | Parsed URL components |
| `query_string` | `str` | Raw query string |
| `script_name` | `str` | WSGI SCRIPT_NAME |
| `content_type` | `str` | Content-Type header |
| `content_length` | `int` | Content-Length (-1 if invalid) |
| `remote_addr` | `str` | Client IP address |
| `remote_route` | `list` | IP chain from X-Forwarded-For |
| `is_xhr` | `bool` | XMLHttpRequest check |
| `is_ajax` | `bool` | Alias for is_xhr |
| `auth` | `tuple` | Parsed Basic auth (user, pass) or None |
| `chunked` | `bool` | Chunked transfer encoding |
| `headers` | `WSGIHeaderDict` | Request headers (case-insensitive) |
| `cookies` | `FormsDict` | Cookie values |
| `query` / `GET` | `FormsDict` | Query string parameters |
| `forms` | `FormsDict` | Form body fields |
| `params` | `FormsDict` | Combined query + forms |
| `files` | `FormsDict` | Uploaded files (FileUpload objects) |
| `json` | `dict/None` | Parsed JSON body |
| `body` | `BytesIO` | Raw request body stream |
| `app` | `Lcore` | Parent application |
| `route` | `Route` | Matched route |
| `url_args` | `dict` | URL parameter arguments |

### Methods

| Method | Signature | Description |
|---|---|---|
| `get_header` | `(name, default=None)` | Get a request header value. |
| `get_cookie` | `(key, default=None, secret=None, digestmod=sha256)` | Read cookie (with optional signature verification). |
| `path_shift` | `(shift=1)` | Shift path segments between script_name and path. |
| `copy` | `()` | Create a copy of this request. |

## BaseResponse

### `BaseResponse(body='', status=None, headers=None, **more_headers)`

HTTP response builder. Thread-local via `response` proxy.

### Properties

| Property | Type | Description |
|---|---|---|
| `status` | `int/str` | HTTP status (read/write). Set with int or string. |
| `status_code` | `int` | Numeric status code (read-only). |
| `status_line` | `str` | Full status line like "200 OK" (read-only). |
| `headers` | `HeaderDict` | Response headers. |
| `headerlist` | `list` | Headers as list of (name, value) tuples. |
| `content_type` | `str` | Content-Type header. |
| `content_length` | `int` | Content-Length header. |
| `expires` | `datetime` | Expires header. |
| `charset` | `str` | Character set from Content-Type. |
| `body` | `str/bytes` | Response body. |

### Methods

| Method | Signature | Description |
|---|---|---|
| `set_header` | `(name, value)` | Set header (replaces existing). |
| `add_header` | `(name, value)` | Add header (allows duplicates). |
| `get_header` | `(name, default=None)` | Get response header. |
| `set_cookie` | `(name, value, secret=None, digestmod=sha256, **options)` | Set cookie. Options: max_age, expires, path, domain, secure, httponly, samesite. |
| `delete_cookie` | `(key, **kwargs)` | Delete cookie by setting max_age=-1. |
| `copy` | `(cls=None)` | Copy this response. |
| `close` | `()` | Close body if file-like. |

## RequestContext

### `RequestContext(req=None, resp=None, app=None)`

Per-request context object carrying state across middleware and handlers. Thread-local via `ctx` proxy.

| Attribute | Type | Description |
|---|---|---|
| `request` | `BaseRequest` | Current request. |
| `response` | `BaseResponse` | Current response. |
| `app` | `Lcore` | Application instance. |
| `route` | `Route` | Matched route. |
| `request_id` | `str` | Unique request ID. |
| `user` | `any` | User info (set by auth). |
| `state` | `dict` | Arbitrary per-request state. |

| Method | Signature | Description |
|---|---|---|
| `lazy` | `(key, factory)` | Register a lazy-loaded attribute. |

## Router

### `Router(strict=False)`

URL routing engine. Matches URL paths to route targets.

| Method | Signature | Description |
|---|---|---|
| `add` | `(rule, method, target, name=None)` | Add a route rule. |
| `match` | `(environ)` | Match WSGI environ to a route. Returns (target, url_args). |
| `build` | `(_name, *anons, **query)` | Build URL from route name. |
| `add_filter` | `(name, func)` | Add custom filter function. |

## Route

### `Route(app, rule, method, callback, name=None, plugins=None, skiplist=None, **config)`

Represents a single route with metadata, plugins, and configuration.

| Property/Method | Type | Description |
|---|---|---|
| `app` | `Lcore` | Parent application. |
| `rule` | `str` | URL pattern. |
| `method` | `str` | HTTP method. |
| `callback` | `callable` | Original handler function. |
| `name` | `str` | Route name. |
| `config` | `ConfigDict` | Per-route configuration. |
| `call` | `callable` | Cached callback (after plugin application). |
| `reset()` | - | Reset cached call. |
| `prepare()` | - | Pre-compute callback with plugins. |
| `all_plugins()` | `list` | Get all applicable plugins. |
| `get_undecorated_callback()` | `callable` | Get original callback. |
| `get_callback_args()` | `list` | Get callback parameter names. |

## ConfigDict

### `ConfigDict()`

Configuration dictionary with metadata, overlays, and multi-source loading.

| Method | Signature | Description |
|---|---|---|
| `load_module` | `(name, squash=True)` | Load config from Python module. |
| `load_config` | `(filename, **options)` | Load from INI file. |
| `load_dict` | `(source, namespace='')` | Load from dict (flattens nested dicts). |
| `load_env` | `(prefix='LCORE_', strip_prefix=True)` | Load from environment variables. |
| `load_json` | `(filename)` | Load from JSON file. |
| `load_dotenv` | `(filename='.env')` | Load from .env file (validates key names). |
| `validate_config` | `(schema)` | Validate against dataclass schema. |
| `update` | `(*a, **ka)` | Update with optional prefix support. |
| `setdefault` | `(key, value=None)` | Set default value. |
| `meta_get` | `(key, metafield, default=None)` | Get metadata for a key. |
| `meta_set` | `(key, metafield, value)` | Set metadata for a key. |

## Middleware Classes

### `Middleware`

Base class. Attrs: `name=None`, `order=50`, `phase='post'` (v0.0.4: set `'pre'` to run before routing). Override `__call__(self, ctx, next_handler)`.

### `MiddlewareHook`

Hook-based middleware. Override `pre(ctx)` and `post(ctx, result)`.

### `MiddlewarePipeline`

Manages middleware chain with pre/post routing phases (v0.0.4). Methods: `add(mw, routes, order)`, `remove(mw)`, `execute_pre_routing(ctx)`, `execute(ctx, handler)`.

### Built-in Middleware

| Class | Constructor | Order / Phase |
|---|---|---|
| `ProxyFixMiddleware` | `(trusted_proxies=None, num_proxies=None)` | -10 / pre |
| `TimeoutMiddleware` | `(timeout=30, max_workers=None)` | -5 / post |
| `BodyLimitMiddleware` | `(max_size=10*1024*1024)` | 0 / pre |
| `RequestIDMiddleware` | `()` | 1 / post |
| `RequestLoggerMiddleware` | `(logger=None)` | 2 / post |
| `CORSMiddleware` | `(allow_origins='*', allow_methods=None, allow_headers=None, expose_headers=None, allow_credentials=False, max_age=86400)` | 3 / pre handles OPTIONS before routing |
| `SecurityHeadersMiddleware` | `(hsts=False, hsts_max_age=31536000, **overrides)` | 5 / post |
| `CSRFMiddleware` | `(secret=None, cookie_name='_csrf_token', header_name='X-CSRF-Token', safe_methods=('GET','HEAD','OPTIONS'))` | 10 / pre sets token cookie before routing |
| `SessionMiddleware` | `(backend=None, secret=None, cookie_name='lcore_session', ttl=1209600, absolute_ttl=None, refresh_every=None, secure=False, httponly=True, samesite='Lax', path='/', domain=None, on_backend_error='unavailable')` | 20 / post |
| `CompressionMiddleware` | `(min_size=256, level=6, content_types=None, stream_threshold=262144)` | 90 / post |

## Session Backends

| Class | Constructor | Notes |
|---|---|---|
| `MemorySessionBackend` | `(max_sessions=100000, warn=True)` | Development only. Per-process, lost on restart. |
| `SQLiteSessionBackend` | `(path='lcore_sessions.db', busy_timeout=5000, cleanup_every=300, cleanup_batch=1000)` | Stdlib only. Multi-worker safe on one machine. `cleanup_batch` bounds each periodic sweep to that many expired rows, so a backlog cannot turn one request into a full-table scan. |
| `RedisSessionBackend` | `(redis_url='redis://localhost:6379/0', prefix='lcore:sess:', socket_connect_timeout=2, health_check_interval=30)` | Requires `uv add redis`. Multi-server. |
| `SessionBackend` | ABC | Implement `load`, `save`, `delete`, `list_user`, `revoke_user`, `get_epoch`, `bump_epoch`. `revoke_all()`, `touch()` and `cached_epoch()` are inherited. Also override `unindex(sid, user_key)` if your backend keeps its own per-user index (the base implementation is a no-op) — it is called when `bind_user(regenerate=False)` reassigns a session to a different user, so the old user's index does not keep pointing at it. Class attributes `epoch_cache_ttl` (default `5.0`) and `epoch_cache_max` (default `10000`) tune the per-process epoch cache; call `self._forget_epoch(key)` from a custom `bump_epoch`. |

## DependencyContainer

### `DependencyContainer()`

Manages dependency injection with singleton, scoped, and transient lifetimes.

| Method | Signature | Description |
|---|---|---|
| `register` | `(name, factory, lifetime='singleton')` | Register a dependency factory. |
| `resolve` | `(name, ctx=None)` | Resolve dependency by name. |
| `_begin_scope` | `(ctx)` | Begin request scope. |
| `_end_scope` | `(ctx)` | End scope and close scoped deps. |
| `__contains__` | `(name)` | Check if dependency registered. |
| `__len__` | `()` | Count registered dependencies. |

## Exceptions

| Exception | Parent | Description |
|---|---|---|
| `HTTPResponse` | `BaseResponse` | Can be raised to send immediate response. `(body, status, headers)` |
| `HTTPError` | `HTTPResponse` | Error response. v0.0.4: `(status, body, exception, traceback, content_type)`. Headers set before raising are now preserved. |
| `LcoreException` | `Exception` | Base framework exception. |
| `RouteError` | `LcoreException` | Routing error base. |
| `RouterUnknownModeError` | `RouteError` | Unknown router mode. |
| `RouteSyntaxError` | `RouteError` | Invalid route pattern syntax. |
| `RouteBuildError` | `RouteError` | URL build failure. |
| `PluginError` | `LcoreException` | Plugin conflict or error. |
| `TemplateError` | `LcoreException` | Template loading/rendering error. |
| `MultipartError` | `HTTPError` | Multipart parsing error (400). |

## Data Structures

### `MultiDict(*a, **k)`

Dict supporting multiple values per key. Methods: `get(key, default, index, type)`, `append(key, value)`, `replace(key, value)`, `getall(key)`, `allitems()`.

### `FormsDict`

Form data dict. Extends MultiDict. Methods: `decode(encoding)`, `getunicode(name, default, encoding)`. Supports attribute access.

### `HeaderDict`

Case-insensitive header dict. Extends MultiDict. Method: `filter(names)` to remove headers.

### `WSGIHeaderDict(environ)`

Read-only header dict wrapping WSGI environ. Method: `raw(key, default)` for raw environ value.

### `FileUpload(fileobj, name, filename, headers=None)`

Uploaded file wrapper. Props: `filename` (sanitized), `content_type`, `content_length`, `file`. Methods: `save(dest, overwrite)`, `get_header(name)`.

### `ResourceManager(base='./', opener=open, cachemode='all')`

File resource finder with caching. Methods: `add_path(path, base, index, create)`, `lookup(name)`, `open(name, mode)`.

### `AppStack`

Stack of Lcore apps. Methods: `push(value)` / `new_app()`. Callable returns default app. Property: `default`.

### `cached_property(func)`

Thread-safe cached property descriptor with double-checked locking (RLock).

## Utility Functions

| Function | Signature | Description |
|---|---|---|
| `tob` | `(s, enc='utf8')` | Convert to bytes. None → b''. |
| `touni` | `(s, enc='utf8', err='strict')` | Convert to unicode string. |
| `html_escape` | `(string)` | Escape HTML special characters. |
| `html_quote` | `(string)` | Quote an HTML string. |
| `makelist` | `(data)` | Wrap in list if not already. |
| `parse_auth` | `(header)` | Parse HTTP Basic Auth header. Returns (user, pass). |
| `parse_date` | `(ims)` | Parse HTTP date string to timestamp. |
| `parse_range_header` | `(header, maxlen=0)` | Parse Range header. Returns list of (start, end). |
| `http_date` | `(value)` | Format datetime/timestamp as HTTP date string. |
| `redirect` | `(url, code=None)` | Raise a redirect HTTPResponse. |
| `abort` | `(code=500, text='Unknown Error.')` | Raise an HTTPError. |
| `static_file` | `(filename, root, mimetype=True, download=False, charset='UTF-8', etag=None, headers=None)` | Serve a static file with caching, range requests, and security. |
| `load` | `(target)` | Dynamically load module/attribute (safe getattr chain). |
| `load_app` | `(target)` | Load WSGI app from "module:app" string. |
| `load_dotenv` | `(path=None)` | v0.0.4: Load .env file into os.environ. Auto-called by `app.run()`. |
| `debug` | `(mode=True)` | Enable/disable debug mode globally. |
| `run` | `(app=None, server='wsgiref', host='127.0.0.1', port=8080, interval=1, reloader=False, quiet=False, plugins=None, debug=None, config=None, **kargs)` | Start a WSGI server. |
| `pretty_error_page` | `(exception, traceback_str=None)` | Generate styled HTML error page. |

## Security Utilities

| Function | Signature | Description |
|---|---|---|
| `hash_password` | `(password, iterations=600000)` | Hash password using PBKDF2-SHA256 with random 32-byte salt. Returns `'pbkdf2:sha256:N$salt$hash'`. |
| `verify_password` | `(password, hash_string)` | Verify password against PBKDF2 hash. Timing-safe via `hmac.compare_digest`. |

## Test Client

### `TestClient(app)`

WSGI test client. Calls app directly without HTTP no server needed.

| Method | Signature | Description |
|---|---|---|
| `request` | `(method, path, body=b'', headers=None, query_string='', content_type=None, json=None)` | Send any HTTP method. Returns `TestResponse`. |
| `get` | `(path, **kw)` | GET request |
| `post` | `(path, **kw)` | POST request |
| `put` | `(path, **kw)` | PUT request |
| `patch` | `(path, **kw)` | PATCH request |
| `delete` | `(path, **kw)` | DELETE request |
| `head` | `(path, **kw)` | HEAD request |
| `options` | `(path, **kw)` | OPTIONS request |

### `TestResponse`

Response object returned by `TestClient` methods.

| Property | Type | Description |
|---|---|---|
| `.status` | `str` | Full status line: `"200 OK"` |
| `.status_code` | `int` | HTTP status code: `200` |
| `.headers` | `dict` | Response headers |
| `.body` | `bytes` | Raw response body |
| `.text` | `str` | Body decoded as UTF-8 |
| `.json` | `dict/list` | Body parsed as JSON |

## BackgroundTaskPool

### `BackgroundTaskPool(max_workers=4)`

Thread-pool for fire-and-forget background tasks. Wraps `concurrent.futures.ThreadPoolExecutor`.

| Method / Property | Description |
|---|---|
| `.submit(fn, *args, **kwargs)` | Queue callable for background execution. Returns `Future`. |
| `.pending` | Number of tasks still running or queued. |
| `.shutdown(wait=True)` | Shut down pool. Blocks if `wait=True`. |

## Decorators

| Decorator | Signature | Description |
|---|---|---|
| `@auth_basic` | `(check, realm='private', text='Access denied')` | HTTP Basic authentication. `check(user, pass)` must return True. |
| `@rate_limit` | `(limit, per=60, max_buckets=10000, backend=None)` | Token bucket rate limiting per IP. **In-process by default** (each worker has independent buckets; effective limit per client = `N × limit` under N workers). Pass a `RedisRateLimitBackend` to enforce limits across all workers. |
| `@validate_request` | `(body=None, query=None)` | v0.0.4: Validate request body/query against schema. Supports `Optional[type]`, auto-coerces types, returns structured JSON errors. |
| `@on_shutdown` | `(func)` | Register function to run on app shutdown. |
| `@view` | `(tpl_name, **defaults)` | Render SimpleTemplate when handler returns dict. |
| `@jinja2_view` | `(tpl_name, **defaults)` | Render Jinja2 template. |
| `@mako_view` | `(tpl_name, **defaults)` | Render Mako template. |

### Module-Level Wrappers

These wrap the default app's methods for convenience:

```python
from lcore import route, get, post, put, delete, patch
from lcore import error, mount, hook, install, uninstall, url, use
```

## Rate Limit Backends

### `RateLimitBackend(abc.ABC)`

Abstract base class for custom rate-limit storage. Subclass it and implement `consume(key, limit, per)` to plug any atomic store into `@rate_limit(backend=...)`.

| Method | Signature | Description |
|---|---|---|
| `consume` | `(key, limit, per) -> bool` | **Abstract.** Atomically consume one token. Return `True` = allowed, `False` = blocked (429). |
| `close` | `()` | Optional. Release resources. Called on process exit if registered via `@on_shutdown`. |

### `RedisRateLimitBackend(redis_url='redis://localhost:6379/0', prefix='lcore:rl:', socket_connect_timeout=2, health_check_interval=30)`

Built-in Redis-backed backend. Enforces per-IP limits **across all worker processes** via an atomic Lua script (`INCR` + `EXPIRE` in one round-trip). Requires: `uv add redis`.

Fails **open** (allows request, logs warning) when Redis is unavailable so a Redis outage cannot take down your application.

| Parameter | Default | Description |
|---|---|---|
| `redis_url` | `'redis://localhost:6379/0'` | Redis connection URL (`redis://`, `rediss://`, or `unix://`). |
| `prefix` | `'lcore:rl:'` | Key prefix used in Redis. Change it to namespace multiple apps. |
| `socket_connect_timeout` | `2` | Seconds before a connection attempt gives up. |
| `health_check_interval` | `30` | Seconds between background health-check pings to Redis. |

```python
from lcore import RedisRateLimitBackend, rate_limit

_rl = RedisRateLimitBackend('redis://localhost:6379/0')

@app.post('/api/login')
@rate_limit(5, per=300, backend=_rl)   # shared across all workers
def login(): ...
```

## Template Classes

| Class | Engine | Extensions |
|---|---|---|
| `BaseTemplate` | Abstract base | `.tpl .html .thtml .stpl` |
| `SimpleTemplate` | Built-in | Uses `StplParser` |
| `Jinja2Template` | Jinja2 | Requires `jinja2` |
| `MakoTemplate` | Mako | Requires `mako` |
| `CheetahTemplate` | Cheetah | Requires `cheetah3` |

All templates share: `search(name, lookup)`, `global_config(key)`, `prepare(**options)`, `render(*args, **kwargs)`.

## Server Adapters

### `ServerAdapter(host='127.0.0.1', port=8080, **options)`

Base class for all server adapters. Override `run(handler)` to start the server.

| Adapter | Server Name | Package |
|---|---|---|
| `WSGIRefServer` | `wsgiref` | Built-in |
| `CherootServer` | `cheroot` | `cheroot` |
| `WaitressServer` | `waitress` | `waitress` |
| `GunicornServer` | `gunicorn` | `gunicorn` |
| `GeventServer` | `gevent` | `gevent` |
| `EventletServer` | `eventlet` | `eventlet` |
| `TornadoServer` | `tornado` | `tornado` |
| `TwistedServer` | `twisted` | `twisted` |
| `MeinheldServer` | `meinheld` | `meinheld` |
| `BjoernServer` | `bjoern` | `bjoern` |
| `AiohttpServer` | `aiohttp` | `aiohttp` |
| `AiohttpUVLoopServer` | `uvloop` | `aiohttp + uvloop` |
| `PasteServer` | `paste` | `paste` |
| `AutoServer` | `auto` | Auto-detect |

### Module Constants

| Constant | Value | Description |
|---|---|---|
| `__version__` | `'0.0.6'` | Framework version. |
| `__author__` | `'Lusan Sapkota'` | Author. |
| `__license__` | `'MIT'` | License. |
| `TEMPLATE_PATH` | `['./', './views/']` | Template search paths. |
| `HTTP_CODES` | dict | HTTP status code descriptions. |
| `DEBUG` | `False` | Global debug flag. |
| `request` | `LocalRequest` | Thread-local request proxy. |
| `response` | `LocalResponse` | Thread-local response proxy. |
| `ctx` | `LocalContext` | Thread-local context proxy. |
| `app` / `default_app` | `AppStack` | Default application stack. |
