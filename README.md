# Agent Cost Benchmark

**Cost per Token vs Cost per Task Completion** — a multi-model benchmark that proves the cheapest model per token isn't always the cheapest model per task.

## The Thesis

Cost-per-token is the wrong unit of account. A "cheaper" model that burns 3x the tokens, takes 3x longer, or doesn't finish correctly is the more expensive model. Conversely, a "cheaper" model that takes longer but still completes correctly at lower total cost IS genuinely cheaper.

This benchmark measures what actually matters: **how much does it cost to get the job done?**

## What It Measures

| Metric | Unit | Source |
|--------|------|--------|
| Total cost to complete task | USD | Langfuse trace cost_details |
| Wall-clock time | seconds | Timer |
| Bugs found (of 8) | count | Programmatic (manifest match) |
| Bugs correctly fixed (of 8) | count | Programmatic (pytest) |
| Quality score | 0-1 composite | Programmatic + LLM-as-judge |
| Cost per bug fixed | USD | Derived |
| Time per bug fixed | seconds | Derived |
| Autonomy premium | ratio | Track 2 cost / Track 1 cost |

## Two Benchmark Tracks

**Track 1 — Prescribed Pipeline:** 5 agents run in sequence (Scout → Triage → Fixer → Tester → Reviewer). Same prompts, same flow for every model. Measures model capability at each sub-task.

**Track 2 — Autonomous Goal Loop:** The model gets tools (read, edit, bash) and a goal ("fix all bugs, make all tests pass"). It decides its own workflow. Measures how efficiently each model self-directs. Uses Haiku as the completion evaluator (mirrors Claude Code's `/goal` behavior).

## Models Compared

| Provider | Model | Tier |
|----------|-------|------|
| Anthropic | Claude Opus 4.6 | Premium |
| Anthropic | Claude Sonnet 4.6 | Mid |
| Anthropic | Claude Haiku 4.5 | Value |
| OpenAI | GPT-4o | Mid |
| OpenAI | GPT-4o-mini | Value |
| OpenRouter | DeepSeek V3 | Value (open-weight) |

## The Benchmark Task: "Bug Hunt"

A FastAPI task management API (`target_project/`) with 8 intentionally planted bugs:

| Bug | Category | Severity |
|-----|----------|----------|
| SQL injection in search | Security | Critical |
| Off-by-one in pagination | Logic | High |
| Past due dates accepted | Data integrity | High |
| N+1 query pattern | Performance | Medium |
| Unhandled ValueError | Error handling | Medium |
| Race condition in counter | Concurrency | Medium |
| Wrong priority weight | Business logic | Low |
| Empty status filter crash | Edge case | Low |

Ground truth: `bugs_manifest.json` + 8 pytest tests in `bugs_manifest_tests/` that fail on the buggy code and pass on correct code.

## Quick Start

```bash
# Clone and install
git clone https://github.com/doneyli/agent-cost-benchmark.git
cd agent-cost-benchmark
pip install -e .

# Set up environment
cp .env.example .env
# Edit .env with your API keys (Anthropic, OpenAI, OpenRouter, Langfuse)

# Verify the target project
pytest target_project/tests/ -v          # Should PASS (existing tests)
pytest bugs_manifest_tests/ -v           # Should FAIL (8 bugs unfixed)

# One-time Langfuse setup (model pricing + dataset)
benchmark setup

# Run a single model (cheapest first to validate)
benchmark run --model claude-haiku-4-5-20251001 --track pipeline --repeat 1

# Run all models via Langfuse Experiments
benchmark run --experiment

# Run all models (direct mode, both tracks)
benchmark run

# Analyze
benchmark compare    # Terminal comparison table
benchmark chart      # Plotly charts in results/charts/
benchmark export     # Newsletter-ready markdown
```

## CLI Commands

| Command | What It Does |
|---------|--------------|
| `benchmark setup` | Configure Langfuse model pricing + create dataset |
| `benchmark run` | Run benchmark (direct mode with JSON output) |
| `benchmark run --experiment` | Run via Langfuse Experiments (side-by-side in UI) |
| `benchmark run --model X` | Single model only |
| `benchmark run --track pipeline` | Track 1 only |
| `benchmark run --track goal` | Track 2 only |
| `benchmark run --repeat 5` | 5 runs per model (default: 3) |
| `benchmark run --dry-run` | Validate setup without API calls |
| `benchmark compare` | Print comparison table |
| `benchmark chart` | Generate Plotly charts |
| `benchmark export` | Export newsletter markdown |

## Project Structure

```
benchmark/
  agents/          # 5 specialized agents + provider-agnostic base
  evals/           # Programmatic (manifest) + LLM-as-judge evaluators
  analysis/        # Comparison, charts, newsletter export
  schemas/         # Pydantic models for agent output + results
  prompts/         # Agent system prompts
  scripts/         # Langfuse setup, Claude Code /goal runner
  datasets.py      # Langfuse Datasets + Experiments integration
  runner.py        # Track 1 pipeline orchestrator
  goal_loop.py     # Track 2 autonomous loop
  tools.py         # Sandboxed tools for goal loop
  config.py        # Model matrix, pricing, rate limits
  cli.py           # Click CLI
target_project/    # The bug-planted FastAPI app
bugs_manifest_tests/  # 8 ground-truth tests (one per bug)
bugs_manifest.json    # Bug locations, categories, reference fixes
```

## Langfuse Integration

This benchmark uses [Langfuse](https://langfuse.com) as the instrumentation centerpiece:

- **Tracing:** Every LLM call is a generation span within agent spans within a trace
- **Cost tracking:** Per-generation token counts + cost via model pricing definitions
- **Evaluations:** Programmatic scores (bugs found/fixed) + LLM-as-judge (quality 1-5)
- **Datasets + Experiments:** Side-by-side model comparison in the Langfuse UI
- **Sessions:** Runs grouped by model for aggregation

## Estimated API Cost

Running the full benchmark (~$38, ~$57 with buffer):

| Component | Estimate |
|-----------|----------|
| Track 1 (6 models × 3 runs) | ~$5 |
| Track 2 (6 models × 3 runs) | ~$30 |
| LLM-as-judge evaluations | ~$2 |
| Evaluator (Haiku) | ~$0.50 |
| **Total with 50% buffer** | **~$57** |

## Prior Work

This benchmark builds on several existing frameworks:

- **[Cost-of-Pass](https://arxiv.org/abs/2504.13359)** (Stanford, 2025) — Formal metric definition for cost per correct answer
- **[HAL](https://arxiv.org/abs/2510.11977)** (Princeton, 2025) — Pareto frontier visualization for agent cost vs accuracy
- **[CEBench](https://arxiv.org/abs/2407.12797)** (2024) — Pipeline-level cost-effectiveness evaluation
- **[CLEAR](https://arxiv.org/abs/2511.14136)** (2025) — Enterprise agent evaluation with cost as first-class dimension

See [design spec](https://github.com/doneyli/content-system/issues/475) for full prior work analysis and differentiation.

## License

MIT
