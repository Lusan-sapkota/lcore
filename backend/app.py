"""
TaskFlow API - Project Management Backend built with Lcore
==========================================================

A real-world project management API (like Trello/Jira) demonstrating
every feature of the Lcore framework. Run with: python app.py

Features demonstrated:
  - SQLite database with real schema
  - .env + env var config loading + dataclass validation
  - All 7 built-in middleware (CORS, CSRF, SecurityHeaders, BodyLimit,
    RequestID, RequestLogger, Compression)
  - Custom middleware (TimingMiddleware, AuditLogHook)
  - Custom plugins (APIVersionPlugin, RequestCounterPlugin)
  - Module mounting (auth, users, projects, notifications)
  - Route groups (/admin, /debug)
  - Dependency injection (singleton, scoped, transient)
  - All HTTP methods (GET, POST, PUT, PATCH, DELETE)
  - Typed route parameters (<id:int>, <filepath:path>)
  - Custom route filters (slug)
  - Rate limiting, request validation
  - HTTP Basic Auth + token auth + signed cookies
  - File uploads + static file serving
  - SMTP email sending
  - Async route handlers
  - SimpleTemplate rendering
  - 12 lifecycle hooks
  - Custom error handlers (404, 500, 429, 403)
  - Auto API docs at /docs
  - Redirect, named routes, URL building
  - Graceful shutdown with @on_shutdown
"""
import os
import sys
import time
import uuid
import logging

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lcore import (
    Lcore, request, response, ctx, abort, redirect, static_file,
    template, TEMPLATE_PATH, on_shutdown, rate_limit,
    CORSMiddleware, SecurityHeadersMiddleware, CSRFMiddleware,
    RequestIDMiddleware, RequestLoggerMiddleware,
    BodyLimitMiddleware, CompressionMiddleware,
)

from config import configure_app
from models import Database, init_db

import modules.auth as auth_module
from modules.auth import auth_app, TokenAuthMiddleware, AdminGuardHook
from modules.users import users_app
from modules.products import projects_app
from modules.notifications import notifications_app

from modules.plugins import (
    TimingMiddleware, AuditLogHook,
    APIVersionPlugin, RequestCounterPlugin,
)

# ─── Logging ────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('taskflow')

# ─── Create App & Load Config ──────────────────────────────

app = Lcore()
configure_app(app)

# Initialize SQLite database
db_path = app.config.get('db_path', './taskflow.db')
if not os.path.isabs(db_path):
    db_path = os.path.join(os.path.dirname(__file__), db_path)
init_db(db_path)

# Set auth secret
auth_module.SECRET = app.config.get('secret_key', 'default-secret-key')

# Template path
TEMPLATE_PATH.insert(0, os.path.join(os.path.dirname(__file__), 'templates'))

# ═══════════════════════════════════════════════════════════
#  MIDDLEWARE STACK (all 7 built-in + 4 custom)
# ═══════════════════════════════════════════════════════════

app.use(BodyLimitMiddleware(
    max_size=int(app.config.get('max_upload_size', 10_485_760))
))
app.use(RequestIDMiddleware())
app.use(RequestLoggerMiddleware(logger=logging.getLogger('http')))
app.use(TimingMiddleware())

cors_origins = app.config.get('cors_origins', '*')
if isinstance(cors_origins, str) and ',' in cors_origins:
    cors_origins = [o.strip() for o in cors_origins.split(',')]
app.use(CORSMiddleware(
    allow_origins=cors_origins,
    allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
    allow_headers=['Content-Type', 'Authorization', 'X-CSRF-Token', 'X-Requested-With'],
    expose_headers=['X-Request-ID', 'X-Response-Time', 'X-API-Version'],
    allow_credentials=True,
    max_age=86400,
))

app.use(SecurityHeadersMiddleware(hsts=True, hsts_max_age=31536000))

app.use(TokenAuthMiddleware(
    skip_paths=['/auth/', '/health', '/docs', '/', '/frontend', '/playground/', '/static/', '/debug/', '/old-api']
))
app.use(AdminGuardHook())
app.use(AuditLogHook())

# Note: CSRFMiddleware is available (imported above) for form-based apps.
# For this JSON API with Bearer token auth, CSRF is unnecessary since
# cross-origin requests can't set custom Authorization headers.
# Uncomment below for server-rendered form-based apps:
#   app.use(CSRFMiddleware(
#       secret=app.config.get('secret_key', 'csrf-secret'),
#       cookie_name='_csrf_token',
#       header_name='X-CSRF-Token',
#   ))

app.use(CompressionMiddleware(min_size=256, level=6))

# ═══════════════════════════════════════════════════════════
#  PLUGINS
# ═══════════════════════════════════════════════════════════

version_plugin = APIVersionPlugin(version='0.0.1')
app.install(version_plugin)

counter_plugin = RequestCounterPlugin()
app.install(counter_plugin)

# ═══════════════════════════════════════════════════════════
#  DEPENDENCY INJECTION
# ═══════════════════════════════════════════════════════════

class AppCache:
    """In-memory cache (singleton lifetime)."""
    def __init__(self):
        self._store = {}

    def get(self, key):
        entry = self._store.get(key)
        if entry and entry['expires'] > time.time():
            return entry['value']
        return None

    def set(self, key, value, ttl=300):
        self._store[key] = {'value': value, 'expires': time.time() + ttl}

    def invalidate(self, key):
        self._store.pop(key, None)

app.inject('cache', AppCache, lifetime='singleton')
app.inject('db', lambda: Database(db_path), lifetime='scoped')
app.inject('trace_id', lambda: str(uuid.uuid4()), lifetime='transient')

# ═══════════════════════════════════════════════════════════
#  LIFECYCLE HOOKS
# ═══════════════════════════════════════════════════════════

@app.hook('on_request_start')
def on_request_start():
    ctx.state['start_time'] = time.time()

@app.hook('before_request')
def before_request():
    logger.info(f"-> {request.method} {request.path}")

@app.hook('after_request')
def after_request():
    response.set_header('X-Powered-By', 'Lcore')

@app.hook('on_response_send')
def on_response_send():
    start = ctx.state.get('start_time', 0)
    duration = (time.time() - start) * 1000
    logger.info(f"<- {request.method} {request.path} [{response.status_code}] {duration:.1f}ms")

@app.hook('on_module_mount')
def on_module_mount(prefix, child):
    logger.info(f"  Mounted module at {prefix}")

# ═══════════════════════════════════════════════════════════
#  MOUNT SUB-APPLICATIONS
# ═══════════════════════════════════════════════════════════

app.mount('/auth/', auth_app)
app.mount('/api/users/', users_app)
app.mount('/api/projects/', projects_app)
app.mount('/api/notifications/', notifications_app)

# ═══════════════════════════════════════════════════════════
#  ROOT ROUTES
# ═══════════════════════════════════════════════════════════

@app.get('/', name='home', skip_versioning=True)
def home():
    """TaskFlow welcome page with API overview."""
    return template('welcome',
        title='TaskFlow API',
        description='Project management API built with the Lcore framework',
        version='0.0.1',
        host=app.config.get('host', '0.0.0.0'),
        port=app.config.get('port', '8080'),
        features=[
            {'name': 'SQLite DB', 'desc': 'Real database with projects, tasks, users, comments'},
            {'name': '.env Config', 'desc': 'Multi-source config loading + dataclass validation'},
            {'name': '11 Middleware', 'desc': '7 built-in + 4 custom (timing, auth, admin, audit)'},
            {'name': 'Auth System', 'desc': 'Token auth, Basic auth, signed cookies, RBAC'},
            {'name': 'Rate Limiting', 'desc': 'Token bucket per-IP rate limiting on every endpoint'},
            {'name': 'Validation', 'desc': 'Body + query parameter schema validation'},
            {'name': 'File Uploads', 'desc': 'Task attachments with static file serving'},
            {'name': 'SMTP Email', 'desc': 'Task assignment notifications via smtplib'},
            {'name': 'Async Routes', 'desc': 'Dashboard overview uses asyncio.gather'},
            {'name': 'DI Container', 'desc': 'Singleton cache, scoped DB, transient trace IDs'},
            {'name': 'Custom Plugins', 'desc': 'API versioning + request counter plugins'},
            {'name': 'Auto API Docs', 'desc': 'Interactive docs at /docs (debug mode)'},
        ],
        endpoint_groups=[
            {'name': 'Auth', 'endpoints': [
                {'method': 'POST', 'path': '/auth/login', 'desc': 'Login with credentials'},
                {'method': 'POST', 'path': '/auth/register', 'desc': 'Register new account'},
                {'method': 'GET', 'path': '/auth/me', 'desc': 'Get current user (cookie)'},
                {'method': 'POST', 'path': '/auth/logout', 'desc': 'Clear session'},
                {'method': 'GET', 'path': '/auth/basic-demo', 'desc': 'HTTP Basic Auth demo'},
            ]},
            {'name': 'Users', 'endpoints': [
                {'method': 'GET', 'path': '/api/users/', 'desc': 'List team members'},
                {'method': 'POST', 'path': '/api/users/', 'desc': 'Invite member'},
                {'method': 'GET', 'path': '/api/users/<id>', 'desc': 'Get member profile'},
                {'method': 'PUT', 'path': '/api/users/<id>', 'desc': 'Update profile'},
                {'method': 'PATCH', 'path': '/api/users/<id>', 'desc': 'Change role/status'},
                {'method': 'DELETE', 'path': '/api/users/<id>', 'desc': 'Remove member'},
                {'method': 'GET', 'path': '/api/users/search?q=', 'desc': 'Search members'},
            ]},
            {'name': 'Projects & Tasks', 'endpoints': [
                {'method': 'GET', 'path': '/api/projects/', 'desc': 'List projects'},
                {'method': 'POST', 'path': '/api/projects/', 'desc': 'Create project'},
                {'method': 'GET', 'path': '/api/projects/<id>', 'desc': 'Project detail + stats'},
                {'method': 'GET', 'path': '/api/projects/<id>/tasks', 'desc': 'List tasks'},
                {'method': 'POST', 'path': '/api/projects/<id>/tasks', 'desc': 'Create task'},
                {'method': 'PATCH', 'path': '/api/projects/<id>/tasks/<tid>', 'desc': 'Update task'},
                {'method': 'POST', 'path': '/api/projects/<id>/tasks/<tid>/comments', 'desc': 'Add comment'},
                {'method': 'POST', 'path': '/api/projects/<id>/tasks/<tid>/attachment', 'desc': 'Upload file'},
                {'method': 'GET', 'path': '/api/projects/dashboard/overview', 'desc': 'Dashboard (async)'},
            ]},
            {'name': 'Notifications', 'endpoints': [
                {'method': 'POST', 'path': '/api/notifications/email', 'desc': 'Send email'},
                {'method': 'POST', 'path': '/api/notifications/task-assigned/<id>', 'desc': 'Assignment email'},
                {'method': 'POST', 'path': '/api/notifications/async-batch', 'desc': 'Batch (async)'},
                {'method': 'GET', 'path': '/api/notifications/history', 'desc': 'Email log'},
            ]},
            {'name': 'System', 'endpoints': [
                {'method': 'GET', 'path': '/health', 'desc': 'Health check (skip plugins)'},
                {'method': 'GET', 'path': '/admin/dashboard', 'desc': 'Admin panel'},
                {'method': 'GET', 'path': '/debug/routes', 'desc': 'Route inspection'},
                {'method': 'GET', 'path': '/debug/middleware', 'desc': 'Middleware stack'},
                {'method': 'GET', 'path': '/debug/config', 'desc': 'Config (redacted)'},
                {'method': 'GET', 'path': '/debug/stats', 'desc': 'Request counter'},
            ]},
        ],
    )


@app.get('/frontend', name='frontend', skip_versioning=True)
def frontend():
    """TaskFlow frontend — full project management UI."""
    return template('frontend')


@app.post('/playground/run', name='playground_run', skip_versioning=True)
@rate_limit(30, per=60)
def playground_run():
    """Execute Lcore code in a sandboxed environment."""
    import io
    import threading

    code = request.json.get('code', '') if request.json else ''
    if not code.strip():
        return {'error': 'No code provided', 'output': ''}

    # Safety: limit code length
    if len(code) > 5000:
        return {'error': 'Code too long (max 5000 chars)', 'output': ''}

    # Block dangerous operations
    blocked = ['import os', 'import sys', 'import subprocess', 'import shutil',
               'exec(', 'eval(', 'open(', 'compile(',
               'os.system', 'os.popen', 'os.remove', 'os.unlink',
               'shutil.', 'subprocess.', 'socket.', 'import socket']
    for b in blocked:
        if b in code:
            return {'error': f'Blocked operation: {b}', 'output': ''}

    output = io.StringIO()

    # Safe __import__ that only allows whitelisted modules
    import lcore as _lcore
    _allowed_modules = {'lcore': _lcore, 'time': __import__('time'), 'json': __import__('json'),
                        'math': __import__('math'), 'random': __import__('random'),
                        'hashlib': __import__('hashlib'), 'functools': __import__('functools'),
                        'collections': __import__('collections'), 're': __import__('re')}

    def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name not in _allowed_modules:
            raise ImportError(f"Module '{name}' is not available in the playground")
        return _allowed_modules[name]

    sandbox_globals = {'__builtins__': {
        '__import__': _safe_import,
        '__build_class__': __builtins__['__build_class__'] if isinstance(__builtins__, dict) else __builtins__.__build_class__,
        '__name__': '<playground>',
        'print': lambda *a, **kw: print(*a, file=output, **kw),
        'range': range, 'len': len, 'str': str, 'int': int, 'float': float,
        'bool': bool, 'list': list, 'dict': dict, 'tuple': tuple, 'set': set,
        'True': True, 'False': False, 'None': None,
        'isinstance': isinstance, 'type': type, 'enumerate': enumerate,
        'zip': zip, 'map': map, 'filter': filter, 'sorted': sorted,
        'min': min, 'max': max, 'sum': sum, 'abs': abs, 'round': round,
        'hasattr': hasattr, 'getattr': getattr, 'setattr': setattr,
        'property': property, 'staticmethod': staticmethod, 'classmethod': classmethod,
        'super': super, 'object': object,
        'Exception': Exception, 'ValueError': ValueError, 'TypeError': TypeError,
        'KeyError': KeyError, 'IndexError': IndexError, 'ImportError': ImportError,
        'AttributeError': AttributeError, 'RuntimeError': RuntimeError,
        'StopIteration': StopIteration, 'NotImplementedError': NotImplementedError,
    }}

    # Inject lcore into sandbox
    sandbox_globals['lcore'] = _lcore
    sandbox_globals['Lcore'] = _lcore.Lcore
    sandbox_globals['TestClient'] = _lcore.TestClient
    sandbox_globals['TestResponse'] = _lcore.TestResponse
    sandbox_globals['hash_password'] = _lcore.hash_password
    sandbox_globals['verify_password'] = _lcore.verify_password
    sandbox_globals['BackgroundTaskPool'] = _lcore.BackgroundTaskPool
    sandbox_globals['rate_limit'] = _lcore.rate_limit
    sandbox_globals['validate_request'] = _lcore.validate_request
    sandbox_globals['HTTPError'] = _lcore.HTTPError
    sandbox_globals['request'] = _lcore.request
    sandbox_globals['response'] = _lcore.response
    sandbox_globals['abort'] = _lcore.abort
    sandbox_globals['redirect'] = _lcore.redirect
    sandbox_globals['Middleware'] = _lcore.Middleware

    # Execute with timeout to prevent infinite loops / hangs
    result = {'output': '', 'error': None}

    def _run():
        try:
            compiled = compile(code, '<playground>', 'exec')
            exec(compiled, sandbox_globals)
            result['output'] = output.getvalue()
        except Exception as e:
            result['output'] = output.getvalue()
            result['error'] = f'{type(e).__name__}: {e}'

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=10)

    if t.is_alive():
        return {'output': result['output'], 'error': 'Execution timed out (10s limit)'}

    return result


@app.get('/health', name='health')
def health():
    """Health check endpoint."""
    db = Database(db_path)
    try:
        return {
            'status': 'ok',
            'timestamp': time.time(),
            'db': {
                'users': db.count('users'),
                'projects': db.count('projects'),
                'tasks': db.count('tasks'),
            },
        }
    finally:
        db.close()


@app.get('/static/<filepath:path>', name='static')
def serve_static(filepath):
    """Serve static files with ETag and cache headers."""
    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    return static_file(filepath, root=static_dir,
                       headers={'Cache-Control': 'max-age=86400'})


# ═══════════════════════════════════════════════════════════
#  ADMIN ROUTES (AdminGuardHook protects /admin/*)
# ═══════════════════════════════════════════════════════════

@app.get('/admin/dashboard', name='admin_dashboard')
def admin_dashboard():
    """Admin dashboard - requires admin role token."""
    db = Database(db_path)
    try:
        return {
            'dashboard': 'admin',
            'counts': {
                'users': db.count('users'),
                'projects': db.count('projects'),
                'tasks': db.count('tasks'),
                'notifications': db.count('notifications'),
            },
        }
    finally:
        db.close()


@app.get('/admin/users', name='admin_users')
def admin_list_users():
    """Admin: list all users with all fields."""
    db = Database(db_path)
    try:
        users = db.fetchall("SELECT * FROM users")
        return {'users': users, 'total': len(users)}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
#  DEBUG / INSPECTION ROUTES
# ═══════════════════════════════════════════════════════════

@app.get('/debug/routes', name='debug_routes')
def debug_routes():
    """Route inspection via app.show_routes()."""
    routes = app.show_routes()
    return {
        'routes': [
            {'method': r.get('method', 'GET'), 'rule': r.get('rule', ''), 'name': r.get('name')}
            for r in routes
        ],
        'total': len(routes),
    }


@app.get('/debug/middleware', name='debug_middleware')
def debug_middleware():
    """Middleware stack via app.show_middleware()."""
    mw_list = app.show_middleware()
    return {
        'middleware': [
            {'name': m.get('name', '?'), 'order': m.get('order', 50), 'type': m.get('type', '?')}
            for m in mw_list
        ],
        'total': len(mw_list),
    }


@app.get('/debug/config', name='debug_config')
def debug_config():
    """Show config with sensitive values redacted."""
    sensitive = {'secret_key', 'smtp_password', 'password'}
    safe = {}
    for key in app.config:
        if any(s in key.lower() for s in sensitive):
            safe[key] = '***REDACTED***'
        else:
            safe[key] = str(app.config[key])
    return {'config': safe}


@app.get('/debug/stats', name='debug_stats')
def debug_stats():
    """Plugin request counter stats."""
    return {'route_stats': counter_plugin.get_stats()}


@app.get('/debug/di', name='debug_di')
def debug_di():
    """Dependency injection demo - shows different lifetimes."""
    return {
        'trace_id_1': ctx.trace_id,
        'trace_id_2': ctx.trace_id,  # Different each access (transient)
        'cache_type': type(ctx.cache).__name__,
        'db_type': type(ctx.db).__name__,
    }


# ═══════════════════════════════════════════════════════════
#  REDIRECT
# ═══════════════════════════════════════════════════════════

@app.get('/old-api', name='old_api')
def old_api():
    """Redirect demo - 301 Moved Permanently."""
    redirect('/api/projects/', 301)


# ═══════════════════════════════════════════════════════════
#  ERROR HANDLERS
# ═══════════════════════════════════════════════════════════

@app.error(404)
def error_404(error):
    import json as _json
    if 'application/json' in (request.get_header('Accept') or ''):
        response.content_type = 'application/json'
        return _json.dumps({'error': 'Not Found', 'path': request.path, 'status': 404})
    return template('error', status_code=404, status_text='Not Found',
                     message=f"The path '{request.path}' does not exist.")

@app.error(500)
def error_500(error):
    import json as _json
    if 'application/json' in (request.get_header('Accept') or ''):
        response.content_type = 'application/json'
        return _json.dumps({'error': 'Internal Server Error', 'status': 500})
    return template('error', status_code=500, status_text='Internal Server Error',
                     message='Something went wrong. Please try again later.')

@app.error(429)
def error_429(error):
    import json as _json
    response.content_type = 'application/json'
    return _json.dumps({'error': 'Too Many Requests', 'status': 429,
            'message': 'Rate limit exceeded. Please slow down.'})

@app.error(403)
def error_403(error):
    import json as _json
    response.content_type = 'application/json'
    return _json.dumps({'error': 'Forbidden', 'status': 403,
            'message': str(error.body) if error.body else 'You do not have permission to access this resource.'})


# ═══════════════════════════════════════════════════════════
#  GRACEFUL SHUTDOWN
# ═══════════════════════════════════════════════════════════

@on_shutdown
def cleanup():
    """Demonstrates @on_shutdown for cleanup."""
    logger.info("Shutting down TaskFlow...")
    logger.info(f"  Final stats: {counter_plugin.get_stats()}")
    logger.info("Goodbye!")


# ═══════════════════════════════════════════════════════════
#  API DOCS
# ═══════════════════════════════════════════════════════════

is_debug = str(app.config.get('debug', 'false')).lower() in ('true', '1', 'yes')
if is_debug:
    app.enable_docs()
    logger.info("  API docs at /docs")


# ═══════════════════════════════════════════════════════════
#  STARTUP
# ═══════════════════════════════════════════════════════════

if __name__ == '__main__':
    host = app.config.get('host', '0.0.0.0')
    port = int(app.config.get('port', 8080))

    print()
    print("=" * 60)
    print("  TaskFlow API - Built with Lcore")
    print("=" * 60)
    print()
    print(f"  Server:    http://{host}:{port}")
    print(f"  Database:  {db_path}")
    print(f"  Debug:     {is_debug}")
    print(f"  API Docs:  http://{host}:{port}/docs")
    print()

    routes = app.show_routes()
    print(f"  Routes:    {len(routes)} registered")

    mw = app.show_middleware()
    print(f"  Middleware: {len(mw)} active")
    for m in mw:
        print(f"    [{m.get('order', '?'):3}] {m.get('name', '?')}")

    print()
    print("  Demo credentials:")
    print("    admin / admin123  (role: admin)")
    print("    alice / alice123  (role: member)")
    print("    bob   / bob123    (role: member)")
    print()
    print("  Quick start:")
    print('    curl -X POST http://localhost:8080/auth/login \\')
    print('      -H "Content-Type: application/json" \\')
    print('      -d \'{"username":"admin","password":"admin123"}\'')
    print()
    print("=" * 60)
    print()

    app.run(host=host, port=port, debug=is_debug, reloader=is_debug)
