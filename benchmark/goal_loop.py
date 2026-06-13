"""Goal-loop runner — autonomous task completion benchmark (Track 2B).

Mimics Claude Code's /goal behavior: work turn -> check condition -> loop or stop.
Uses Haiku as the evaluator (same as /goal's built-in evaluator).
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from langfuse import observe

from benchmark.agents.base import BaseAgent, get_langfuse
from benchmark.config import MAX_GOAL_BUDGET_PER_RUN, MAX_GOAL_TURNS, MODEL_LOOKUP
from benchmark.tools import TOOL_DEFINITIONS, execute_tool, set_working_dir

EVALUATOR_MODEL = "claude-haiku-4-5-20251001"

GOAL_CONDITION = (
    "All 8 tests in bugs_manifest_tests/ pass AND "
    "all existing tests in target_project/tests/test_app.py still pass."
)

SYSTEM_PROMPT = """You are a senior software engineer. You have access to a project directory.
Your task: find and fix all bugs in target_project/.

You can:
- Read files to understand the code
- Edit files to fix bugs
- Run bash commands (e.g., pytest) to verify your fixes

After each fix, run the test suites to check progress:
  pytest bugs_manifest_tests/ -v
  pytest target_project/tests/test_app.py -v

Work methodically. Fix one bug at a time. Verify each fix before moving on.
Do not modify any test files."""


_evaluator_client: anthropic.Anthropic | None = None


def _get_evaluator() -> anthropic.Anthropic:
    global _evaluator_client
    if _evaluator_client is None:
        _evaluator_client = anthropic.Anthropic()
    return _evaluator_client


@observe(name="goal_loop")
def run_goal_loop(model_id: str, working_dir: Path, run_number: int) -> dict:
    """Run the goal loop for a single model."""
    config = MODEL_LOOKUP[model_id]
    lf = get_langfuse()
    set_working_dir(working_dir)

    lf.update_current_trace(
        session_id=f"benchmark_goal_{model_id}",
        tags=[config.provider, model_id, "benchmark", "goal"],
        metadata={
            "model_id": model_id,
            "provider": config.provider,
            "run_number": run_number,
            "track": "goal",
        },
    )

    agent = BaseAgent(model_id, "goal_worker")
    conversation: list[dict] = []
    turn_count = 0
    total_cost = 0.0
    total_tokens = 0
    tool_call_count = 0
    evaluator_cost = 0.0
    turn_history: list[dict] = []
    goal_met = False
    reason = ""
    start_time = time.monotonic()

    while turn_count < MAX_GOAL_TURNS and total_cost < MAX_GOAL_BUDGET_PER_RUN:
        turn_count += 1

        # --- Work turn: send conversation, execute tool calls ---
        turn_result = _execute_work_turn(agent, conversation, turn_count)
        conversation = turn_result["conversation"]
        total_cost += turn_result["cost"]
        total_tokens += turn_result["tokens"]
        tool_call_count += turn_result["tool_calls"]

        # --- Run tests to check progress ---
        test_results = _run_test_suites(working_dir)
        turn_history.append({
            "turn": turn_count,
            "bugs_passing": test_results["manifest_passing"],
            "existing_passing": test_results["existing_passing"],
            "cumulative_cost": round(total_cost, 6),
            "cumulative_tokens": total_tokens,
        })

        # --- Evaluate: is the goal met? ---
        eval_result = _evaluate_goal(test_results["raw_output"])
        goal_met = eval_result["met"]
        reason = eval_result["reason"]
        evaluator_cost += eval_result["cost"]
        total_cost += eval_result["cost"]

        if goal_met:
            break

    elapsed = time.monotonic() - start_time

    # Final independent verification
    final_tests = _run_test_suites(working_dir)

    result = {
        "run_id": f"goal_{model_id}_{run_number}_{int(time.time())}",
        "model_id": model_id,
        "provider": config.provider,
        "run_number": run_number,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "track": "goal",
        "goal_met": goal_met,
        "total_turns": turn_count,
        "total_cost_usd": round(total_cost, 6),
        "total_tokens": total_tokens,
        "wall_clock_seconds": round(elapsed, 2),
        "tool_calls": tool_call_count,
        "evaluator_calls": turn_count,
        "evaluator_cost_usd": round(evaluator_cost, 6),
        "bugs_fixed": final_tests["manifest_passing"],
        "existing_tests_pass": final_tests["existing_all_pass"],
        "turn_history": turn_history,
        "reason_stopped": reason if goal_met else f"max_turns ({MAX_GOAL_TURNS})",
    }

    lf.score(name="bugs_fixed", value=final_tests["manifest_passing"], data_type="NUMERIC")
    lf.score(name="goal_met", value=goal_met, data_type="BOOLEAN")
    lf.score(name="turns_to_complete", value=turn_count, data_type="NUMERIC")

    return result


@observe(name="work_turn")
def _execute_work_turn(agent: BaseAgent, conversation: list[dict], turn: int) -> dict:
    """One work turn: send to model, execute tool calls, return updated conversation."""
    if not conversation:
        conversation = [{"role": "user", "content": "Begin. List the project files first, then analyze the code."}]

    # Provider-specific tool calling
    if agent.provider == "anthropic":
        return _anthropic_work_turn(agent, conversation)
    else:
        return _openai_work_turn(agent, conversation)


def _anthropic_work_turn(agent: BaseAgent, conversation: list[dict]) -> dict:
    """Anthropic tool-use loop for one work turn."""
    from benchmark.agents.base import get_anthropic_client, get_langfuse

    client = get_anthropic_client()
    lf = get_langfuse()
    total_cost = 0.0
    total_tokens = 0
    tool_calls = 0

    anthropic_tools = [
        {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
        for t in TOOL_DEFINITIONS
    ]

    while True:
        response = client.messages.create(
            model=agent.model_id,
            max_tokens=4096,
            temperature=0.0,
            system=SYSTEM_PROMPT,
            messages=conversation,
            tools=anthropic_tools,
        )

        tokens = response.usage.input_tokens + response.usage.output_tokens
        cost = (
            response.usage.input_tokens * agent.config.input_price_per_m / 1_000_000
            + response.usage.output_tokens * agent.config.output_price_per_m / 1_000_000
        )
        total_tokens += tokens
        total_cost += cost

        conversation.append({"role": "assistant", "content": response.content})

        tool_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_blocks:
            break

        tool_results = []
        for block in tool_blocks:
            tool_calls += 1
            result = execute_tool(block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result.get("output", json.dumps(result)),
            })

        conversation.append({"role": "user", "content": tool_results})

        if response.stop_reason != "tool_use":
            break

    return {
        "conversation": conversation,
        "cost": total_cost,
        "tokens": total_tokens,
        "tool_calls": tool_calls,
    }


def _openai_work_turn(agent: BaseAgent, conversation: list[dict]) -> dict:
    """OpenAI/OpenRouter tool-use loop for one work turn."""
    from benchmark.agents.base import get_openai_client, get_openrouter_client

    client = get_openai_client() if agent.provider == "openai" else get_openrouter_client()
    total_cost = 0.0
    total_tokens = 0
    tool_calls = 0

    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in TOOL_DEFINITIONS
    ]

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation

    while True:
        kwargs: dict = {
            "model": agent.model_id,
            "temperature": 0.0,
            "messages": messages,
            "tools": openai_tools,
        }
        if agent.provider == "openrouter":
            kwargs["extra_body"] = {"usage": {"include": True}}

        response = client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        if response.usage:
            tokens = (response.usage.prompt_tokens or 0) + (response.usage.completion_tokens or 0)
            cost = (
                (response.usage.prompt_tokens or 0) * agent.config.input_price_per_m / 1_000_000
                + (response.usage.completion_tokens or 0) * agent.config.output_price_per_m / 1_000_000
            )
            total_tokens += tokens
            total_cost += cost

        messages.append(choice.message.model_dump())

        if not choice.message.tool_calls:
            break

        for tc in choice.message.tool_calls:
            tool_calls += 1
            args = json.loads(tc.function.arguments)
            result = execute_tool(tc.function.name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result.get("output", json.dumps(result)),
            })

        if choice.finish_reason != "tool_calls":
            break

    # Convert back to simple conversation format
    conversation.append({"role": "assistant", "content": choice.message.content or ""})

    return {
        "conversation": conversation,
        "cost": total_cost,
        "tokens": total_tokens,
        "tool_calls": tool_calls,
    }


def _evaluate_goal(test_output: str) -> dict:
    """Use Haiku to judge if the goal condition is met."""
    client = _get_evaluator()
    response = client.messages.create(
        model=EVALUATOR_MODEL,
        max_tokens=200,
        temperature=0.0,
        system='You judge whether a goal condition is met based on test output evidence. Return JSON: {"met": true/false, "reason": "..."}',
        messages=[{
            "role": "user",
            "content": f"CONDITION:\n{GOAL_CONDITION}\n\nEVIDENCE (test output):\n{test_output}\n\nIs the condition met?",
        }],
    )

    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    result = json.loads(text)

    cost = (
        response.usage.input_tokens * 0.0000008
        + response.usage.output_tokens * 0.000004
    )

    return {"met": result["met"], "reason": result.get("reason", ""), "cost": cost}


def _run_test_suites(working_dir: Path) -> dict:
    """Run both test suites and return structured results."""
    manifest_result = subprocess.run(
        ["python", "-m", "pytest", "bugs_manifest_tests/", "-v", "--tb=short"],
        capture_output=True, text=True, timeout=60, cwd=str(working_dir),
    )
    existing_result = subprocess.run(
        ["python", "-m", "pytest", "target_project/tests/test_app.py", "-v", "--tb=short"],
        capture_output=True, text=True, timeout=60, cwd=str(working_dir),
    )

    manifest_passing = manifest_result.stdout.count(" PASSED")
    existing_passing = existing_result.stdout.count(" PASSED")
    existing_total = existing_passing + existing_result.stdout.count(" FAILED")

    return {
        "manifest_passing": manifest_passing,
        "existing_passing": existing_passing,
        "existing_all_pass": existing_result.returncode == 0,
        "raw_output": (
            f"=== MANIFEST TESTS ===\n{manifest_result.stdout}\n"
            f"=== EXISTING TESTS ===\n{existing_result.stdout}"
        ),
    }
