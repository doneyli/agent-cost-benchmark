"""Pipeline runner — orchestrates the 5-agent pipeline for one model."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from langfuse import observe

from benchmark.agents import (
    FixerAgent,
    ReviewerAgent,
    ScoutAgent,
    TesterAgent,
    TriageAgent,
)
from benchmark.agents.base import get_langfuse
from benchmark.config import MODEL_LOOKUP
from benchmark.evals.programmatic import eval_fixer, eval_scout


@observe(name="benchmark_pipeline")
def run_pipeline(model_id: str, source_code: dict[str, str], run_number: int) -> dict:
    """Run the full 5-agent pipeline for one model. Returns raw result dict."""
    config = MODEL_LOOKUP[model_id]
    lf = get_langfuse()

    lf.update_current_trace(
        session_id=f"benchmark_pipeline_{model_id}",
        tags=[config.provider, model_id, "benchmark", "pipeline"],
        metadata={
            "model_id": model_id,
            "provider": config.provider,
            "tier": config.tier,
            "run_number": run_number,
            "track": "pipeline",
            "benchmark_version": "v1",
        },
    )

    start = time.monotonic()

    # --- Agent 1: Scout ---
    scout = ScoutAgent(model_id)
    findings = scout.run(source_code)

    scout_eval = eval_scout(findings)
    lf.score(name="bugs_detected", value=scout_eval["bugs_detected"], data_type="NUMERIC")
    lf.score(name="detection_recall", value=scout_eval["detection_recall"], data_type="NUMERIC")
    lf.score(name="scout_gate", value=scout_eval["gate_pass"], data_type="BOOLEAN")

    # --- Agent 2: Triage ---
    triage = TriageAgent(model_id)
    plan = triage.run(findings)

    # --- Agent 3: Fixer ---
    fixer = FixerAgent(model_id)
    fixes = fixer.run(plan, source_code)

    fixer_eval = eval_fixer(fixes)
    lf.score(
        name="bugs_fixed_correctly",
        value=fixer_eval["bugs_fixed_correctly"],
        data_type="NUMERIC",
    )
    lf.score(name="fix_rate", value=fixer_eval["fix_rate"], data_type="NUMERIC")
    lf.score(
        name="existing_tests_pass",
        value=fixer_eval["existing_tests_still_pass"],
        data_type="BOOLEAN",
    )
    lf.score(name="fixer_gate", value=fixer_eval["gate_pass"], data_type="BOOLEAN")

    # --- Agent 4: Tester ---
    tester = TesterAgent(model_id)
    test_code = tester.run(fixes)

    # --- Agent 5: Reviewer ---
    reviewer = ReviewerAgent(model_id)
    review = reviewer.run(source_code, fixes, test_code)

    elapsed = time.monotonic() - start

    # --- Composite score ---
    quality = _compute_quality(scout_eval, fixer_eval, review.overall_quality)
    pipeline_complete = (
        fixer_eval["bugs_fixed_correctly"] >= 1 and fixer_eval["existing_tests_still_pass"]
    )

    lf.score(name="overall_quality", value=quality, data_type="NUMERIC")
    lf.score(name="pipeline_complete", value=pipeline_complete, data_type="BOOLEAN")

    return {
        "run_id": f"{model_id}_{run_number}_{int(time.time())}",
        "model_id": model_id,
        "provider": config.provider,
        "run_number": run_number,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "wall_clock_seconds": round(elapsed, 2),
        # Quality
        "bugs_detected": scout_eval["bugs_detected"],
        "bugs_fixed_correctly": fixer_eval["bugs_fixed_correctly"],
        "existing_tests_pass": fixer_eval["existing_tests_still_pass"],
        "overall_quality": quality,
        "pipeline_complete": pipeline_complete,
        "review_quality": review.overall_quality,
        # Raw outputs (for analysis)
        "scout_output": findings.model_dump(),
        "triage_output": plan.model_dump(),
        "fixer_output": fixes.model_dump(),
        "test_code": test_code,
        "review_output": review.model_dump(),
        # Gate results
        "scout_eval": scout_eval,
        "fixer_eval": fixer_eval,
    }


def _compute_quality(scout_eval: dict, fixer_eval: dict, review_score: int) -> float:
    """Weighted composite quality score (0.0 - 1.0)."""
    weights = {
        "detection_recall": 0.20,
        "fix_rate": 0.30,
        "no_regressions": 0.20,
        "review_quality": 0.15,
        "scout_precision": 0.15,
    }
    total_findings = scout_eval["bugs_detected"] + scout_eval["false_positives"]
    precision = scout_eval["bugs_detected"] / max(total_findings, 1)

    scores = {
        "detection_recall": scout_eval["detection_recall"],
        "fix_rate": fixer_eval["fix_rate"],
        "no_regressions": 1.0 if fixer_eval["existing_tests_still_pass"] else 0.0,
        "review_quality": review_score / 5.0,
        "scout_precision": precision,
    }
    return round(sum(scores[k] * weights[k] for k in weights), 3)
