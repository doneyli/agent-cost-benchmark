"""BUG-04: N+1 query in list-tasks-with-assignees."""

import unittest.mock


def test_no_n_plus_one_queries(client):
    """Listing tasks with assignees should not execute one query per task."""
    for i in range(10):
        client.post("/tasks", json={"title": f"Task {i}", "assignee": f"user{i % 3}"})

    # Count the number of SQL executions
    import target_project.models as models
    original_get_db = models.get_db

    call_count = 0
    original_conn_execute = None

    class CountingConnection:
        def __init__(self, conn):
            self.conn = conn
            self.row_factory = conn.row_factory

        def execute(self, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            return self.conn.execute(*args, **kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.conn.close()

    from contextlib import contextmanager

    @contextmanager
    def counting_get_db():
        with original_get_db() as conn:
            yield CountingConnection(conn)

    with unittest.mock.patch.object(models, "get_db", counting_get_db):
        call_count = 0
        response = client.get("/tasks-with-assignees")

    assert response.status_code == 200
    # With N+1: 1 (list all) + 10 (one per task) = 11 queries
    # Without: should be <= 3 queries (list + aggregation + maybe one more)
    assert call_count <= 3, f"N+1 detected: {call_count} queries for 10 tasks"
