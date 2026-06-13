"""BUG-07: Priority score uses wrong weight."""

from target_project.utils import calculate_priority_score


def test_urgency_weight_is_not_inflated():
    """Urgency component should use weight 0.05, not 0.5."""
    # Task with priority 3, assigned, due in 2 days (urgency = 30)
    score = calculate_priority_score(priority=3, has_assignee=True, days_until_due=2)

    # Correct: 3*10 + 5 + 30*0.05 = 36.5
    # Buggy:   3*10 + 5 + 30*0.5  = 50.0
    assert score < 40, (
        f"Priority score {score} is too high — urgency weight appears to be 0.5 instead of 0.05"
    )
    assert abs(score - 36.5) < 0.01, f"Expected ~36.5, got {score}"
