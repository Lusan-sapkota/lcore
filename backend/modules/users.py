"""
Users module (mounted at /api/users/) demonstrating:
  - Module mounting, module-scoped hooks
  - Typed route parameters (<id:int>)
  - All HTTP shorthand decorators (get, post, put, patch, delete)
  - @rate_limit, @validate_request
  - Query parameters with pagination
  - Named routes
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from lcore import Lcore, request, response, ctx, abort, rate_limit, validate_request
from models import Database, hash_password

users_app = Lcore()


def _require_admin():
    """Abort 403 if current user is not an admin."""
    user = getattr(ctx, 'user', None)
    if not user or user.get('role') != 'admin':
        abort(403, 'Admin access required')


@users_app.hook('before_request')
def log_user_request():
    print(f"  [Users] {request.method} {request.path}")


def _get_db():
    return Database()


@users_app.get('/', name='list_users')
@rate_limit(100, per=60)
def list_users():
    """List all team members with optional role filter and pagination."""
    db = _get_db()
    try:
        role = request.query.get('role')
        page = int(request.query.get('page', '1'))
        limit = int(request.query.get('limit', '20'))
        offset = (page - 1) * limit

        if role:
            users = db.fetchall(
                "SELECT id, username, email, role, is_active, created_at FROM users WHERE role = ? LIMIT ? OFFSET ?",
                (role, limit, offset)
            )
            total = db.fetchone("SELECT COUNT(*) as cnt FROM users WHERE role = ?", (role,))['cnt']
        else:
            users = db.fetchall(
                "SELECT id, username, email, role, is_active, created_at FROM users LIMIT ? OFFSET ?",
                (limit, offset)
            )
            total = db.count('users')

        return {'users': users, 'total': total, 'page': page, 'limit': limit}
    finally:
        db.close()


@users_app.get('/<id:int>', name='get_user')
@rate_limit(200, per=60)
def get_user(id):
    """Fetch a team member by ID."""
    db = _get_db()
    try:
        user = db.fetchone(
            "SELECT id, username, email, role, is_active, avatar, created_at FROM users WHERE id = ?",
            (id,)
        )
        if not user:
            abort(404, 'User not found')
        return user
    finally:
        db.close()


@users_app.post('/', name='create_user')
@rate_limit(20, per=60)
@validate_request(body={'username': str, 'email': str, 'password': str})
def create_user():
    """Invite a new team member. Admin only."""
    _require_admin()
    data = request.json
    db = _get_db()
    try:
        if db.fetchone("SELECT id FROM users WHERE username = ?", (data['username'],)):
            abort(409, 'Username already exists')
        if db.fetchone("SELECT id FROM users WHERE email = ?", (data['email'],)):
            abort(409, 'Email already registered')

        user_id = db.insert('users', {
            'username': data['username'],
            'email': data['email'],
            'password_hash': hash_password(data['password']),
            'role': data.get('role', 'member'),
            'is_active': 1,
        })
        response.status = 201
        return {'id': user_id, 'username': data['username'], 'created': True}
    finally:
        db.close()


@users_app.put('/<id:int>', name='update_user')
@rate_limit(50, per=60)
@validate_request(body={'username': str, 'email': str})
def update_user(id):
    """Full update of a user profile. Admin or self only."""
    user = getattr(ctx, 'user', None)
    if not user or (user.get('role') != 'admin' and user.get('id') != id):
        abort(403, 'Admin access required or can only update own profile')
    data = request.json
    db = _get_db()
    try:
        if not db.fetchone("SELECT id FROM users WHERE id = ?", (id,)):
            abort(404, 'User not found')
        db.update('users', id, {'username': data['username'], 'email': data['email']})
        return {'id': id, 'updated': True}
    finally:
        db.close()


@users_app.patch('/<id:int>', name='patch_user')
@rate_limit(50, per=60)
def patch_user(id):
    """Partial update (change role, deactivate, etc.). Admin only."""
    _require_admin()
    data = request.json
    if not data:
        abort(400, 'No data provided')
    db = _get_db()
    try:
        if not db.fetchone("SELECT id FROM users WHERE id = ?", (id,)):
            abort(404, 'User not found')
        allowed = {'username', 'email', 'role', 'is_active'}
        update_data = {k: v for k, v in data.items() if k in allowed}
        if not update_data:
            abort(400, 'No valid fields to update')
        db.update('users', id, update_data)
        return {'id': id, 'patched': True, 'fields': list(update_data.keys())}
    finally:
        db.close()


@users_app.delete('/<id:int>', name='delete_user')
@rate_limit(10, per=60)
def delete_user(id):
    """Remove a team member. Admin only."""
    _require_admin()
    db = _get_db()
    try:
        if not db.fetchone("SELECT id FROM users WHERE id = ?", (id,)):
            abort(404, 'User not found')
        db.delete('users', id)
        return {'id': id, 'deleted': True}
    finally:
        db.close()


@users_app.get('/search', name='search_users')
@rate_limit(50, per=60)
@validate_request(query={'q': str})
def search_users():
    """Search team members by name or email."""
    q = request.query.get('q', '')
    db = _get_db()
    try:
        users = db.fetchall(
            "SELECT id, username, email, role FROM users WHERE username LIKE ? OR email LIKE ?",
            (f'%{q}%', f'%{q}%')
        )
        return {'query': q, 'results': users, 'count': len(users)}
    finally:
        db.close()
