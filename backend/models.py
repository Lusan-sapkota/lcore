"""
SQLite database layer for TaskFlow.
Demonstrates real-world database usage with Lcore's dependency injection.
"""
import sqlite3
import os
import sys
import time
from typing import Optional, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from lcore import hash_password, verify_password  # noqa: E402


DB_PATH = os.path.join(os.path.dirname(__file__), 'taskflow.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    avatar TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    owner_id INTEGER NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'active',
    created_at REAL NOT NULL,
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    project_id INTEGER NOT NULL REFERENCES projects(id),
    assignee_id INTEGER REFERENCES users(id),
    creator_id INTEGER NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'todo',
    priority TEXT NOT NULL DEFAULT 'medium',
    due_date TEXT,
    attachment TEXT,
    created_at REAL NOT NULL,
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    body TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    type TEXT NOT NULL,
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    created_at REAL NOT NULL
);
"""


class Database:
    """SQLite wrapper used as a scoped dependency (one per request)."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def fetchone(self, sql: str, params: tuple = ()) -> Optional[dict]:
        row = self.conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def fetchall(self, sql: str, params: tuple = ()) -> List[dict]:
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def insert(self, table: str, data: dict) -> int:
        data['created_at'] = time.time()
        cols = ', '.join(data.keys())
        placeholders = ', '.join('?' for _ in data)
        cur = self.conn.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
            tuple(data.values())
        )
        self.conn.commit()
        return cur.lastrowid

    def update(self, table: str, row_id: int, data: dict) -> bool:
        data['updated_at'] = time.time()
        sets = ', '.join(f"{k} = ?" for k in data)
        self.conn.execute(
            f"UPDATE {table} SET {sets} WHERE id = ?",
            (*data.values(), row_id)
        )
        self.conn.commit()
        return True

    def delete(self, table: str, row_id: int) -> bool:
        cur = self.conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def count(self, table: str) -> int:
        row = self.conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
        return row['cnt']

    def close(self):
        self.conn.close()


def init_db(db_path: str = None):
    """Initialize the database schema and seed demo data."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)

    # Seed data if users table is empty
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count == 0:
        now = time.time()

        # Admin user (password: admin123)
        conn.execute(
            "INSERT INTO users (username, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
            ('admin', 'admin@taskflow.app', hash_password('admin123'), 'admin', now)
        )
        # Regular users
        conn.execute(
            "INSERT INTO users (username, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
            ('alice', 'alice@example.com', hash_password('alice123'), 'member', now)
        )
        conn.execute(
            "INSERT INTO users (username, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
            ('bob', 'bob@example.com', hash_password('bob123'), 'member', now)
        )

        # Demo project
        conn.execute(
            "INSERT INTO projects (name, description, owner_id, status, created_at) VALUES (?, ?, ?, ?, ?)",
            ('Website Redesign', 'Redesign the company website with modern UI', 1, 'active', now)
        )
        conn.execute(
            "INSERT INTO projects (name, description, owner_id, status, created_at) VALUES (?, ?, ?, ?, ?)",
            ('Mobile App', 'Build the mobile companion app', 2, 'active', now)
        )

        # Demo tasks
        conn.execute(
            "INSERT INTO tasks (title, description, project_id, assignee_id, creator_id, status, priority, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ('Design homepage mockup', 'Create Figma mockups for the new homepage', 1, 2, 1, 'in_progress', 'high', now)
        )
        conn.execute(
            "INSERT INTO tasks (title, description, project_id, assignee_id, creator_id, status, priority, due_date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ('Set up CI/CD pipeline', 'Configure GitHub Actions for automated deployment', 1, 3, 1, 'todo', 'medium', '2026-03-15', now)
        )
        conn.execute(
            "INSERT INTO tasks (title, description, project_id, assignee_id, creator_id, status, priority, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ('User authentication flow', 'Implement login/signup screens', 2, 2, 2, 'todo', 'high', now)
        )

        # Demo comment
        conn.execute(
            "INSERT INTO comments (task_id, user_id, body, created_at) VALUES (?, ?, ?, ?)",
            (1, 1, 'Looking great! Lets use the dark theme as the default.', now)
        )

        conn.commit()
        print("[DB] Seeded demo data (3 users, 2 projects, 3 tasks)")

    conn.close()
