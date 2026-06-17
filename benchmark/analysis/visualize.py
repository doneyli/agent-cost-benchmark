"""Chart generation for benchmark results."""

from __future__ import annotations

from pathlib import Path

from benchmark.analysis.compare import generate_comparison


def generate_charts(results_dir: Path, charts_dir: Path) -> None:
    """Generate all benchmark charts."""
    rankings = generate_comparison(results_dir)

    _cost_vs_time_scatter(rankings, charts_dir)
    _progress_curves(results_dir, charts_dir)


def _cost_vs_time_scatter(rankings: list[dict], charts_dir: Path) -> None:
    """Two-axis scatter: cost vs time, bubble = quality, color = provider."""
    try:
        import plotly.graph_objects as go
    except ImportError:
        print("plotly not installed — skipping scatter chart")
        return

    provider_colors = {"anthropic": "#1e88e5", "openai": "#43a047", "openrouter": "#fb8c00"}

    fig = go.Figure()
    for r in rankings:
        if not r.get("pipeline_cost_median"):
            continue
        fig.add_trace(go.Scatter(
            x=[r["pipeline_cost_median"]],
            y=[r.get("pipeline_time_median", 0)],
            mode="markers+text",
            marker=dict(
                size=max((r.get("pipeline_quality_median", 0) or 0) * 80, 10),
                color=provider_colors.get(r["provider"], "#999"),
                opacity=0.7,
            ),
            text=[r["display_name"]],
            textposition="top center",
            name=r["display_name"],
        ))

    fig.update_layout(
        title="Cost per Token vs Cost per Task Completion",
        xaxis_title="Total Cost ($)",
        yaxis_title="Wall-Clock Time (seconds)",
        showlegend=True,
    )
    fig.write_html(str(charts_dir / "cost_vs_time_scatter.html"))


def _progress_curves(results_dir: Path, charts_dir: Path) -> None:
    """Goal loop progress curves: bugs fixed vs turns."""
    import json

    try:
        import plotly.graph_objects as go
    except ImportError:
        print("plotly not installed — skipping progress chart")
        return

    fig = go.Figure()
    for f in sorted(results_dir.glob("goal_*.json")):
        data = json.loads(f.read_text())
        if not data.get("turn_history"):
            continue

        turns = [t["turn"] for t in data["turn_history"]]
        bugs = [t["bugs_passing"] for t in data["turn_history"]]

        fig.add_trace(go.Scatter(
            x=turns,
            y=bugs,
            mode="lines+markers",
            name=f"{data['model_id']} (run {data['run_number']})",
        ))

    fig.update_layout(
        title="Goal Loop: Progress Curves",
        xaxis_title="Turn",
        yaxis_title="Bugs Fixed (of 8)",
        yaxis=dict(range=[0, 9]),
    )
    fig.write_html(str(charts_dir / "progress_curves.html"))
