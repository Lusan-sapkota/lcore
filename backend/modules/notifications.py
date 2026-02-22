"""
Notifications module (mounted at /api/notifications/) demonstrating:
  - SMTP email sending (Python stdlib smtplib)
  - Async route handlers (asyncio.gather)
  - Rate limiting on sensitive endpoints
  - Request validation
"""
import os
import sys
import smtplib
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from lcore import Lcore, request, response, ctx, abort, rate_limit, validate_request
from models import Database

notifications_app = Lcore()


class EmailService:
    """Email service for TaskFlow.

    Always simulates emails (stores in DB without sending via SMTP).
    This is intentional for the public playground — no real emails are sent.
    To enable real SMTP, set APP_SMTP_REAL=true and configure SMTP env vars.
    """

    def __init__(self):
        self.host = os.environ.get('APP_SMTP_HOST', 'smtp.gmail.com')
        self.port = int(os.environ.get('APP_SMTP_PORT', '587'))
        self.user = os.environ.get('APP_SMTP_USER', '')
        self.password = os.environ.get('APP_SMTP_PASSWORD', '')
        self.from_addr = os.environ.get('APP_SMTP_FROM', 'noreply@taskflow.app')
        self.use_tls = os.environ.get('APP_SMTP_USE_TLS', 'true').lower() == 'true'
        self.real_smtp = os.environ.get('APP_SMTP_REAL', 'false').lower() == 'true'

    def send(self, to: str, subject: str, body: str, html: bool = False) -> dict:
        db = Database()
        try:
            # Only send real SMTP if explicitly enabled and configured
            if self.real_smtp and self.user and self.user != 'your-email@gmail.com':
                msg = MIMEMultipart('alternative')
                msg['From'] = self.from_addr
                msg['To'] = to
                msg['Subject'] = subject
                msg.attach(MIMEText(body, 'html' if html else 'plain'))

                server = smtplib.SMTP(self.host, self.port, timeout=10)
                if self.use_tls:
                    server.starttls()
                server.login(self.user, self.password)
                server.sendmail(self.from_addr, [to], msg.as_string())
                server.quit()

                db.insert('notifications', {
                    'type': 'email', 'recipient': to, 'subject': subject,
                    'body': body, 'status': 'sent',
                })
                return {'status': 'sent', 'to': to, 'subject': subject}

            # Simulate — store in DB without sending
            db.insert('notifications', {
                'type': 'email', 'recipient': to, 'subject': subject,
                'body': body, 'status': 'simulated',
            })
            return {
                'status': 'simulated', 'to': to, 'subject': subject,
                'note': 'Email simulated and stored. No real email was sent.',
            }

        except Exception as e:
            db.insert('notifications', {
                'type': 'email', 'recipient': to, 'subject': subject,
                'status': 'failed', 'error': str(e),
            })
            return {'status': 'failed', 'to': to, 'error': str(e)}
        finally:
            db.close()


@notifications_app.post('/email', name='send_email')
@rate_limit(10, per=60)
@validate_request(body={'to': str, 'subject': str, 'body': str})
def send_email():
    """Send an email notification via SMTP."""
    data = request.json
    svc = EmailService()
    return svc.send(data['to'], data['subject'], data['body'], data.get('html', False))


@notifications_app.post('/task-assigned/<task_id:int>', name='notify_assignment')
@rate_limit(20, per=60)
def notify_assignment(task_id):
    """Notify a user they've been assigned a task."""
    db = Database()
    try:
        task = db.fetchone(
            """SELECT t.*, u.email as assignee_email, u.username as assignee_name,
                 p.name as project_name
               FROM tasks t
               JOIN users u ON t.assignee_id = u.id
               JOIN projects p ON t.project_id = p.id
               WHERE t.id = ?""",
            (task_id,)
        )
        if not task:
            abort(404, 'Task not found or has no assignee')

        svc = EmailService()
        return svc.send(
            to=task['assignee_email'],
            subject=f"[TaskFlow] You've been assigned: {task['title']}",
            body=f"""
            <h2>New Task Assignment</h2>
            <p>Hi {task['assignee_name']},</p>
            <p>You've been assigned a new task in <strong>{task['project_name']}</strong>:</p>
            <ul>
              <li><strong>Task:</strong> {task['title']}</li>
              <li><strong>Priority:</strong> {task['priority']}</li>
              <li><strong>Due:</strong> {task.get('due_date', 'No deadline')}</li>
            </ul>
            <p>{task.get('description', '')}</p>
            """,
            html=True,
        )
    finally:
        db.close()


@notifications_app.post('/async-batch', name='async_batch_notify')
@rate_limit(5, per=60)
async def async_batch_notify():
    """Send batch notifications asynchronously.

    Demonstrates async def route handler with asyncio.gather.
    """
    data = request.json
    if not data or 'recipients' not in data:
        abort(400, 'Missing "recipients" array')

    subject = data.get('subject', 'TaskFlow Notification')
    body = data.get('body', 'You have a new notification.')

    async def send_one(email_addr):
        await asyncio.sleep(0.05)  # Simulate network I/O
        db = Database()
        try:
            db.insert('notifications', {
                'type': 'email', 'recipient': email_addr,
                'subject': subject, 'status': 'simulated_async',
            })
        finally:
            db.close()
        return {'to': email_addr, 'status': 'sent'}

    results = await asyncio.gather(*[send_one(r) for r in data['recipients']])
    return {'batch_size': len(data['recipients']), 'results': list(results)}


@notifications_app.get('/history', name='notification_history')
@rate_limit(100, per=60)
def notification_history():
    """Get notification log with optional filters."""
    db = Database()
    try:
        sql = "SELECT * FROM notifications WHERE 1=1"
        params = []

        ntype = request.query.get('type')
        if ntype:
            sql += " AND type = ?"
            params.append(ntype)

        status = request.query.get('status')
        if status:
            sql += " AND status = ?"
            params.append(status)

        limit = int(request.query.get('limit', '50'))
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        notifications = db.fetchall(sql, tuple(params))
        return {'notifications': notifications, 'total': len(notifications)}
    finally:
        db.close()
