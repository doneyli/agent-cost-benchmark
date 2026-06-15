"""CLI entry point for the benchmark."""

from __future__ import annotations

import json
import time
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from benchmark.config import MODEL_LOOKUP, PROVIDER_CONFIGS, RUN_ORDER, RUNS_PER_MODEL

console = Console()
RESULTS_DIR = Path(__file__).parent.parent / "results" / "raw"


def _load_source_code() -> dict[str, str]:
    """Load the target project source files."""
    target_dir = Path(__file__).parent.parent / "target_project"
    source = {}
    for f in sorted(target_dir.glob("*.py")):
        source[f"target_project/{f.name}"] = f.read_text()
    return source


@click.group()
def cli():
    """Agent Cost Benchmark — Cost per Token vs Cost per Task Completion."""
    pass


@cli.command()
@click.option("--model", "-m", help="Model ID to run (default: all)")
@click.option("--track", "-t", type=click.Choice(["pipeline", "goal", "both"]), default="both")
@click.option("--repeat", "-r", default=RUNS_PER_MODEL, help="Number of runs per model")
@click.option("--dry-run", is_flag=True, help="Validate setup without making API calls")
@click.option(
    "--experiment", "-e", is_flag=True,
    help="Run via Langfuse Experiments (dataset.run_experiment) for side-by-side comparison in Langfuse UI",
)
def run(model: str | None, track: str, repeat: int, dry_run: bool, experiment: bool):
    """Run the benchmark for one or all models."""
    from benchmark.agents.base import get_langfuse

    models = [model] if model else RUN_ORDER
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if experiment:
        _run_experiment_mode(models, repeat, dry_run)
        return

    for model_id in models:
        if model_id not in MODEL_LOOKUP:
            console.print(f"[red]Unknown model: {model_id}[/red]")
            continue

        config = MODEL_LOOKUP[model_id]
        console.print(f"\n[bold]{'=' * 60}[/bold]")
        console.print(f"[bold cyan]{config.display_name}[/bold cyan] ({config.provider} / {config.tier})")
        console.print(f"Pricing: ${config.input_price_per_m}/M in, ${config.output_price_per_m}/M out")

        if dry_run:
            console.print("[yellow]DRY RUN — skipping API calls[/yellow]")
            continue

        provider_config = PROVIDER_CONFIGS[config.provider]

        if track in ("pipeline", "both"):
            _run_pipeline_track(model_id, repeat, provider_config)

        if track in ("goal", "both"):
            _run_goal_track(model_id, repeat, provider_config)

    get_langfuse().flush()
    console.print("\n[bold green]Benchmark complete.[/bold green]")


def _run_experiment_mode(models: list[str], repeat: int, dry_run: bool):
    """Run via Langfuse Experiments for side-by-side comparison in the UI."""
    from benchmark.agents.base import get_langfuse
    from benchmark.datasets import ensure_dataset, run_experiment

    console.print("\n[bold]Setting up Langfuse Dataset...[/bold]")
    if dry_run:
        console.print("[yellow]DRY RUN — would create dataset 'cost-per-task-benchmark'[/yellow]")
        return

    ensure_dataset()
    console.print("[green]Dataset ready: cost-per-task-benchmark[/green]")

    for model_id in models:
        if model_id not in MODEL_LOOKUP:
            console.print(f"[red]Unknown model: {model_id}[/red]")
            continue

        config = MODEL_LOOKUP[model_id]
        provider_config = PROVIDER_CONFIGS[config.provider]
        console.print(f"\n[bold]{'=' * 60}[/bold]")
        console.print(f"[bold cyan]{config.display_name}[/bold cyan] (experiment mode)")

        # Warm-up for Anthropic
        if config.provider == "anthropic":
            console.print("  [dim]Cache warm-up...[/dim]")
            try:
                run_experiment(model_id, run_number=0)
            except Exception as e:
                console.print(f"  [yellow]Warm-up failed: {e}[/yellow]")
            time.sleep(2)

        for run_num in range(1, repeat + 1):
            console.print(f"  [experiment] Run {run_num}/{repeat}...")
            try:
                result = run_experiment(model_id, run_number=run_num)
                output_file = RESULTS_DIR / f"experiment_{model_id}_{run_num}.json"
                output_file.write_text(json.dumps(result, indent=2, default=str))
                console.print(f"    Experiment: {result['experiment_name']}")
            except Exception as e:
                console.print(f"    [red]FAILED: {e}[/red]")

            time.sleep(provider_config.delay_between_runs)

    get_langfuse().flush()
    console.print("\n[bold green]All experiments complete. View in Langfuse UI → Datasets → cost-per-task-benchmark[/bold green]")


def _run_pipeline_track(model_id: str, repeat: int, provider_config):
    """Run Track 1: prescribed pipeline."""
    from benchmark.runner import run_pipeline

    source_code = _load_source_code()
    config = MODEL_LOOKUP[model_id]

    # Warm-up for Anthropic (prompt cache priming)
    if config.provider == "anthropic":
        console.print("  [dim]Cache warm-up...[/dim]")
        try:
            run_pipeline(model_id, source_code, run_number=0)
        except Exception as e:
            console.print(f"  [yellow]Warm-up failed: {e}[/yellow]")
        time.sleep(2)

    for run_num in range(1, repeat + 1):
        console.print(f"  [pipeline] Run {run_num}/{repeat}...")
        try:
            result = run_pipeline(model_id, source_code, run_number=run_num)
            output_file = RESULTS_DIR / f"pipeline_{model_id}_{run_num}.json"
            output_file.write_text(json.dumps(result, indent=2, default=str))
            console.print(
                f"    Bugs: {result['bugs_detected']} found, "
                f"{result['bugs_fixed_correctly']} fixed | "
                f"Quality: {result['overall_quality']} | "
                f"Time: {result['wall_clock_seconds']}s"
            )
        except Exception as e:
            console.print(f"    [red]FAILED: {e}[/red]")

        time.sleep(provider_config.delay_between_runs)


def _run_goal_track(model_id: str, repeat: int, provider_config):
    """Run Track 2: autonomous goal loop."""
    import shutil
    import tempfile

    from benchmark.goal_loop import run_goal_loop

    target_src = Path(__file__).parent.parent / "target_project"

    for run_num in range(1, repeat + 1):
        console.print(f"  [goal] Run {run_num}/{repeat}...")

        # Create isolated working copy
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = Path(tmpdir)
            shutil.copytree(target_src, work_dir / "target_project")
            # Also copy manifest tests
            manifest_tests = Path(__file__).parent.parent / "bugs_manifest_tests"
            if manifest_tests.exists():
                shutil.copytree(manifest_tests, work_dir / "bugs_manifest_tests")

            try:
                result = run_goal_loop(model_id, work_dir, run_number=run_num)
                output_file = RESULTS_DIR / f"goal_{model_id}_{run_num}.json"
                output_file.write_text(json.dumps(result, indent=2, default=str))
                console.print(
                    f"    Goal: {'MET' if result['goal_met'] else 'NOT MET'} | "
                    f"Turns: {result['total_turns']} | "
                    f"Bugs: {result['bugs_fixed']}/8 | "
                    f"Cost: ${result['total_cost_usd']:.4f} | "
                    f"Time: {result['wall_clock_seconds']}s"
                )
            except Exception as e:
                console.print(f"    [red]FAILED: {e}[/red]")

        time.sleep(provider_config.delay_between_runs)


@cli.command()
def setup():
    """One-time setup: configure Langfuse model pricing and create the benchmark dataset."""
    from benchmark.datasets import ensure_dataset

    console.print("[bold]1/2 — Setting up Langfuse model pricing...[/bold]")
    try:
        from benchmark.scripts.setup_langfuse_models import main as setup_models
        setup_models()
        console.print("[green]Model pricing configured.[/green]")
    except Exception as e:
        console.print(f"[yellow]Model pricing setup failed: {e}[/yellow]")
        console.print("[dim]You can configure models manually in Langfuse UI → Settings → Models[/dim]")

    console.print("\n[bold]2/2 — Creating Langfuse dataset...[/bold]")
    try:
        ensure_dataset()
        console.print("[green]Dataset 'cost-per-task-benchmark' ready.[/green]")
    except Exception as e:
        console.print(f"[red]Dataset creation failed: {e}[/red]")

    console.print("\n[bold green]Setup complete.[/bold green]")
    console.print("[dim]Next: benchmark run --experiment --model claude-haiku-4-5-20251001 --repeat 1[/dim]")


@cli.command()
def compare():
    """Generate cross-model comparison from results."""
    from benchmark.analysis.compare import generate_comparison

    results = generate_comparison(RESULTS_DIR)
    _print_comparison_table(results)


@cli.command()
def chart():
    """Generate visualization charts from results."""
    from benchmark.analysis.visualize import generate_charts

    charts_dir = Path(__file__).parent.parent / "results" / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    generate_charts(RESULTS_DIR, charts_dir)
    console.print(f"[green]Charts saved to {charts_dir}[/green]")


@cli.command()
def export():
    """Export results as newsletter-ready markdown."""
    from benchmark.analysis.export import export_newsletter

    output = Path(__file__).parent.parent / "results" / "newsletter_export.md"
    export_newsletter(RESULTS_DIR, output)
    console.print(f"[green]Newsletter export saved to {output}[/green]")


def _print_comparison_table(results: list[dict]):
    """Print a rich comparison table to the terminal."""
    table = Table(title="Cost per Token vs Cost per Task")
    table.add_column("Model", style="cyan")
    table.add_column("$/1M tok", justify="right")
    table.add_column("Total $", justify="right")
    table.add_column("Time (s)", justify="right")
    table.add_column("Bugs Fixed", justify="center")
    table.add_column("Quality", justify="right")
    table.add_column("$/Bug", justify="right")
    table.add_column("Complete?", justify="center")

    for r in results:
        table.add_row(
            r["display_name"],
            f"${r['output_price_per_m']:.2f}",
            f"${r.get('pipeline_cost_median', 0):.4f}",
            f"{r.get('pipeline_time_median', 0):.1f}",
            f"{r.get('pipeline_bugs_median', 0):.0f}/8",
            f"{r.get('pipeline_quality_median', 0):.2f}",
            f"${r.get('cost_per_bug', 0):.4f}" if r.get("cost_per_bug") else "N/A",
            "[green]Yes[/green]" if r.get("pipeline_complete") else "[red]No[/red]",
        )

    console.print(table)
