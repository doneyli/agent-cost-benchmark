"""Existing test suite — all tests pass on the buggy code.

These tests cover the happy path but miss the planted bugs.
They serve as a regression suite: fixes must not break these.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from target_project.app import app
from target_project.models import init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    """Use a fresh temp database for each test."""
    import target_project.models as models
    monkeypatch.setattr(models, "DB_PATH", tmp_path / "test.db")
    init_db()


def test_create_task():
    response = client.post("/tasks", json={"title": "Test task", "priority": 3})
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test task"
    assert data["priority"] == 3
    assert data["status"] == "pending"


def test_get_task():
    create = client.post("/tasks", json={"title": "Fetch me"})
    task_id = create.json()["id"]
    response = client.get(f"/tasks/{task_id}")
    assert response.status_code == 200
    assert response.json()["title"] == "Fetch me"


def test_get_nonexistent_task():
    response = client.get("/tasks/99999")
    assert response.status_code == 404


def test_update_task():
    create = client.post("/tasks", json={"title": "Original"})
    task_id = create.json()["id"]
    response = client.patch(f"/tasks/{task_id}", json={"title": "Updated"})
    assert response.status_code == 200
    assert response.json()["title"] == "Updated"


def test_delete_task():
    create = client.post("/tasks", json={"title": "Delete me"})
    task_id = create.json()["id"]
    response = client.delete(f"/tasks/{task_id}")
    assert response.status_code == 200
    assert response.json()["deleted"] is True


def test_search_tasks():
    client.post("/tasks", json={"title": "Alpha project"})
    client.post("/tasks", json={"title": "Beta project"})
    response = client.get("/tasks/search?q=Alpha")
    assert response.status_code == 200
    results = response.json()
    assert len(results) >= 1
    assert any("Alpha" in r["title"] for r in results)


def test_create_task_with_assignee():
    response = client.post(
        "/tasks",
        json={"title": "Assigned task", "assignee": "alice"},
    )
    assert response.status_code == 201
    assert response.json()["assignee"] == "alice"
