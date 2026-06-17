"""BUG-06: Race condition in task counter."""

import inspect
import textwrap


def test_counter_uses_lock():
    """The task counter update in create_task must be protected by _counter_lock."""
    import target_project.app as app_module

    source = inspect.getsource(app_module.create_task)

    # The counter update (reading count and writing new count) must be inside
    # a `with _counter_lock:` block to prevent race conditions.
    assert "_counter_lock" in source and "with _counter_lock" in source, (
        "create_task does not use _counter_lock — the counter update has a race condition"
    )
