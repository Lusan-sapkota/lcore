# TaskFlow API

> A real-world project management API (like Trello/Jira) built with the **Lcore** framework.
> This backend demonstrates every feature Lcore offers in a production-style codebase.

## Quick Start

```bash
cd backend
python app.py
```

The server starts at `http://localhost:8080` with a seeded SQLite database (3 users, 2 projects, 3 tasks).

**Demo credentials:**

| Username | Password  | Role   |
|----------|-----------|--------|
| admin    | admin123  | admin  |
| alice    | alice123  | member |
| bob      | bob123    | member |

```bash
# Login
curl -X POST http://localhost:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# Use the returned token
curl http://localhost:8080/api/users/ \
  -H "Authorization: Bearer <token>"
```

---

## Project Structure

```
backend/
  app.py                  # Main entry point — wires everything together
  config.py               # Config loading + dataclass validation
  models.py               # SQLite database layer (schema + seed data)
  .env                    # Environment variables
  modules/
    __init__.py
    auth.py               # Token auth, Basic Auth, signed cookies, RBAC
    users.py              # Users CRUD (all HTTP methods)
    products.py           # Projects + Tasks + Comments + File uploads
    notifications.py      # SMTP email sending + async batch
    plugins.py            # Custom plugins + custom middleware
  templates/
    welcome.tpl           # API overview + interactive playground
    frontend.tpl          # Full project management frontend (SPA)
    error.tpl             # Error page template
  static/                 # Static file directory
  uploads/                # File upload directory
```

---

## API Endpoints

### Auth (`/auth/`)

| Method | Path               | Description                      |
|--------|--------------------|----------------------------------|
| POST   | `/auth/login`      | Login, returns signed token + session cookie |
| POST   | `/auth/register`   | Register new account             |
| GET    | `/auth/me`         | Current user (from signed cookie)|
| POST   | `/auth/logout`     | Clear session cookie             |
| GET    | `/auth/basic-demo` | HTTP Basic Auth demo             |

### Users (`/api/users/`)

| Method | Path                    | Description                    |
|--------|-------------------------|--------------------------------|
| GET    | `/api/users/`           | List with pagination           |
| POST   | `/api/users/`           | Create user (admin only)       |
| GET    | `/api/users/<id>`       | Get by ID                      |
| PUT    | `/api/users/<id>`       | Full update (admin or self)    |
| PATCH  | `/api/users/<id>`       | Partial update (admin only)    |
| DELETE | `/api/users/<id>`       | Delete (admin only)            |
| GET    | `/api/users/search?q=`  | Search by name/email           |

### Projects & Tasks (`/api/projects/`)

| Method | Path                                          | Description                  |
|--------|-----------------------------------------------|------------------------------|
| GET    | `/api/projects/`                              | List projects                |
| POST   | `/api/projects/`                              | Create project (admin only)  |
| GET    | `/api/projects/<id>`                          | Get with task stats          |
| PUT    | `/api/projects/<id>`                          | Update project (admin only)  |
| DELETE | `/api/projects/<id>`                          | Delete cascade (admin only)  |
| GET    | `/api/projects/<id>/tasks`                    | List tasks (filterable) |
| POST   | `/api/projects/<id>/tasks`                    | Create task          |
| GET    | `/api/projects/<id>/tasks/<tid>`              | Get task + comments  |
| PATCH  | `/api/projects/<id>/tasks/<tid>`              | Update task          |
| DELETE | `/api/projects/<id>/tasks/<tid>`              | Delete task          |
| POST   | `/api/projects/<id>/tasks/<tid>/comments`     | Add comment          |
| POST   | `/api/projects/<id>/tasks/<tid>/attachment`   | Upload file          |
| GET    | `/api/projects/attachments/<filename>`        | Serve attachment     |
| GET    | `/api/projects/dashboard/overview`            | Dashboard (async)    |
| GET    | `/api/projects/dashboard/activity`            | Activity feed        |

### Notifications (`/api/notifications/`)

| Method | Path                                     | Description              |
|--------|------------------------------------------|--------------------------|
| POST   | `/api/notifications/email`               | Send email (simulated)   |
| POST   | `/api/notifications/task-assigned/<id>`  | Assignment notification  |
| POST   | `/api/notifications/async-batch`         | Batch send (async)       |
| GET    | `/api/notifications/history`             | Notification log         |

### System

| Method | Path                | Description                        |
|--------|---------------------|------------------------------------|
| GET    | `/`                 | API overview + interactive playground |
| GET    | `/frontend`         | Project management frontend (SPA)  |
| GET    | `/health`           | Health check                       |
| GET    | `/docs`             | Auto-generated API docs (debug)    |
| GET    | `/admin/dashboard`  | Admin panel (admin role only)      |
| GET    | `/admin/users`      | All users (admin only)             |
| GET    | `/debug/routes`     | Route inspection                   |
| GET    | `/debug/middleware`  | Middleware stack                    |
| GET    | `/debug/config`     | Config (secrets redacted)          |
| GET    | `/debug/stats`      | Request counter plugin stats       |
| GET    | `/debug/di`         | Dependency injection demo          |
| GET    | `/old-api`          | Redirect demo (301)                |

---

## Lcore Features Demonstrated

Every feature below is actively used in this backend, verified with a **30/30 passing test suite**.

### Configuration (3 sources + validation)

```
config.py → load_dict() → load_dotenv() → load_env('APP_') → validate_config(dataclass)
```

- **`load_dict()`** — Default values from a Python dict
- **`load_dotenv()`** — Override from `.env` file
- **`load_env('APP_')`** — Override from environment variables with prefix stripping
- **`validate_config(AppConfigSchema)`** — Validate against a dataclass schema with type coercion

### Middleware Stack (10 active)

All 7 built-in middleware + 3 custom, ordered by priority:

| Order | Middleware              | Type     | Purpose                          |
|-------|-------------------------|----------|----------------------------------|
| 0     | BodyLimitMiddleware     | Built-in | Reject oversized request bodies  |
| 1     | RequestIDMiddleware     | Built-in | Generate/propagate X-Request-ID  |
| 2     | RequestLoggerMiddleware | Built-in | Structured JSON request logging  |
| 2     | TimingMiddleware        | Custom   | X-Response-Time header           |
| 3     | CORSMiddleware          | Built-in | Full CORS with preflight         |
| 5     | SecurityHeadersMiddleware| Built-in| HSTS, XSS, clickjacking headers  |
| 6     | TokenAuthMiddleware     | Custom   | Bearer token validation          |
| 7     | AdminGuardHook          | Custom   | RBAC for /admin/* routes         |
| 8     | AuditLogHook            | Custom   | Log state-changing requests      |
| 90    | CompressionMiddleware   | Built-in | Gzip compression                 |

> **CSRFMiddleware** is imported but commented out — it's designed for server-rendered form apps, not JSON APIs with Bearer token auth.

### Custom Middleware Types

- **`Middleware` subclass** (`TimingMiddleware`) — Wraps request with `__call__(ctx, next_handler)`
- **`MiddlewareHook` subclass** (`AdminGuardHook`, `AuditLogHook`) — Pre/post pattern with `pre(ctx)` and `post(ctx, result)`, can short-circuit by returning `HTTPResponse`

### Plugins (2 custom)

| Plugin               | Purpose                                    |
|----------------------|--------------------------------------------|
| APIVersionPlugin     | Adds `_api_version` to JSON + X-API-Version header. Per-route skip via `skip_versioning=True` |
| RequestCounterPlugin | Tracks per-route hit counts. Has `close()` cleanup |

Both implement the `setup(app)` / `apply(callback, route)` plugin lifecycle.

### Authentication & Authorization

- **Token auth** — HMAC-SHA256 signed tokens (base64 JSON payload + signature), validated by `TokenAuthMiddleware`
- **Password hashing** — Uses Lcore's built-in `hash_password()` / `verify_password()` (PBKDF2-SHA256 with random salt, 600k iterations)
- **HTTP Basic Auth** — `@auth_basic` decorator on `/auth/basic-demo`
- **Signed cookies** — HMAC-SHA256 session cookies via `response.set_cookie(secret=...)` and `request.get_cookie(secret=...)`
- **RBAC (Route-level)** — `AdminGuardHook` restricts `/admin/*` to users with `role: admin`
- **RBAC (Endpoint-level)** — `_require_admin()` guards on write endpoints: create/update/delete projects, create/patch/delete users. Users can update their own profile via `PUT /api/users/<id>` (admin or self check)

### Dependency Injection (3 lifetimes)

```python
app.inject('cache', AppCache, lifetime='singleton')    # One instance for app lifetime
app.inject('db', lambda: Database(path), lifetime='scoped')  # One per request
app.inject('trace_id', lambda: str(uuid.uuid4()), lifetime='transient')  # New each access
```

Accessed via `ctx.cache`, `ctx.db`, `ctx.trace_id`.

### Route Features

- **All HTTP methods** — `@app.get`, `@app.post`, `@app.put`, `@app.patch`, `@app.delete`
- **Typed parameters** — `<id:int>`, `<filepath:path>`
- **Custom filters** — `slug` filter: `<slug:slug>` matching `[a-z0-9]+(-[a-z0-9]+)*`
- **Named routes** — `name='list_users'` for URL building via `app.get_url()`
- **Module mounting** — Sub-apps mounted at URL prefixes (`/auth/`, `/api/users/`, etc.)
- **Async handlers** — `async def` with `asyncio.gather` for concurrent DB queries
- **Redirect** — `redirect('/new-path', 301)`

### Request/Response

- **`request.json`** — Auto-parsed JSON body
- **`request.query`** — Query string parameters
- **`request.files`** — File uploads with `FileUpload.save()`
- **`request.auth`** — Basic auth credentials tuple
- **`response.status`** — Set HTTP status code
- **`response.set_header()`** — Set response headers
- **Static file serving** — `static_file()` with ETag, Range, and Cache-Control

### Validation

- **`@validate_request(body={...})`** — Validate JSON body fields and types
- **`@validate_request(query={...})`** — Validate query parameters
- **`@rate_limit(n, per=60)`** — Token bucket rate limiting per IP

### Templates (SimpleTemplate)

`.tpl` files are **Lcore's built-in SimpleTemplate** format. They are standard HTML files with embedded Python:

```html
<!-- Variable output -->
<h1>{{title}}</h1>

<!-- Loop -->
% for item in items:
  <li>{{item['name']}}</li>
% end

<!-- Conditional -->
% if user:
  <p>Hello, {{user}}!</p>
% end
```

- Templates live in `templates/` and are registered via `TEMPLATE_PATH`
- Rendered with `template('name', key=value)`
- Full HTML support — `.tpl` files are just HTML with template tags
- Also supports Jinja2, Mako, and Cheetah adapters

### Lifecycle Hooks

| Hook               | Where Used            | Purpose                        |
|---------------------|-----------------------|--------------------------------|
| `on_request_start`  | app.py                | Record request start time      |
| `before_request`    | app.py, users.py      | Log incoming request           |
| `after_request`     | app.py                | Add X-Powered-By header        |
| `on_response_send`  | app.py                | Log response with duration     |
| `on_module_mount`   | app.py                | Log mounted sub-applications   |

### Error Handling

Custom handlers for 404, 500, 429, 403 with content negotiation:
- JSON response if `Accept: application/json`
- HTML template otherwise (via `error.tpl`)

### Auto API Docs

When `debug=true`, `app.enable_docs()` generates interactive API documentation at `/docs`.

### Graceful Shutdown

```python
@on_shutdown
def cleanup():
    logger.info("Final stats: ...")
```

---

## Frontend Application

The project includes a full single-page frontend at `/frontend` built entirely with Lcore's SimpleTemplate engine — no build tools, no npm, no frameworks. Just HTML, CSS, and vanilla JavaScript served by the backend.

### Pages

| Page           | Description                                                    |
|----------------|----------------------------------------------------------------|
| Login          | Demo credential quick-fill, token stored in localStorage       |
| Dashboard      | Stats overview, project summary, recent activity feed          |
| Projects       | List all projects, create/delete (admin only)                  |
| Project Detail | Kanban task board (To Do / In Progress / Done), create tasks   |
| Task Detail    | Full task view, status changes, comments thread, delete (admin)|
| Team           | Member list with roles, add/remove members (admin only)        |
| Notifications  | Email history log, send emails                                 |
| My Profile     | View/edit own username and email, account info and permissions  |

### Role-Based UI

- **Admin** sees all CRUD buttons: create projects, add/remove team members, delete tasks
- **Member** sees read-only views for projects and team, but can create/update tasks and post comments
- Backend enforces the same rules — even if a member bypasses the UI, the API returns 403

---

## WebSocket Support

**Lcore does not natively support WebSockets.** It is a WSGI framework, and WSGI is a synchronous request/response protocol that does not support persistent bidirectional connections.

However, a companion WebSocket library designed to work alongside the Lcore framework is currently in development and will be released in a later phase. This will allow you to run a WebSocket server side-by-side with your Lcore application, sharing configuration, auth, and application logic.

In the meantime, you can:
- Use a separate WebSocket server (e.g., `websockets`, `socket.io`) alongside Lcore
- Or use an ASGI framework for WebSocket-only services

---

## Test Results

All 30 endpoint tests pass:

```
  PASS: Unauthenticated = 401
  PASS: Login
  PASS: Register
  PASS: Basic Auth
  PASS: Health
  PASS: List users
  PASS: Get user
  PASS: Create user
  PASS: Patch user
  PASS: Search users
  PASS: List projects
  PASS: Get project
  PASS: Create project
  PASS: List tasks
  PASS: Create task
  PASS: Update task
  PASS: Get task
  PASS: Add comment
  PASS: Send email
  PASS: Batch notify
  PASS: History
  PASS: Dashboard (async)
  PASS: Activity
  PASS: Admin (admin)
  PASS: Admin (member=403)
  PASS: Routes
  PASS: Middleware
  PASS: Config
  PASS: Stats
  PASS: Redirect 301

  30 passed, 0 failed
```
