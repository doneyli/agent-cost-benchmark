"""BUG-06: Race condition in task counter."""

import concurrent.futures


def test_counter_consistency_under_concurrency(client):
    """Creating tasks concurrently should maintain accurate counter."""
    num_tasks = 20

    def create_task(i):
        return client.post("/tasks", json={"title": f"Concurrent task {i}"})

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(create_task, i) for i in range(num_tasks)]
        results = [f.result() for f in futures]

    assert all(r.status_code == 201 for r in results)

    # Verify counter matches actual task count
    import target_project.models as models
    with models.get_db() as conn:
        counter = conn.execute("SELECT count FROM task_counter WHERE id = 1").fetchone()
        actual = conn.execute("SELECT COUNT(*) as cnt FROM tasks").fetchone()

    assert counter["count"] == actual["cnt"], (
        f"Counter ({counter['count']}) doesn't match actual task count ({actual['cnt']})"
    )
