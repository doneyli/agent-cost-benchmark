"""Export benchmark results as newsletter-ready markdown."""

from __future__ import annotations

from pathlib import Path

from benchmark.analysis.compare import generate_comparison


def export_newsletter(results_dir: Path, output_path: Path) -> None:
    """Generate a markdown comparison table for the newsletter."""
    rankings = generate_comparison(results_dir)

    lines = [
        "## Cost per Token vs Cost per Task Completion",
        "",
        "### Ranked by Cost per 1M Output Tokens (how vendors sell it)",
        "",
        "| # | Model | $/1M Output | Tier |",
        "|---|-------|-------------|------|",
    ]
    by_price = sorted(rankings, key=lambda r: r["output_price_per_m"])
    for i, r in enumerate(by_price, 1):
        lines.append(f"| {i} | {r['display_name']} | ${r['output_price_per_m']:.2f} | {r['tier']} |")

    lines += [
        "",
        "### Ranked by Cost per Bug Correctly Fixed (what actually matters)",
        "",
        "| # | Model | Total $ | Time (s) | Bugs Fixed | Quality | $/Bug | Complete? |",
        "|---|-------|---------|----------|------------|---------|-------|-----------|",
    ]
    for i, r in enumerate(rankings, 1):
        cost = f"${r.get('pipeline_cost_median', 0):.4f}"
        time_s = f"{r.get('pipeline_time_median', 0):.1f}"
        bugs = f"{r.get('pipeline_bugs_median', 0):.0f}/8"
        quality = f"{r.get('pipeline_quality_median', 0):.2f}"
        cpb = f"${r['cost_per_bug']:.4f}" if r.get("cost_per_bug") else "INF"
        complete = "Yes" if r.get("pipeline_complete") else "No"
        lines.append(f"| {i} | {r['display_name']} | {cost} | {time_s} | {bugs} | {quality} | {cpb} | {complete} |")

    lines += ["", "**These two lists are not the same. That's the entire point.**", ""]

    # Goal loop comparison if available
    goal_models = [r for r in rankings if r.get("goal_cost_median") is not None]
    if goal_models:
        lines += [
            "### Autonomous Goal Loop (Track 2)",
            "",
            "| Model | Turns | Cost | Bugs Fixed | Goal Met? | Autonomy Premium |",
            "|-------|-------|------|------------|-----------|------------------|",
        ]
        for r in goal_models:
            turns = f"{r.get('goal_turns_median', 0):.0f}"
            cost = f"${r.get('goal_cost_median', 0):.4f}"
            bugs = f"{r.get('goal_bugs_median', 0):.0f}/8"
            met = f"{r.get('goal_met_rate', 0):.0%}"
            premium = f"{r.get('autonomy_premium', 0):.1f}x" if r.get("autonomy_premium") else "N/A"
            lines.append(f"| {r['display_name']} | {turns} | {cost} | {bugs} | {met} | {premium} |")
        lines.append("")

    output_path.write_text("\n".join(lines))
