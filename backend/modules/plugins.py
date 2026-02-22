"""
Custom plugins and middleware demonstrating:
  - Writing a custom Plugin (setup/apply lifecycle)
  - Writing a custom Middleware (__call__ pattern)
  - Writing a MiddlewareHook (pre/post pattern)
  - Response timing
  - Request audit logging
  - API versioning plugin
"""
import os
import sys
import time
import json
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from lcore import Middleware, MiddlewareHook, HTTPResponse, response


# ─── Custom Middleware: Response Timing ──────────────────────

class TimingMiddleware(Middleware):
    """Adds X-Response-Time header to every response.

    Demonstrates custom Middleware subclass with __call__.
    """
    name = 'timing'
    order = 2

    def __call__(self, ctx, next_handler):
        start = time.time()
        result = next_handler(ctx)
        duration = time.time() - start
        ctx.response.set_header('X-Response-Time', f'{duration * 1000:.2f}ms')
        return result


# ─── Custom MiddlewareHook: Audit Logger ─────────────────────

class AuditLogHook(MiddlewareHook):
    """Logs all state-changing requests (POST, PUT, PATCH, DELETE).

    Demonstrates MiddlewareHook with pre() and post() methods.
    """
    name = 'audit_log'
    order = 8

    def __init__(self):
        self.logger = logging.getLogger('audit')

    def pre(self, ctx):
        if ctx.request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            ctx.state['audit_start'] = time.time()
            self.logger.info(
                f"[AUDIT] {ctx.request.method} {ctx.request.path} "
                f"from {ctx.request.remote_addr}"
            )
        return None

    def post(self, ctx, result):
        if 'audit_start' in ctx.state:
            duration = time.time() - ctx.state['audit_start']
            self.logger.info(
                f"[AUDIT] Completed {ctx.request.method} {ctx.request.path} "
                f"-> {ctx.response.status_code} ({duration * 1000:.1f}ms)"
            )
        return result


# ─── Custom Plugin: API Versioning ───────────────────────────

class APIVersionPlugin:
    """Adds API version info to every JSON response.

    Demonstrates:
      - Plugin class with setup/apply lifecycle
      - Per-route config (route.config)
      - Wrapping route callbacks
      - Skipping via route config
    """
    name = 'api_version'
    api = 2

    def __init__(self, version='0.0.1'):
        self.version = version

    def setup(self, app):
        """Called once when the plugin is installed."""
        self.app = app
        print(f"  [Plugin] APIVersionPlugin v{self.version} installed")

    def apply(self, callback, route):
        """Called for each route. Wraps the callback."""
        # Skip if route opts out
        if route.config.get('skip_versioning'):
            return callback

        version = self.version

        def wrapper(*args, **kwargs):
            result = callback(*args, **kwargs)
            if isinstance(result, dict):
                result['_api_version'] = version
            response.set_header('X-API-Version', version)
            return result

        return wrapper


# ─── Custom Plugin: Request Counter ──────────────────────────

class RequestCounterPlugin:
    """Tracks total request count per route.

    Demonstrates:
      - Simple stateful plugin
      - Plugin with close() cleanup
    """
    name = 'request_counter'
    api = 2

    def __init__(self):
        self.counts = {}

    def setup(self, app):
        self.app = app

    def apply(self, callback, route):
        rule = route.rule
        self.counts.setdefault(rule, 0)
        counts = self.counts

        def wrapper(*args, **kwargs):
            counts[rule] = counts.get(rule, 0) + 1
            result = callback(*args, **kwargs)
            if isinstance(result, dict):
                result['_request_number'] = counts[rule]
            return result

        return wrapper

    def get_stats(self):
        return dict(self.counts)

    def close(self):
        """Called when plugin is uninstalled."""
        print(f"  [Plugin] RequestCounterPlugin closed. Final stats: {self.counts}")
