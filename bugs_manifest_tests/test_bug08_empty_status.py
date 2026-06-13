"""BUG-08: Empty string status filter causes 500 or wrong results."""


def test_empty_status_returns_all_tasks(client):
    """GET /tasks?status= (empty string) should return all tasks, not error."""
    client.post("/tasks", json={"title": "Task A", "status": "pending"})
    client.post("/tasks", json={"title": "Task B", "status": "pending"})

    # Empty status should behave like "no filter" — return all tasks
    response = client.get("/tasks?status=")
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) >= 2, (
        f"Empty status filter should return all tasks, got {len(tasks)}"
    )
