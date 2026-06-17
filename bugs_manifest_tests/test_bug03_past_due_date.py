"""BUG-03: Missing validation for past due dates."""


def test_reject_past_due_date(client):
    """Creating a task with a due_date in the past should be rejected."""
    response = client.post("/tasks", json={
        "title": "Past due task",
        "due_date": "2020-01-01",
    })
    assert response.status_code in (400, 422), (
        f"Past due_date should be rejected, got {response.status_code}"
    )
