"""BUG-05: Unhandled ValueError in date parser."""

from fastapi.testclient import TestClient
from target_project.app import app


def test_invalid_date_returns_400_not_500(client):
    """An invalid date should return 400, not crash with 500."""
    # Use raise_server_exceptions=False so unhandled errors return 500
    # instead of raising in the test process
    safe_client = TestClient(app, raise_server_exceptions=False)
    response = safe_client.post("/tasks", json={
        "title": "Bad date task",
        "due_date": "not-a-date",
    })
    assert response.status_code == 400 or response.status_code == 422, (
        f"Invalid date should return 4xx, got {response.status_code}"
    )
