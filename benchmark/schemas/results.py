"""Standardized result schemas for benchmark output."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AgentMetrics(BaseModel):
    agent_name: str
    tokens_input: int
    tokens_output: int
    tokens_total: int
    cost_usd: float
    duration_seconds: float
    llm_calls: int


class GateResult(BaseModel):
    gate_name: str
    passed: bool
    score: float
    details: dict


class PipelineResult(BaseModel):
    """Track 1: Prescribed pipeline result."""

    run_id: str
    model_id: str
    provider: str
    track: str = "pipeline"
    run_number: int
    timestamp: datetime

    # Primary metrics
    total_cost_usd: float
    total_tokens: int
    total_input_tokens: int
    total_output_tokens: int
    wall_clock_seconds: float

    # Quality metrics
    bugs_detected: int = Field(ge=0, le=8)
    bugs_fixed_correctly: int = Field(ge=0, le=8)
    tests_generated: int
    tests_passing: int
    existing_tests_pass: bool
    overall_quality: float = Field(ge=0.0, le=1.0)
    pipeline_complete: bool

    # Per-agent breakdown
    agent_metrics: list[AgentMetrics]
    gate_results: list[GateResult]

    # Derived (computed post-hoc)
    cost_per_bug_fixed: float | None = None
    time_per_bug_fixed: float | None = None
    token_efficiency: float | None = None

    # Cache info (Anthropic only)
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    # Langfuse reference
    langfuse_trace_id: str | None = None


class TurnSnapshot(BaseModel):
    turn: int
    bugs_passing: int
    cumulative_cost: float
    cumulative_tokens: int


class GoalLoopResult(BaseModel):
    """Track 2: Autonomous goal-loop result."""

    run_id: str
    model_id: str
    provider: str
    track: str = "goal"
    run_number: int
    timestamp: datetime

    # Primary metrics
    total_cost_usd: float
    total_tokens: int
    wall_clock_seconds: float

    # Goal-specific metrics
    total_turns: int
    goal_met: bool
    bugs_fixed: int = Field(ge=0, le=8)
    existing_tests_pass: bool
    evaluator_calls: int
    evaluator_cost_usd: float
    tool_calls: int

    # Progress curve
    turn_history: list[TurnSnapshot]

    # Derived
    cost_per_bug_fixed: float | None = None
    turns_to_first_fix: int | None = None
    turns_to_completion: int | None = None

    # Langfuse reference
    langfuse_trace_id: str | None = None


class ModelRanking(BaseModel):
    model_id: str
    display_name: str
    provider: str
    tier: str
    input_price_per_m: float
    output_price_per_m: float
    pipeline_cost_median: float | None = None
    pipeline_quality_median: float | None = None
    pipeline_bugs_fixed_median: float | None = None
    goal_cost_median: float | None = None
    goal_turns_median: float | None = None
    goal_bugs_fixed_median: float | None = None
    autonomy_premium: float | None = None


class BenchmarkSummary(BaseModel):
    """Cross-model comparison summary."""

    benchmark_version: str = "v1"
    run_date: datetime
    total_cost_usd: float

    pipeline_results: list[PipelineResult]
    goal_results: list[GoalLoopResult]
    model_rankings: list[ModelRanking]
