"""BUG-02: Off-by-one in pagination."""


def test_page_one_returns_first_items(client):
    """Page 1 should return the first page_size items, not skip them."""
    for i in range(5):
        client.post("/tasks", json={"title": f"Task {i+1}"})

    response = client.get("/tasks?page=1&page_size=3")
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 3
    assert tasks[0]["title"] == "Task 1", f"First task should be 'Task 1', got '{tasks[0]['title']}'"
