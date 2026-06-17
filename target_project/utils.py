"""Utility functions for the task manager."""

from __future__ import annotations

from datetime import datetime


def parse_date(date_str: str) -> datetime:
    """Parse a date string in various formats."""
    formats = ["%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    # BUG-05: No handling if none of the formats match — raises unhandled ValueError
    raise ValueError(f"Unable to parse date: {date_str}")


def calculate_priority_score(priority: int, has_assignee: bool, days_until_due: int | None) -> float:
    """Calculate a composite priority score for sorting.

    Higher score = more urgent.
    """
    base = priority * 10

    if has_assignee:
        base += 5

    if days_until_due is not None:
        if days_until_due < 0:
            # Overdue
            urgency = 50
        elif days_until_due <= 3:
            urgency = 30
        elif days_until_due <= 7:
            urgency = 15
        else:
            urgency = 0
        # BUG-07: Wrong weight — should be 0.05 but is 0.5
        # This inflates the urgency component by 10x
        base += urgency * 0.5

    return base


def paginate(items: list, page: int, page_size: int) -> list:
    """Return a page of items.

    Pages are 1-indexed.
    """
    # BUG-02: Off-by-one — should be (page - 1) * page_size
    # page=1 should start at index 0, but this starts at page_size
    start = page * page_size
    end = start + page_size
    return items[start:end]


def sanitize_status(status: str | None) -> str | None:
    """Validate and normalize a task status string."""
    if status is None:
        return None
    valid = {"pending", "in_progress", "done", "cancelled"}
    # BUG-08: Empty string falls through — not in valid set,
    # returns "" which causes issues downstream
    normalized = status.strip().lower()
    if normalized in valid:
        return normalized
    return status  # Returns the invalid status instead of raising or returning None
