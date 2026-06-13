"""BUG-01: SQL injection in search endpoint."""


def test_sql_injection_in_search(client):
    """Search with SQL injection payload must not execute arbitrary SQL."""
    client.post("/tasks", json={"title": "Normal task"})
    # This payload would drop the table if the query is vulnerable
    response = client.get("/tasks/search?q=' OR 1=1 --")
    # A safe query returns 0 results (no title matches the literal string)
    # A vulnerable query returns ALL rows
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 0, "SQL injection returned results — query is vulnerable"
