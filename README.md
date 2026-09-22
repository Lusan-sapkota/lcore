<p align="center">
  <img src="https://lcore.lusansapkota.com.np/lcore.png" alt="Lcore" width="80">
</p>

<h1 align="center">Lcore</h1>

<p align="center">
  A fast, lightweight, single-file Python WSGI framework with zero dependencies.<br>
  Inspired by the simplicity of <a href="https://bottlepy.org">Bottle</a>.
</p>

<p align="center">
  <a href="https://lcore.lusansapkota.com.np">Documentation</a> &bull;
  <a href="https://lcore.lusansapkota.com.np/getting-started.html">Getting Started</a> &bull;
  <a href="https://lcore.lusansapkota.com.np/api-reference.html">API Reference</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.8%2B-blue" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/version-0.0.4-informational" alt="v0.0.4">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT">
  <img src="https://img.shields.io/badge/dependencies-none-brightgreen" alt="Zero Dependencies">
</p>

---

## Installation

```bash
uv add lcore          # uv (recommended)
pip install lcore     # pip
```

## Quick Start

```python
from lcore import Lcore

app = Lcore()

@app.route('/hello/<name>')
def hello(name):
    return {'message': f'Hello, {name}!'}

app.run()
```

## Key Features

- **Single file, zero dependencies**  drop `lcore.py` into any project
- **Full WSGI compliance**  works with Gunicorn, uWSGI, Waitress, and 17+ server adapters
- **Concurrency without async/await**  run under the `gevent`/`eventlet` server adapters and ordinary synchronous handlers get real concurrency for free, no code changes. Measured: 200 concurrent requests to a 0.2s handler took 2.07s on a 20-thread server, 0.58s under gevent. `async def` handlers are accepted too, but [do not provide concurrency under WSGI](https://lcore.lusansapkota.com.np/routing.html#async-routes)  Lcore warns at first use of any async route.
- **10 built-in middleware**  CORS, CSRF, sessions, security headers, compression, body limits, request ID, logging, proxy fix, timeouts
- **Server-side sessions**  revocable logins with memory, SQLite or Redis backends, sign-out-everywhere, and active device listing
- **Security primitives**  PBKDF2 password hashing, HMAC-SHA256 signed cookies, rate limiting
- **Dependency injection**  singleton, scoped, and transient lifetimes
- **Plugin system**  JSON serialization, template rendering, and custom plugins
- **Request validation**  JSON body and query parameter validation with type checking
- **Built-in test client**  unit test routes without starting a server
- **12 lifecycle hooks**  request start, auth, handler enter/exit, response build/send, and more
- **Module mounting**  compose sub-applications with isolated routes and middleware

Full documentation at **[lcore.lusansapkota.com.np](https://lcore.lusansapkota.com.np)**.

## Performance

Benchmarked with 100,000 iterations × 3 runs per framework (best run recorded), single process, no I/O, measuring pure framework overhead:

| Framework | JSON (req/s) | Plaintext (req/s) |
|-----------|-------------|-------------------|
| Lcore     | 91,917      | 116,794           |
| Flask 3.1.3 | 22,757    | 25,497            |
| Bottle 0.13.4 | 138,299  | 187,334           |

Lcore processes **2.2x – 4.6x** more requests per second than Flask across 7 test scenarios (plaintext, JSON, route params, middleware stack, 404 miss, multi-route dispatch, POST JSON). See the [full benchmarks](https://lcore.lusansapkota.com.np/#performance) for details.

Run the benchmarks yourself:
```bash
pip install flask bottle
cd benchmarks && python benchmark.py --full
```

## When NOT to Use Lcore

| Situation | Better choice |
|-----------|---------------|
| You need WebSockets or real-time async I/O | FastAPI, Starlette, Quart |
| You specifically need asyncio-native libraries (`asyncpg`, `httpx`, `motor`) with a persistent event loop | FastAPI, Starlette |
| You need automatic OpenAPI / Swagger generation | FastAPI |
| You need ASGI and Uvicorn / Daphne | FastAPI, Starlette |
| You need a full MVC framework with ORM, admin panel, and migrations | Django |
| Your team is already on Flask and migration cost outweighs the benefit | Stay on Flask |

If your workload is primarily synchronous  REST APIs, internal services, microservices with sync DB drivers  Lcore is a strong fit. That includes high-concurrency I/O-bound workloads too, as long as they don't specifically need asyncio-native libraries: the `gevent`/`eventlet` server adapters give ordinary synchronous handlers real concurrency under slow I/O, with zero code changes.

## License

MIT  see [LICENSE](LICENSE) for details.

---

<p align="center">
  Built by <a href="https://lusansapkota.com.np">Lusan Sapkota</a> &bull; Inspired by <a href="https://bottlepy.org">Bottle</a>
</p>
