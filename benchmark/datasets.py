"""Langfuse Datasets & Experiments integration.

The benchmark task is stored as a Langfuse Dataset item. Each model run
creates an Experiment via dataset.run_experiment(), giving us side-by-side
comparison in the Langfuse UI (scores, cost, latency across all 6 models).
"""

from __future__ import annotations

import json
from pathlib import Path

from langfuse import Evaluation

from benchmark.agents.base import get_langfuse
from benchmark.config import MODEL_LOOKUP
from benchmark.evals.programmatic import eval_fixer, eval_scout, load_manifest

DATASET_NAME = "cost-per-task-benchmark"
TARGET_DIR = Path(__file__).parent.parent / "target_project"
MANIFEST_PATH = Path(__file__).parent.parent / "bugs_manifest.json"


# ---------------------------------------------------------------------------
# Dataset setup (run once)
# ---------------------------------------------------------------------------

def ensure_dataset() -> None:
    """Create the Langfuse dataset and item if they don't exist yet."""
    lf = get_langfuse()

    try:
        lf.get_dataset(DATASET_NAME)
        return
    except Exception:
        pass

    lf.create_dataset(
        name=DATASET_NAME,
        description=(
            "Bug Hunt benchmark: FastAPI task manager with 8 planted bugs. "
            "Models run a 5-agent pipeline (Scout → Triage → Fixer → Tester → Reviewer) "
            "to find, fix, test, and review the code."
        ),
        metadata={
            "benchmark_version": "v1",
            "bugs_total": 8,
            "tracks": ["pipeline", "goal"],
        },
    )

    source_code = _load_source_code()
    manifest = load_manifest()

    lf.create_dataset_item(
        dataset_name=DATASET_NAME,
        input={
            "source_code": source_code,
            "task_description": (
                "Analyze the target_project/ codebase. Find all bugs, prioritize them, "
                "fix them, write tests for the fixes, and review the changes."
            ),
        },
        expected_output={
            "bugs_total": 8,
            "bug_ids": [b["bug_id"] for b in manifest],
            "manifest": manifest,
        },
        metadata={"task": "bug-hunt", "version": "v1"},
    )

    lf.flush()


# ---------------------------------------------------------------------------
# Experiment evaluators (run after each item)
# ---------------------------------------------------------------------------

def eval_pipeline_quality(*, output, expected_output, **kwargs) -> Evaluation:
    """Programmatic evaluation: how many bugs were found and fixed?"""
    if output is None:
        return Evaluation(name="pipeline_quality", value=0.0, comment="Run failed")

    scout_result = eval_scout(output["scout_output_parsed"])
    fixer_result = eval_fixer(output["fixer_output_parsed"])

    quality = _composite_score(scout_result, fixer_result, output.get("review_quality", 3))
    pipeline_complete = (
        fixer_result["bugs_fixed_correctly"] >= 1
        and fixer_result["existing_tests_still_pass"]
    )

    return Evaluation(
        name="pipeline_quality",
        value=quality,
        comment=(
            f"Found {scout_result['bugs_detected']}/8, "
            f"fixed {fixer_result['bugs_fixed_correctly']}/8, "
            f"complete={pipeline_complete}"
        ),
    )


def eval_bugs_fixed(*, output, expected_output, **kwargs) -> Evaluation:
    """Count of correctly fixed bugs (programmatic, 0-8)."""
    if output is None:
        return Evaluation(name="bugs_fixed", value=0)

    fixer_result = eval_fixer(output["fixer_output_parsed"])
    return Evaluation(
        name="bugs_fixed",
        value=fixer_result["bugs_fixed_correctly"],
        comment=f"{fixer_result['bugs_fixed_correctly']}/8 bugs fixed correctly",
    )


def eval_bugs_detected(*, output, expected_output, **kwargs) -> Evaluation:
    """Count of bugs detected by scout (programmatic, 0-8)."""
    if output is None:
        return Evaluation(name="bugs_detected", value=0)

    scout_result = eval_scout(output["scout_output_parsed"])
    return Evaluation(
        name="bugs_detected",
        value=scout_result["bugs_detected"],
        comment=(
            f"Detected {scout_result['bugs_detected']}/8. "
            f"Missed: {', '.join(scout_result['missed_ids']) or 'none'}"
        ),
    )


def eval_no_regressions(*, output, expected_output, **kwargs) -> Evaluation:
    """Did the fixes break existing tests? (boolean)."""
    if output is None:
        return Evaluation(name="no_regressions", value=0)

    fixer_result = eval_fixer(output["fixer_output_parsed"])
    passed = fixer_result["existing_tests_still_pass"]
    return Evaluation(
        name="no_regressions",
        value=1 if passed else 0,
        comment="Existing tests pass" if passed else f"{fixer_result['regressions']} regressions",
    )


ALL_EVALUATORS = [
    eval_pipeline_quality,
    eval_bugs_fixed,
    eval_bugs_detected,
    eval_no_regressions,
]


# ---------------------------------------------------------------------------
# Experiment runner
# ---------------------------------------------------------------------------

def run_experiment(model_id: str, run_number: int) -> dict:
    """Run the benchmark as a Langfuse Experiment.

    Uses dataset.run_experiment() for side-by-side comparison in the Langfuse UI.
    """
    from benchmark.agents import (
        FixerAgent,
        ReviewerAgent,
        ScoutAgent,
        TesterAgent,
        TriageAgent,
    )

    lf = get_langfuse()
    config = MODEL_LOOKUP[model_id]
    dataset = lf.get_dataset(DATASET_NAME)

    def run_pipeline_task(*, item, **kwargs):
        """Task function for dataset.run_experiment().

        Receives the dataset item, runs the full pipeline, returns output
        that evaluators can score.
        """
        import time

        source_code = item.input["source_code"]
        start = time.monotonic()

        lf.update_current_trace(
            session_id=f"experiment_{model_id}",
            tags=[config.provider, model_id, "experiment", "pipeline"],
            metadata={
                "model_id": model_id,
                "provider": config.provider,
                "tier": config.tier,
                "run_number": run_number,
                "track": "pipeline",
            },
        )

        scout = ScoutAgent(model_id)
        findings = scout.run(source_code)

        triage = TriageAgent(model_id)
        plan = triage.run(findings)

        fixer = FixerAgent(model_id)
        fixes = fixer.run(plan, source_code)

        tester = TesterAgent(model_id)
        test_code = tester.run(fixes)

        reviewer = ReviewerAgent(model_id)
        review = reviewer.run(source_code, fixes, test_code)

        elapsed = time.monotonic() - start

        return {
            "model_id": model_id,
            "wall_clock_seconds": round(elapsed, 2),
            "review_quality": review.overall_quality,
            # Parsed objects for evaluators (they call eval_scout/eval_fixer)
            "scout_output_parsed": findings,
            "fixer_output_parsed": fixes,
            # Serializable copies for JSON export
            "scout_output": findings.model_dump(),
            "triage_output": plan.model_dump(),
            "fixer_output": fixes.model_dump(),
            "test_code": test_code,
            "review_output": review.model_dump(),
        }

    experiment_name = f"pipeline-{config.display_name.lower().replace(' ', '-')}-run{run_number}"

    result = dataset.run_experiment(
        name=experiment_name,
        task=run_pipeline_task,
        evaluators=ALL_EVALUATORS,
        metadata={
            "model_id": model_id,
            "provider": config.provider,
            "tier": config.tier,
            "run_number": run_number,
            "input_price_per_m": config.input_price_per_m,
            "output_price_per_m": config.output_price_per_m,
        },
    )

    return {
        "experiment_name": experiment_name,
        "model_id": model_id,
        "run_number": run_number,
        "result_summary": str(result),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_source_code() -> dict[str, str]:
    source = {}
    for f in sorted(TARGET_DIR.glob("*.py")):
        source[f"target_project/{f.name}"] = f.read_text()
    return source


def _composite_score(scout_eval: dict, fixer_eval: dict, review_score: int) -> float:
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
