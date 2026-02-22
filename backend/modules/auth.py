"""
Authentication module for TaskFlow demonstrating:
  - Custom Middleware (token validation)
  - MiddlewareHook (pre/post for admin guard)
  - @auth_basic decorator
  - Signed cookies (HMAC-SHA256) for sessions
  - ctx.user for carrying auth state
  - @rate_limit on login
  - @validate_request on registration
"""
import os
import sys
import hashlib
import hmac
import time
import json
import base64

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from lcore import (
    Lcore, Middleware, MiddlewareHook, HTTPResponse,
    request, response, ctx, abort, auth_basic, rate_limit,
    validate_request,
)
from models import Database, hash_password, verify_password

SECRET = None  # Set from app config at startup


def _get_secret():
    return SECRET or 'default-secret-key'


# ─── Token helpers ──────────────────────────────────────────

def generate_token(user_id: int, username: str, role: str) -> str:
    """Generate a signed auth token (base64 JSON + HMAC-SHA256)."""
    payload = {
        'sub': user_id,
        'username': username,
        'role': role,
        'iat': int(time.time()),
        'exp': int(time.time()) + 3600,
    }
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).decode()
    signature = hmac.new(
        _get_secret().encode(), payload_b64.encode(), hashlib.sha256
    ).hexdigest()
    return f"{payload_b64}.{signature}"


def verify_token(token: str) -> dict | None:
    """Verify and decode a signed auth token."""
    try:
        payload_b64, signature = token.rsplit('.', 1)
        expected_sig = hmac.new(
            _get_secret().encode(), payload_b64.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        if payload.get('exp', 0) < time.time():
            return None
        return payload
    except Exception:
        return None


# ─── Token Auth Middleware ──────────────────────────────────

class TokenAuthMiddleware(Middleware):
    """Validates Bearer tokens on protected API routes.

    Demonstrates: custom Middleware, short-circuiting, ctx.user.
    """
    name = 'token_auth'
    order = 6

    def __init__(self, skip_paths=None):
        self.skip_paths = skip_paths or []

    def __call__(self, ctx, next_handler):
        path = ctx.request.path
        for skip in self.skip_paths:
            if skip == path:
                return next_handler(ctx)
            if len(skip) > 1 and skip.endswith('/') and path.startswith(skip):
                return next_handler(ctx)

        auth_header = ctx.request.get_header('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            ctx.response.status = 401
            return {'error': 'Missing or invalid Authorization header'}

        payload = verify_token(auth_header[7:])
        if not payload:
            ctx.response.status = 401
            return {'error': 'Invalid or expired token'}

        ctx.user = {
            'id': payload['sub'],
            'username': payload['username'],
            'role': payload['role'],
        }
        return next_handler(ctx)


# ─── Admin Guard (MiddlewareHook) ───────────────────────────

class AdminGuardHook(MiddlewareHook):
    """Restricts /admin/* to admin users. Demonstrates MiddlewareHook pre/post."""
    name = 'admin_guard'
    order = 7

    def pre(self, ctx):
        if not ctx.request.path.startswith('/admin'):
            return None
        user = getattr(ctx, 'user', None)
        if not user or user.get('role') != 'admin':
            return HTTPResponse(
                body=json.dumps({'error': 'Admin access required'}),
                status=403,
                headers={'Content-Type': 'application/json'}
            )
        return None

    def post(self, ctx, result):
        return result


# ─── Auth Sub-App (mounted at /auth/) ───────────────────────

auth_app = Lcore()


def _check_basic_auth(username, password):
    """Callback for @auth_basic - checks against SQLite."""
    db = Database()
    try:
        user = db.fetchone("SELECT * FROM users WHERE username = ?", (username,))
        if not user:
            return False
        return verify_password(password, user['password_hash'])
    finally:
        db.close()


@auth_app.post('/login')
@rate_limit(5, per=300)
@validate_request(body={'username': str, 'password': str})
def login():
    """Authenticate and return a signed token + session cookie."""
    data = request.json
    db = Database()
    try:
        user = db.fetchone("SELECT * FROM users WHERE username = ?", (data['username'],))
        if not user or not verify_password(data['password'], user['password_hash']):
            abort(401, 'Invalid credentials')

        token = generate_token(user['id'], user['username'], user['role'])

        response.set_cookie('session_user', user['username'],
                            secret=_get_secret(), path='/',
                            httponly=True, samesite='Lax', max_age=3600)

        return {
            'token': token,
            'user': {'id': user['id'], 'username': user['username'], 'role': user['role']}
        }
    finally:
        db.close()


@auth_app.post('/register')
@rate_limit(10, per=3600)
@validate_request(body={'username': str, 'email': str, 'password': str})
def register():
    """Register a new TaskFlow account."""
    data = request.json
    db = Database()
    try:
        if db.fetchone("SELECT id FROM users WHERE username = ?", (data['username'],)):
            abort(409, 'Username already taken')
        if db.fetchone("SELECT id FROM users WHERE email = ?", (data['email'],)):
            abort(409, 'Email already registered')

        user_id = db.insert('users', {
            'username': data['username'],
            'email': data['email'],
            'password_hash': hash_password(data['password']),
            'role': 'member',
            'is_active': 1,
        })
        response.status = 201
        return {'id': user_id, 'username': data['username'], 'registered': True}
    finally:
        db.close()


@auth_app.get('/me')
def me():
    """Get current user from signed session cookie."""
    username = request.get_cookie('session_user', secret=_get_secret())
    if not username:
        abort(401, 'Not authenticated')

    db = Database()
    try:
        user = db.fetchone(
            "SELECT id, username, email, role FROM users WHERE username = ?",
            (username,)
        )
        if not user:
            abort(401, 'Session invalid')
        return user
    finally:
        db.close()


@auth_app.post('/logout')
def logout():
    """Clear session cookie."""
    response.delete_cookie('session_user', path='/')
    return {'message': 'Logged out'}


@auth_app.get('/basic-demo')
@auth_basic(_check_basic_auth, realm='TaskFlow')
def basic_auth_demo():
    """Protected by HTTP Basic Auth. Try: curl -u admin:admin123 ..."""
    return {'message': 'Authenticated via HTTP Basic Auth!'}
