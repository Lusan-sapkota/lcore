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
  <a href="https://play-lcore.lusansapkota.com.np">Live Playground</a> &bull;
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
pip install lcore
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
- **7 built-in middleware**  CORS, CSRF, security headers, compression, body limits, request ID, logging
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
| You need true async concurrency (async DB drivers, hundreds of concurrent outbound HTTP calls) | FastAPI, Starlette |
| You need automatic OpenAPI / Swagger generation | FastAPI |
| You need ASGI and Uvicorn / Daphne | FastAPI, Starlette |
| You need a full MVC framework with ORM, admin panel, and migrations | Django |
| Your team is already on Flask and migration cost outweighs the benefit | Stay on Flask |

If your workload is primarily synchronous  REST APIs, internal services, microservices with sync DB drivers  Lcore is a strong fit.

## License

MIT  see [LICENSE](LICENSE) for details.

---

<p align="center">
  Built by <a href="https://lusansapkota.com.np">Lusan Sapkota</a> &bull; Inspired by <a href="https://bottlepy.org">Bottle</a>
</p>
