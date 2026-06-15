"""Cross-model comparison and derived metrics."""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from benchmark.config import MODEL_LOOKUP


def generate_comparison(results_dir: Path) -> list[dict]:
    """Load all results and compute per-model aggregated metrics."""
    all_results: dict[str, dict[str, list]] = {}

    for f in results_dir.glob("*.json"):
        data = json.loads(f.read_text())
        model_id = data["model_id"]
        track = data.get("track", "pipeline")

        if model_id not in all_results:
            all_results[model_id] = {"pipeline": [], "goal": []}
        all_results[model_id][track].append(data)

    rankings = []
    for model_id, tracks in all_results.items():
        config = MODEL_LOOKUP.get(model_id)
        if not config:
            continue

        entry = {
            "model_id": model_id,
            "display_name": config.display_name,
            "provider": config.provider,
            "tier": config.tier,
            "input_price_per_m": config.input_price_per_m,
            "output_price_per_m": config.output_price_per_m,
        }

        # Pipeline metrics (median of runs)
        pipeline_runs = tracks.get("pipeline", [])
        if pipeline_runs:
            entry["pipeline_cost_median"] = statistics.median(
                r.get("total_cost_usd", 0) or 0 for r in pipeline_runs
            )
            entry["pipeline_time_median"] = statistics.median(
                r["wall_clock_seconds"] for r in pipeline_runs
            )
            entry["pipeline_bugs_median"] = statistics.median(
                r["bugs_fixed_correctly"] for r in pipeline_runs
            )
            entry["pipeline_quality_median"] = statistics.median(
                r["overall_quality"] for r in pipeline_runs
            )
            entry["pipeline_complete"] = any(r["pipeline_complete"] for r in pipeline_runs)
            entry["pipeline_tokens_median"] = statistics.median(
                r.get("total_tokens", 0) or 0 for r in pipeline_runs
            )
            entry["pipeline_input_tokens_median"] = statistics.median(
                r.get("total_input_tokens", 0) or 0 for r in pipeline_runs
            )
            entry["pipeline_output_tokens_median"] = statistics.median(
                r.get("total_output_tokens", 0) or 0 for r in pipeline_runs
            )

            bugs_median = entry["pipeline_bugs_median"]
            if bugs_median > 0:
                entry["cost_per_bug"] = entry["pipeline_cost_median"] / bugs_median
                entry["time_per_bug"] = entry["pipeline_time_median"] / bugs_median
            else:
                entry["cost_per_bug"] = None
                entry["time_per_bug"] = None

        # Goal metrics (median of runs)
        goal_runs = tracks.get("goal", [])
        if goal_runs:
            entry["goal_cost_median"] = statistics.median(
                r["total_cost_usd"] for r in goal_runs
            )
            entry["goal_turns_median"] = statistics.median(
                r["total_turns"] for r in goal_runs
            )
            entry["goal_bugs_median"] = statistics.median(
                r["bugs_fixed"] for r in goal_runs
            )
            entry["goal_met_rate"] = sum(1 for r in goal_runs if r["goal_met"]) / len(goal_runs)

            # Autonomy premium
            if entry.get("pipeline_cost_median") and entry["pipeline_cost_median"] > 0:
                entry["autonomy_premium"] = (
                    entry["goal_cost_median"] / entry["pipeline_cost_median"]
                )

        rankings.append(entry)

    # Sort by cost per bug (ascending), None values last
    rankings.sort(key=lambda r: r.get("cost_per_bug") or float("inf"))
    return rankings
