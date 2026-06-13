"""Pydantic models and SQLite helpers for the task manager."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

DB_PATH = Path(__file__).parent / "tasks.db"

# --- Pydantic models ---

class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    assignee: str | None = None
    due_date: str | None = None  # ISO format: YYYY-MM-DD
    priority: int = Field(default=3, ge=1, le=5)
    status: str = "pending"


class TaskResponse(BaseModel):
    id: int
    title: str
    description: str
    assignee: str | None
    due_date: str | None
    priority: int
    status: str
    priority_score: float
    created_at: str


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    assignee: str | None = None
    due_date: str | None = None
    priority: int | None = None
    status: str | None = None


# --- Database helpers ---

@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                assignee TEXT,
                due_date TEXT,
                priority INTEGER DEFAULT 3,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_counter (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                count INTEGER DEFAULT 0
            )
        """)
        conn.execute("INSERT OR IGNORE INTO task_counter (id, count) VALUES (1, 0)")
        conn.commit()
