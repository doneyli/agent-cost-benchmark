"""Pipeline runner — orchestrates the 5-agent pipeline for one model."""

from __future__ import annotations

import json
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
from benchmark.agents.base import UsageAccumulator, get_langfuse
from benchmark.config import MODEL_LOOKUP
from benchmark.evals.llm_judge import judge
from benchmark.evals.programmatic import eval_fixer, eval_scout


@observe(name="benchmark_pipeline")
def run_pipeline(model_id: str, source_code: dict[str, str], run_number: int) -> dict:
    """Run the full 5-agent pipeline for one model. Returns raw result dict."""
    config = MODEL_LOOKUP[model_id]
    lf = get_langfuse()
    usage = UsageAccumulator()

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
    agent_metrics = []

    # --- Agent 1: Scout ---
    scout_start = time.monotonic()
    scout = ScoutAgent(model_id, usage=usage)
    findings = scout.run(source_code)
    scout_elapsed = time.monotonic() - scout_start

    scout_eval = eval_scout(findings)
    lf.score(name="bugs_detected", value=scout_eval["bugs_detected"], data_type="NUMERIC")
    lf.score(name="detection_recall", value=scout_eval["detection_recall"], data_type="NUMERIC")
    lf.score(name="scout_gate", value=scout_eval["gate_pass"], data_type="BOOLEAN")

    scout_usage = scout.usage.to_dict()
    agent_metrics.append({"agent": "scout", "duration_seconds": round(scout_elapsed, 2), **scout_usage})

    # --- Agent 2: Triage ---
    triage_start = time.monotonic()
    triage = TriageAgent(model_id, usage=usage)
    plan = triage.run(findings)
    triage_elapsed = time.monotonic() - triage_start

    agent_metrics.append({"agent": "triage", "duration_seconds": round(triage_elapsed, 2), **triage.usage.to_dict()})

    # --- Agent 3: Fixer ---
    fixer_start = time.monotonic()
    fixer = FixerAgent(model_id, usage=usage)
    fixes = fixer.run(plan, source_code)
    fixer_elapsed = time.monotonic() - fixer_start

    fixer_eval = eval_fixer(fixes)
    lf.score(name="bugs_fixed_correctly", value=fixer_eval["bugs_fixed_correctly"], data_type="NUMERIC")
    lf.score(name="fix_rate", value=fixer_eval["fix_rate"], data_type="NUMERIC")
    lf.score(name="existing_tests_pass", value=fixer_eval["existing_tests_still_pass"], data_type="BOOLEAN")
    lf.score(name="fixer_gate", value=fixer_eval["gate_pass"], data_type="BOOLEAN")

    agent_metrics.append({"agent": "fixer", "duration_seconds": round(fixer_elapsed, 2), **fixer.usage.to_dict()})

    # --- Agent 4: Tester ---
    tester_start = time.monotonic()
    tester = TesterAgent(model_id, usage=usage)
    test_code = tester.run(fixes)
    tester_elapsed = time.monotonic() - tester_start

    tester_eval = _eval_tester(test_code, fixes)
    lf.score(name="tests_generated", value=tester_eval["tests_generated"], data_type="NUMERIC")
    lf.score(name="tests_syntax_valid", value=tester_eval["syntax_valid"], data_type="BOOLEAN")

    agent_metrics.append({"agent": "tester", "duration_seconds": round(tester_elapsed, 2), **tester.usage.to_dict()})

    # --- Agent 5: Reviewer ---
    reviewer_start = time.monotonic()
    reviewer = ReviewerAgent(model_id, usage=usage)
    review = reviewer.run(source_code, fixes, test_code)
    reviewer_elapsed = time.monotonic() - reviewer_start

    agent_metrics.append({"agent": "reviewer", "duration_seconds": round(reviewer_elapsed, 2), **reviewer.usage.to_dict()})

    elapsed = time.monotonic() - start

    # --- LLM-as-judge evaluations ---
    judge_scores = _run_llm_judges(source_code, findings, plan, fixes, test_code, review)
    for name, result in judge_scores.items():
        lf.score(name=name, value=result["score"], data_type="NUMERIC")

    # --- Composite score ---
    quality = _compute_quality(scout_eval, fixer_eval, review.overall_quality)
    pipeline_complete = (
        fixer_eval["bugs_fixed_correctly"] >= 1 and fixer_eval["existing_tests_still_pass"]
    )

    lf.score(name="overall_quality", value=quality, data_type="NUMERIC")
    lf.score(name="pipeline_complete", value=pipeline_complete, data_type="BOOLEAN")

    # --- Cost from accumulator ---
    total_cost = usage.compute_cost(config)

    return {
        "run_id": f"{model_id}_{run_number}_{int(time.time())}",
        "model_id": model_id,
        "provider": config.provider,
        "track": "pipeline",
        "run_number": run_number,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "wall_clock_seconds": round(elapsed, 2),
        # Cost & tokens
        "total_cost_usd": round(total_cost, 6),
        "total_tokens": usage.total_tokens,
        "total_input_tokens": usage.total_input_tokens,
        "total_output_tokens": usage.total_output_tokens,
        "cache_read_tokens": usage.total_cache_read_tokens,
        "cache_creation_tokens": usage.total_cache_creation_tokens,
        # Quality
        "bugs_detected": scout_eval["bugs_detected"],
        "bugs_fixed_correctly": fixer_eval["bugs_fixed_correctly"],
        "existing_tests_pass": fixer_eval["existing_tests_still_pass"],
        "overall_quality": quality,
        "pipeline_complete": pipeline_complete,
        "review_quality": review.overall_quality,
        "tests_generated": tester_eval["tests_generated"],
        "tests_syntax_valid": tester_eval["syntax_valid"],
        # LLM judge scores
        "judge_scores": {k: v["score"] for k, v in judge_scores.items()},
        # Per-agent breakdown
        "agent_metrics": agent_metrics,
        # Raw outputs (for analysis)
        "scout_output": findings.model_dump(),
        "triage_output": plan.model_dump(),
        "fixer_output": fixes.model_dump(),
        "test_code": test_code,
        "review_output": review.model_dump(),
        # Gate results
        "scout_eval": scout_eval,
        "fixer_eval": fixer_eval,
        "tester_eval": tester_eval,
    }


def _eval_tester(test_code: str, fixes) -> dict:
    """Evaluate the generated test code: count tests, check syntax."""
    import re

    test_count = len(re.findall(r"def test_\w+", test_code))

    syntax_valid = True
    try:
        compile(test_code, "<generated_tests>", "exec")
    except SyntaxError:
        syntax_valid = False

    return {
        "tests_generated": test_count,
        "syntax_valid": syntax_valid,
    }


def _run_llm_judges(source_code, findings, plan, fixes, test_code, review) -> dict:
    """Run all 4 LLM-as-judge evaluations. Returns {name: {score, rationale}}."""
    results = {}

    original_block = "\n".join(f"### {p}\n{c}" for p, c in source_code.items())
    fixed_block = "\n".join(f"### {f.path}\n{f.content}" for f in fixes.fixed_files)
    bugs_list = ", ".join(fixes.bugs_addressed)
    findings_text = "\n".join(
        f"- [{f.severity}] {f.file}:{f.line} — {f.description}" for f in findings.findings
    )
    plan_text = "\n".join(
        f"{i.priority}. {i.bug_description} — {i.rationale}" for i in plan.plan
    )

    try:
        results["fix_quality"] = judge("fix_quality", {
            "original_code": original_block[:3000],
            "fixed_code": fixed_block[:3000],
            "bugs_addressed": bugs_list,
        })
    except Exception:
        results["fix_quality"] = {"score": 0, "rationale": "Judge failed"}

    try:
        results["triage_quality"] = judge("triage_quality", {
            "findings": findings_text[:2000],
            "plan": plan_text[:2000],
        })
    except Exception:
        results["triage_quality"] = {"score": 0, "rationale": "Judge failed"}

    try:
        results["test_coverage"] = judge("test_coverage", {
            "bugs_fixed": bugs_list,
            "test_code": test_code[:3000],
        })
    except Exception:
        results["test_coverage"] = {"score": 0, "rationale": "Judge failed"}

    try:
        results["review_thoroughness"] = judge("review_thoroughness", {
            "review": json.dumps(review.model_dump(), indent=2)[:3000],
            "bugs_fixed": bugs_list,
        })
    except Exception:
        results["review_thoroughness"] = {"score": 0, "rationale": "Judge failed"}

    return results


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
