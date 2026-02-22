"""
Projects & Tasks module (mounted at /api/projects/) demonstrating:
  - File uploads (task attachments)
  - Static file serving
  - Route groups (bulk operations, task comments)
  - Custom route filters (UUID)
  - Named routes and URL building
  - Async route handler
"""
import os
import sys
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from lcore import (
    Lcore, request, response, ctx, abort,
    static_file, rate_limit, validate_request,
)
from models import Database

projects_app = Lcore()


def _require_admin():
    """Abort 403 if current user is not an admin."""
    user = getattr(ctx, 'user', None)
    if not user or user.get('role') != 'admin':
        abort(403, 'Admin access required')


# ─── Custom route filter: slug ──────────────────────────────

projects_app.add_route_filter(
    'slug',
    r'[a-z0-9]+(?:-[a-z0-9]+)*',
    to_python=lambda val: val,
    to_url=lambda val: str(val),
)


def _get_db():
    return Database()


# ═══════════════════════════════════════════════════════════
#  PROJECTS CRUD
# ═══════════════════════════════════════════════════════════

@projects_app.get('/', name='list_projects')
@rate_limit(100, per=60)
def list_projects():
    """List all projects with optional status filter."""
    db = _get_db()
    try:
        status = request.query.get('status')
        if status:
            projects = db.fetchall(
                """SELECT p.*, u.username as owner_name
                   FROM projects p JOIN users u ON p.owner_id = u.id
                   WHERE p.status = ?
                   ORDER BY p.created_at DESC""",
                (status,)
            )
        else:
            projects = db.fetchall(
                """SELECT p.*, u.username as owner_name
                   FROM projects p JOIN users u ON p.owner_id = u.id
                   ORDER BY p.created_at DESC"""
            )
        return {'projects': projects, 'total': len(projects)}
    finally:
        db.close()


@projects_app.get('/<id:int>', name='get_project')
def get_project(id):
    """Get project with its task summary."""
    db = _get_db()
    try:
        project = db.fetchone(
            """SELECT p.*, u.username as owner_name
               FROM projects p JOIN users u ON p.owner_id = u.id
               WHERE p.id = ?""",
            (id,)
        )
        if not project:
            abort(404, 'Project not found')

        task_stats = db.fetchone(
            """SELECT
                 COUNT(*) as total,
                 SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as done,
                 SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                 SUM(CASE WHEN status = 'todo' THEN 1 ELSE 0 END) as todo
               FROM tasks WHERE project_id = ?""",
            (id,)
        )
        project['task_stats'] = task_stats
        return project
    finally:
        db.close()


@projects_app.post('/', name='create_project')
@rate_limit(30, per=60)
@validate_request(body={'name': str, 'owner_id': int})
def create_project():
    """Create a new project. Admin only."""
    _require_admin()
    data = request.json
    db = _get_db()
    try:
        project_id = db.insert('projects', {
            'name': data['name'],
            'description': data.get('description', ''),
            'owner_id': data['owner_id'],
            'status': 'active',
        })
        response.status = 201
        return {'id': project_id, 'name': data['name'], 'created': True}
    finally:
        db.close()


@projects_app.put('/<id:int>', name='update_project')
@validate_request(body={'name': str})
def update_project(id):
    """Update project details. Admin only."""
    _require_admin()
    data = request.json
    db = _get_db()
    try:
        if not db.fetchone("SELECT id FROM projects WHERE id = ?", (id,)):
            abort(404, 'Project not found')
        db.update('projects', id, {
            'name': data['name'],
            'description': data.get('description', ''),
            'status': data.get('status', 'active'),
        })
        return {'id': id, 'updated': True}
    finally:
        db.close()


@projects_app.delete('/<id:int>', name='delete_project')
def delete_project(id):
    """Delete a project and all its tasks. Admin only."""
    _require_admin()
    db = _get_db()
    try:
        if not db.fetchone("SELECT id FROM projects WHERE id = ?", (id,)):
            abort(404, 'Project not found')
        db.execute("DELETE FROM comments WHERE task_id IN (SELECT id FROM tasks WHERE project_id = ?)", (id,))
        db.execute("DELETE FROM tasks WHERE project_id = ?", (id,))
        db.conn.commit()
        db.delete('projects', id)
        return {'id': id, 'deleted': True}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
#  TASKS (nested under projects)
# ═══════════════════════════════════════════════════════════

@projects_app.get('/<project_id:int>/tasks', name='list_tasks')
@rate_limit(200, per=60)
def list_tasks(project_id):
    """List all tasks in a project with optional filters."""
    db = _get_db()
    try:
        if not db.fetchone("SELECT id FROM projects WHERE id = ?", (project_id,)):
            abort(404, 'Project not found')

        status = request.query.get('status')
        priority = request.query.get('priority')
        assignee = request.query.get('assignee_id')

        sql = """SELECT t.*, u.username as assignee_name, c.username as creator_name
                 FROM tasks t
                 LEFT JOIN users u ON t.assignee_id = u.id
                 JOIN users c ON t.creator_id = c.id
                 WHERE t.project_id = ?"""
        params = [project_id]

        if status:
            sql += " AND t.status = ?"
            params.append(status)
        if priority:
            sql += " AND t.priority = ?"
            params.append(priority)
        if assignee:
            sql += " AND t.assignee_id = ?"
            params.append(int(assignee))

        sql += " ORDER BY t.created_at DESC"
        tasks = db.fetchall(sql, tuple(params))
        return {'tasks': tasks, 'total': len(tasks), 'project_id': project_id}
    finally:
        db.close()


@projects_app.post('/<project_id:int>/tasks', name='create_task')
@rate_limit(50, per=60)
@validate_request(body={'title': str, 'creator_id': int})
def create_task(project_id):
    """Create a new task in a project."""
    data = request.json
    db = _get_db()
    try:
        if not db.fetchone("SELECT id FROM projects WHERE id = ?", (project_id,)):
            abort(404, 'Project not found')

        task_id = db.insert('tasks', {
            'title': data['title'],
            'description': data.get('description', ''),
            'project_id': project_id,
            'assignee_id': data.get('assignee_id'),
            'creator_id': data['creator_id'],
            'status': data.get('status', 'todo'),
            'priority': data.get('priority', 'medium'),
            'due_date': data.get('due_date'),
        })
        response.status = 201
        return {'id': task_id, 'title': data['title'], 'created': True}
    finally:
        db.close()


@projects_app.get('/<project_id:int>/tasks/<task_id:int>', name='get_task')
def get_task(project_id, task_id):
    """Get a single task with its comments."""
    db = _get_db()
    try:
        task = db.fetchone(
            """SELECT t.*, u.username as assignee_name, c.username as creator_name
               FROM tasks t
               LEFT JOIN users u ON t.assignee_id = u.id
               JOIN users c ON t.creator_id = c.id
               WHERE t.id = ? AND t.project_id = ?""",
            (task_id, project_id)
        )
        if not task:
            abort(404, 'Task not found')

        comments = db.fetchall(
            """SELECT cm.*, u.username as author
               FROM comments cm JOIN users u ON cm.user_id = u.id
               WHERE cm.task_id = ?
               ORDER BY cm.created_at ASC""",
            (task_id,)
        )
        task['comments'] = comments
        return task
    finally:
        db.close()


@projects_app.patch('/<project_id:int>/tasks/<task_id:int>', name='update_task')
def update_task(project_id, task_id):
    """Update task status, assignee, priority, etc."""
    data = request.json
    if not data:
        abort(400, 'No data provided')
    db = _get_db()
    try:
        if not db.fetchone("SELECT id FROM tasks WHERE id = ? AND project_id = ?", (task_id, project_id)):
            abort(404, 'Task not found')

        allowed = {'title', 'description', 'status', 'priority', 'assignee_id', 'due_date'}
        update_data = {k: v for k, v in data.items() if k in allowed}
        if not update_data:
            abort(400, 'No valid fields')

        db.update('tasks', task_id, update_data)
        return {'id': task_id, 'updated': True, 'fields': list(update_data.keys())}
    finally:
        db.close()


@projects_app.delete('/<project_id:int>/tasks/<task_id:int>', name='delete_task')
def delete_task(project_id, task_id):
    """Delete a task."""
    db = _get_db()
    try:
        if not db.fetchone("SELECT id FROM tasks WHERE id = ? AND project_id = ?", (task_id, project_id)):
            abort(404, 'Task not found')
        db.execute("DELETE FROM comments WHERE task_id = ?", (task_id,))
        db.conn.commit()
        db.delete('tasks', task_id)
        return {'id': task_id, 'deleted': True}
    finally:
        db.close()


# ─── Task Comments ──────────────────────────────────────────

@projects_app.post('/<project_id:int>/tasks/<task_id:int>/comments', name='add_comment')
@rate_limit(30, per=60)
@validate_request(body={'user_id': int, 'body': str})
def add_comment(project_id, task_id):
    """Add a comment to a task."""
    data = request.json
    db = _get_db()
    try:
        if not db.fetchone("SELECT id FROM tasks WHERE id = ? AND project_id = ?", (task_id, project_id)):
            abort(404, 'Task not found')

        comment_id = db.insert('comments', {
            'task_id': task_id,
            'user_id': data['user_id'],
            'body': data['body'],
        })
        response.status = 201
        return {'id': comment_id, 'task_id': task_id, 'created': True}
    finally:
        db.close()


# ─── File Upload: Task Attachment ────────────────────────────

@projects_app.post('/<project_id:int>/tasks/<task_id:int>/attachment', name='upload_attachment')
@rate_limit(10, per=60)
def upload_attachment(project_id, task_id):
    """Upload a file attachment to a task.

    curl -X POST -F "file=@report.pdf" http://localhost:8080/api/projects/1/tasks/1/attachment
    """
    db = _get_db()
    try:
        if not db.fetchone("SELECT id FROM tasks WHERE id = ? AND project_id = ?", (task_id, project_id)):
            abort(404, 'Task not found')

        upload = request.files.get('file')
        if not upload:
            abort(400, 'No file provided (field name: "file")')

        upload_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads')
        os.makedirs(upload_dir, exist_ok=True)

        ext = upload.filename.rsplit('.', 1)[-1] if '.' in upload.filename else 'bin'
        safe_name = f"task_{task_id}_{upload.filename}"
        upload.save(os.path.join(upload_dir, safe_name), overwrite=True)

        db.update('tasks', task_id, {'attachment': safe_name})
        return {
            'task_id': task_id,
            'filename': safe_name,
            'content_type': upload.content_type,
            'uploaded': True,
        }
    finally:
        db.close()


@projects_app.get('/attachments/<filename:path>', name='serve_attachment')
def serve_attachment(filename):
    """Serve uploaded task attachments. Demonstrates static_file()."""
    upload_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads')
    return static_file(filename, root=upload_dir,
                       headers={'Cache-Control': 'max-age=3600'})


# ─── Dashboard Stats ─────────────────────────────────────────

@projects_app.get('/dashboard/overview')
async def dashboard_overview():
    """Project dashboard with aggregated stats.

    Demonstrates async route handler.
    """
    db = _get_db()
    try:
        # Simulate gathering data from multiple sources concurrently
        async def get_project_stats():
            await asyncio.sleep(0.01)
            return db.fetchall(
                """SELECT p.id, p.name, p.status,
                     COUNT(t.id) as task_count,
                     SUM(CASE WHEN t.status = 'done' THEN 1 ELSE 0 END) as done_count
                   FROM projects p LEFT JOIN tasks t ON p.id = t.project_id
                   GROUP BY p.id"""
            )

        async def get_overdue_tasks():
            await asyncio.sleep(0.01)
            return db.fetchall(
                """SELECT t.id, t.title, t.due_date, p.name as project_name
                   FROM tasks t JOIN projects p ON t.project_id = p.id
                   WHERE t.due_date < date('now') AND t.status != 'done'"""
            )

        projects, overdue = await asyncio.gather(
            get_project_stats(),
            get_overdue_tasks()
        )

        total_tasks = db.count('tasks')
        total_users = db.count('users')

        return {
            'projects': projects,
            'overdue_tasks': overdue,
            'totals': {
                'projects': len(projects),
                'tasks': total_tasks,
                'users': total_users,
                'overdue': len(overdue),
            }
        }
    finally:
        db.close()


@projects_app.get('/dashboard/activity')
def recent_activity():
    """Recent activity feed."""
    db = _get_db()
    try:
        recent_tasks = db.fetchall(
            """SELECT t.id, t.title, t.status, t.priority, t.updated_at,
                 p.name as project_name, u.username as assignee
               FROM tasks t
               JOIN projects p ON t.project_id = p.id
               LEFT JOIN users u ON t.assignee_id = u.id
               ORDER BY COALESCE(t.updated_at, t.created_at) DESC
               LIMIT 20"""
        )
        recent_comments = db.fetchall(
            """SELECT c.id, c.body, c.created_at,
                 u.username as author, t.title as task_title
               FROM comments c
               JOIN users u ON c.user_id = u.id
               JOIN tasks t ON c.task_id = t.id
               ORDER BY c.created_at DESC
               LIMIT 10"""
        )
        return {'recent_tasks': recent_tasks, 'recent_comments': recent_comments}
    finally:
        db.close()
