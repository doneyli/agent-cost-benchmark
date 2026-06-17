"""FastAPI task manager — contains intentional bugs for benchmarking."""

from __future__ import annotations

import threading
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query

from target_project.models import (
    TaskCreate,
    TaskResponse,
    TaskUpdate,
    get_db,
    init_db,
)
from target_project.utils import calculate_priority_score, paginate, parse_date, sanitize_status

app = FastAPI(title="Task Manager")
_counter_lock = threading.Lock()  # Exists but BUG-06: not used where it should be


@app.on_event("startup")
def startup():
    init_db()


@app.post("/tasks", response_model=TaskResponse, status_code=201)
def create_task(task: TaskCreate):
    # BUG-03: No validation that due_date is in the future
    if task.due_date:
        parse_date(task.due_date)  # validates format only

    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO tasks (title, description, assignee, due_date, priority, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (task.title, task.description, task.assignee, task.due_date, task.priority, task.status),
        )
        conn.commit()
        task_id = cursor.lastrowid

        # BUG-06: Race condition — reads and writes counter without lock
        # _counter_lock exists but is not used here
        row = conn.execute("SELECT count FROM task_counter WHERE id = 1").fetchone()
        new_count = row["count"] + 1
        conn.execute("UPDATE task_counter SET count = ? WHERE id = 1", (new_count,))
        conn.commit()

        return _build_response(conn, task_id)


@app.get("/tasks", response_model=list[TaskResponse])
def list_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    status: str | None = Query(default=None),
):
    with get_db() as conn:
        # BUG-08: sanitize_status returns "" for empty string, which doesn't match any rows
        # but doesn't raise — just returns empty results confusingly
        clean_status = sanitize_status(status)

        if clean_status:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY id", (clean_status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()

        tasks = [_row_to_response(r) for r in rows]
        # BUG-02: paginate has off-by-one, page 1 skips the first page_size items
        return paginate(tasks, page, page_size)


@app.get("/tasks/search")
def search_tasks(q: str = Query(min_length=1)):
    with get_db() as conn:
        # BUG-01: SQL injection — f-string interpolation instead of parameterized query
        query = f"SELECT * FROM tasks WHERE title LIKE '%{q}%' OR description LIKE '%{q}%'"
        rows = conn.execute(query).fetchall()
        return [_row_to_response(r) for r in rows]


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        return _row_to_response(row)


@app.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, update: TaskUpdate):
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Task not found")

        updates = {}
        if update.title is not None:
            updates["title"] = update.title
        if update.description is not None:
            updates["description"] = update.description
        if update.assignee is not None:
            updates["assignee"] = update.assignee
        if update.due_date is not None:
            parse_date(update.due_date)
            updates["due_date"] = update.due_date
        if update.priority is not None:
            updates["priority"] = update.priority
        if update.status is not None:
            updates["status"] = update.status

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [task_id]
            conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
            conn.commit()

        return _build_response(conn, task_id)


@app.get("/tasks-with-assignees")
def list_tasks_with_assignees():
    """List all tasks with their assignee details."""
    with get_db() as conn:
        tasks = conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()
        result = []
        for task in tasks:
            # BUG-04: N+1 query — executes a separate query per task
            # Should use a JOIN or batch query instead
            assignee_info = None
            if task["assignee"]:
                assignee_row = conn.execute(
                    "SELECT * FROM tasks WHERE assignee = ? LIMIT 1",
                    (task["assignee"],),
                ).fetchone()
                if assignee_row:
                    assignee_info = {"name": task["assignee"], "task_count": 1}
            result.append({**_row_to_response(task), "assignee_info": assignee_info})
        return result


@app.delete("/tasks/{task_id}")
def delete_task(task_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        return {"deleted": True, "id": task_id}


# --- Helpers ---

def _build_response(conn, task_id: int) -> dict:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _row_to_response(row)


def _row_to_response(row) -> dict:
    days_until_due = None
    if row["due_date"]:
        try:
            due = parse_date(row["due_date"])
            days_until_due = (due - datetime.now()).days
        except ValueError:
            pass

    score = calculate_priority_score(
        priority=row["priority"],
        has_assignee=row["assignee"] is not None,
        days_until_due=days_until_due,
    )

    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "assignee": row["assignee"],
        "due_date": row["due_date"],
        "priority": row["priority"],
        "status": row["status"],
        "priority_score": score,
        "created_at": row["created_at"],
    }
