# Newsletter Notes: Cost per Token vs Cost per Task

> Running observations, surprises, and quotable moments from building and running the benchmark. Feed directly into the newsletter draft.

---

## Build Phase Notes

### 2026-06-14 — Scaffold design session

**The question that started this:** "I want to compare the same task across various models to compare the tokens used, the total cost, and evaluate quality throughout."

**Key design decisions made:**
- Two tracks: prescribed pipeline (we tell it HOW) vs autonomous goal loop (we tell it WHAT)
- 8 planted bugs in a FastAPI app — objective, testable, reproducible
- Langfuse as the instrumentation centerpiece — not just an add-on, but the way we see everything
- 6 models across 3 providers: Claude (Opus/Sonnet/Haiku), OpenAI (GPT-4o/4o-mini), DeepSeek V3

**The thesis crystallized early:** "Cost per token is the wrong unit of account. A cheaper model that burns 3x the tokens is the more expensive model." But we added the nuance: "Conversely, a cheaper model that takes longer but still completes correctly at lower total cost IS genuinely cheaper. Time and cost are independent dimensions."

**Prior work discovery (6/14):** Found 20+ existing benchmarks. The closest: Stanford's "Cost-of-Pass" (formal metric), Princeton's HAL (Pareto frontiers), CEBench (pipeline-level cost). But nobody does prescribed-vs-autonomous comparison on the same task. That's our lane.

**Grizzly Peak quote (use in newsletter):** "The cheapest model per token is often the most expensive model per result." — We're proving this with data.

**CLEAR Framework finding (use in newsletter):** "Optimizing for accuracy alone yields agents 4.4-10.8x more expensive than cost-aware alternatives." — Cost MUST be a first-class metric.

### 2026-06-17 — Implementation begins

**Observation:** Building the benchmark itself is a meta-experiment. We're using Claude Code (Opus) to build a benchmark that tests Claude models. The irony writes itself.

**Newsletter hook potential:** "I built a benchmark to test whether expensive models are worth it. The most expensive model built the benchmark."

---

## Run Phase Notes

> Fill in as runs complete. Track surprises, unexpected results, quotable data points.

### Model behavior observations
<!-- Add per-model notes as runs complete -->

### Surprising results
<!-- Things that challenge assumptions -->

### Data points for the newsletter
<!-- Specific numbers, charts, comparisons that tell the story -->

---

## Newsletter Framing Ideas

**Possible openers:**
- "Last week I spent $X to prove that spending more doesn't mean getting more."
- "The model that costs 50x more per token fixed the same number of bugs."
- Grizzly Peak quote as the hook, then "I decided to prove it."

**The two rankings table** — rank by $/1M tokens, then rank by $/bug fixed. The lists won't match. That's the whole story.

**The scatter plot** — cost vs time, bubble size = quality. The "sweet spot" quadrant vs the "worst" quadrant tells the story visually.

**The progress curves** (Track 2) — bugs fixed over turns. Shows which models converge fast vs which ones thrash.

**The autonomy premium** — "The cheaper the model, the more expensive autonomy becomes." (Hypothesis — validate with data.)

**Closing frame:** Not "which model is best" but "which model is best FOR THIS TASK AT THIS BUDGET." Cost-per-task reframes the question from vendor marketing to practitioner economics.
