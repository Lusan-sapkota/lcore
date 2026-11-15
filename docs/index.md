Source: https://lcore.lusansapkota.com.np/

# Build Microservices  
at Lightning Speed

A fast, lightweight, single-file Python WSGI framework. Zero dependencies. Production-grade. One file. `async def` supported.

- Python 3.8+
- v0.0.6
- Early Release
- MIT
- Zero Dependencies

## Quick Install

Zero dependencies only Python 3.8+ required. Every import is from the standard library.

```bash
uv add lcore
pip install lcore
curl -O https://raw.githubusercontent.com/Lusan-sapkota/lcore/main/lcore.py
```

## Hello World

```python
from lcore import Lcore

app = Lcore()

@app.route('/hello')
def hello():
    return {'message': 'Hello, World!'}

app.run(host='0.0.0.0', port=8080)
```

## Performance

WSGI throughput benchmark 100,000 iterations × 3 runs per framework, best run recorded. Measures pure framework overhead. Measured November 2026 on Python 3.14 (Linux), version 0.0.6.

| Test | **Lcore** | Flask 3.1.3 | Bottle 0.13.4 | Lcore vs Flask |
|---|---|---|---|---|
| Plaintext | **162,873** | 24,139 | 174,801 | **6.7x** |
| JSON | **113,290** | 21,433 | 127,035 | **5.3x** |
| Route Params | **100,576** | 20,066 | 114,101 | **5.0x** |
| Middleware (2 layers) | **69,785** | 19,350 | 109,021 | **3.6x** |
| 404 Miss | **70,699** | 12,683 | 36,556 | **5.6x** |
| Multi-Route (50 routes) | **117,173** | 21,262 | 130,858 | **5.5x** |
| POST JSON | **80,595** | 16,872 | 89,132 | **4.8x** |

Lcore is **3.6x – 6.7x faster than Flask** across all 7 test scenarios, and 1.9x faster than Bottle on 404 misses. Bottle is faster on raw throughput elsewhere (Lcore reaches 64% – 93% of it) but lacks middleware, DI, security stack, and lifecycle hooks that Lcore provides out of the box. See the full [feature comparison](https://lcore.lusansapkota.com.np/#comparison).

## Feature Comparison

How Lcore compares to other Python microframeworks.

| Feature | Lcore | Flask | Bottle | FastAPI |
|---|---|---|---|---|
| Single file / zero deps | **Yes** | No | Yes | No |
| WSGI | **Yes** | Yes | Yes | No |
| ASGI | No | No | No | **Yes** |
| Async route handlers | **Yes** ⚠ | Yes (2.0+) | No | Yes |
| Typed route parameters | **Yes** | Yes | Yes | Yes |
| Custom route filters | **Yes** | Yes | Yes | No |
| Route groups | **Yes** | Blueprints | No | APIRouter |
| Built-in middleware | **7 included** | 0 | 0 | Several |
| CORS middleware | **Built-in** | Extension | Plugin | Built-in |
| CSRF protection | **Built-in** | Extension | No | No |
| Security headers | **Built-in** | Extension | No | No |
| Rate limiting | **Built-in (per-process; pass `backend=` for shared)** | Extension | No | Extension |
| Request validation | **Built-in** | Extension | No | Built-in |
| Dependency injection | **Built-in (3 lifetimes)** | No | No | Built-in |
| Plugin system | **Yes** | Extensions | Yes | No |
| Lifecycle hooks | **12 hook points** | Signals | 6 hooks | Events |
| Module mounting | **Yes (WSGI)** | Blueprints | Yes | Sub-apps |
| Template engines | **4 engines** | Jinja2 | SimpleTemplate | Jinja2 |
| Signed cookies | **HMAC-SHA256** | itsdangerous | HMAC | No |
| Static file serving | **Yes (ETag, Range)** | Yes | Yes | Yes |
| Server adapters | **21 adapters** | Werkzeug | 20+ adapters | Uvicorn |
| Hot reload | **Built-in + Watchdog** | Werkzeug | Yes | Uvicorn |
| CLI interface | **Yes** | Yes | No | No |
| Auto API docs (HTML + JSON) | **Built-in** | No | No | OpenAPI/Swagger |
| Body size limits | **Built-in** | Config | Config | Config |
| Gzip compression | **Built-in** | Extension | No | Middleware |
| Request ID tracking | **Built-in** | Extension | No | Extension |
| Password hashing | **PBKDF2-SHA256** | Extension | No | No |
| Test client | **Built-in** | Built-in | No | Built-in |
| Background tasks | **Built-in** | Celery | No | Built-in |
| Graceful shutdown | **Built-in** | Server | No | Server |

## Why Lcore Exists

Most Python frameworks make one of two trade-offs: simple and fast (Bottle) but with no middleware, no DI, and no security stack or full-featured (Flask, Django) but dependent on many extensions and slower under load. Lcore closes that gap.

| Framework | What it does |
|---|---|
| **Bottle** | Single file, zero deps, fast. But no middleware stack, no dependency injection, no security primitives, no lifecycle hooks. You build all of that yourself. |
| **Flask** | Popular and well-documented. But you need flask-cors, flask-limiter, flask-login, and many more before you have a production API and each is a dependency. |
| **Lcore** | Single file, zero deps, about 5x faster than Flask, with CORS, CSRF, security headers, rate limiting, PBKDF2 hashing, DI, 12 lifecycle hooks, and a test client all built in. Nothing to install beyond Lcore itself. |

## Design Philosophy

> **One file only.** The entire framework is `lcore.py`. No package structure, no sub-modules, no build step. Drop it into any project and import it.

> **Zero external dependencies.** Every import is from Python's standard library. Works in air-gapped environments, containers, and serverless functions where `pip` may not be available.

> **Production features built in, not bolted on.** CORS, CSRF, security headers, rate limiting, signed cookies, and password hashing ship with the framework. You should not need five extensions to secure a production API.

> **Honest about limitations.** Lcore is WSGI. It documents and warns loudly when a feature has constraints async handlers, per-process rate limiting, thread-blocking timeouts. No surprises.

> **Standard Python throughout.** No metaclass magic, no descriptor abuse, no import-time side effects beyond what is declared. The source is meant to be read and understood.

> **Fast, and measured.** The request path is kept to roughly 10 µs. Any change that touches it is benchmarked before and after, so speed is a tested property, not a hope. The numbers are in the Performance section above.

> **Safe defaults, not safe options.** Request bodies are capped at 10 MB, CRLF in headers and cookies is rejected, and the development server refuses a public address unless you opt in. Input is validated at the boundary, so the secure path is the default one.

> **449 tests, zero test dependencies.** The test suite uses only `unittest` from the standard library. Run it anywhere with `python -m pytest tests/` after installing pytest.

## When NOT to use Lcore

Lcore is a strong fit for synchronous WSGI workloads. It is the wrong choice in these situations:

| Situation | Better choice |
|---|---|
| You need WebSockets or real-time async I/O | FastAPI, Starlette, Quart |
| You need true async concurrency (async DB drivers, hundreds of simultaneous outbound calls) | FastAPI, Starlette |
| Your team is already on Flask and migration cost outweighs any benefit | Stay on Flask |
| You need automatic OpenAPI / Swagger generation | FastAPI |
| You need ASGI and Uvicorn / Daphne today | FastAPI, Starlette |
| You specifically need asyncio-native libraries (`asyncpg`, `httpx`, `motor`) with a persistent event loop | FastAPI, Starlette |
| You need a full MVC framework with ORM, admin panel, and migrations | Django |

> **Lcore is a good fit when...**
> Your workload is primarily synchronous: REST APIs, internal services, background job APIs, or microservices that talk to SQL databases via sync drivers (`psycopg2`, `sqlite3`, `mysqlclient`). If you want maximum feature density in a single file with no installation ceremony, Lcore is built for that. That includes high-concurrency I/O-bound workloads too, as long as they don't specifically need asyncio-native libraries: the `gevent`/`eventlet` server adapters give ordinary synchronous handlers real concurrency under slow I/O with zero code changes — [measured numbers](https://lcore.lusansapkota.com.np/routing.html#async-routes).

## Ideal Use Cases

> **Internal REST APIs.** Admin panels, dashboards, and data pipelines that talk to SQL databases via `psycopg2`, `sqlite3`, or `mysqlclient`.

> **Microservices with no async I/O.** Services that call other services synchronously, process files, hash passwords, or do CPU-bound work.

> **Rapid prototyping.** Drop in a single file, no virtual environment ceremony, start handling requests in minutes. Auth, CORS, and rate limiting included.

> **Air-gapped or restricted environments.** Zero external dependencies means no supply-chain risk and no `pip` access required. Works anywhere Python 3.8+ runs.

> **Embedded and constrained deployments.** Containers, serverless functions, or edge nodes where you want the smallest possible footprint.

> **Teams moving off Bottle.** Familiar single-file philosophy with the middleware, DI, security, and lifecycle hooks that Bottle leaves you to build yourself.

> **Scripts that occasionally serve HTTP.** Background workers, CLI tools, or data jobs that also expose a health check or webhook endpoint.

> **Webhook receivers and event processors.** Ingest webhooks from Stripe, GitHub, or Slack. Validate HMAC signatures, parse JSON, and dispatch with built-in security primitives.

> **Learning Python web development.** A single readable file with no magic, no metaclasses, and no hidden layers. Understand how WSGI, routing, and middleware actually work.

## Key Features

> **Single file, zero dependencies.** One Python file built on the standard library. Drop it into any project containers, serverless, or air-gapped networks.

> **Powerful routing.** Typed parameters, wildcard filters, method decorators, and route groups. `async def` handlers accepted with automatic wrapping [see the async caveat](https://lcore.lusansapkota.com.np/routing.html#async-routes).

> **Security first.** CORS, CSRF, security headers, signed cookies, PBKDF2 password hashing, body limits, rate limiting, and timing-safe comparison all built in.

> **7 built-in middleware.** CORS, CSRF, security headers, compression, body limits, request ID, and structured logging. Add your own with 3 lines.

> **Dependency injection.** Register singleton, scoped, or transient dependencies. Auto-inject DB sessions, caches, and loggers per-request.

> **Async/await WSGI Limitation** What's coming?  
>  Lcore accepts `async def` route handlers, but the worker thread is blocked for the full duration. No concurrency benefit. [Full details](https://lcore.lusansapkota.com.np/routing.html#async-routes).
> **Coming Soon: `lcore-asgi`**
> A companion library bringing full ASGI support: WebSockets, true async I/O, persistent event loop, HTTP/2, Server-Sent Events, and compatibility with `asyncpg`, `httpx`, and `aiohttp`. Same familiar Lcore API.

> **12 lifecycle hooks.** Fine-grained control at every stage: request start, auth, handler enter/exit, response build/send, and more.

> **21 server adapters.** Gunicorn, Waitress, Gevent, Eventlet, Tornado, Bjoern, Meinheld, and more. Use `server='auto'` to pick the best available.

> **Plugin architecture.** JSON serialization, template rendering, and custom plugins with setup/apply lifecycle. Per-route skip support.

> **Module mounting.** Mount sub-applications with isolated routes, hooks, and middleware. Compose microservices into larger systems.

> **Built-in test client.** Test routes without starting a server. TestClient calls WSGI directly assert status codes, JSON bodies, and headers.

> **Background tasks.** Fire-and-forget work with BackgroundTaskPool. Send emails, run cleanup, or process analytics without blocking the response.

## Used in Production

Lcore is already powering production workloads. The list is small today but every deployment feeds directly into real-world performance analysis and targeted improvements.

> **Live deployments.** Lcore serves production traffic on several sites right now, handling REST APIs, webhook ingestion, and internal tooling. Each deployment is monitored for latency, throughput, and memory patterns.

> **Continuous analysis.** Production profiling data drives every optimization pass from route matching to middleware overhead. The goal is to make Lcore the fastest Python WSGI framework that still ships with a full security and middleware stack.

> **Roadmap-driven.** Active production use informs the priority queue: shared-nothing rate limiting backends, ASGI companion library, WebSocket support, and OpenAPI generation are all being scoped based on real-world demand.

## Production Microservice

```python
from lcore import (
    Lcore, request, response, ctx,
    CORSMiddleware, SecurityHeadersMiddleware,
    RequestIDMiddleware, BodyLimitMiddleware,
    rate_limit, validate_request, on_shutdown
)

app = Lcore()

# Production middleware stack
app.use(RequestIDMiddleware())
app.use(SecurityHeadersMiddleware(hsts=True))
app.use(CORSMiddleware(allow_origins=['https://myapp.com']))
app.use(BodyLimitMiddleware(max_size=5 * 1024 * 1024))

# Dependency injection
app.inject('db', create_db_session, lifetime='scoped')
app.inject('cache', RedisCache, lifetime='singleton')

# Rate-limited, validated API endpoint
@app.route('/api/users/<id:int>', method='GET')
@rate_limit(100, per=60)
def get_user(id):
    user = ctx.db.query(User).get(id)
    if not user:
        abort(404, 'User not found')
    return user.to_dict()

@app.post('/api/users')
@validate_request(body={'name': str, 'email': str})
def create_user():
    data = request.json
    return {'id': ctx.db.insert(data), 'created': True}

# Graceful shutdown
@on_shutdown
def cleanup():
    close_all_connections()

app.run(server='gunicorn', host='0.0.0.0', port=8080)
```

Lcore Framework Created by [Lusan Sapkota](https://lusansapkota.com.np) MIT License   
 [GitHub](https://github.com/Lusan-sapkota/lcore)
