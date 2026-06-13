"""Fixer agent — implements bug fixes based on the triage plan."""

from __future__ import annotations

from pathlib import Path

from langfuse import observe

from benchmark.agents.base import BaseAgent
from benchmark.schemas.agents import FixerOutput, TriageOutput

SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "fixer.md").read_text()


class FixerAgent(BaseAgent):
    def __init__(self, model_id: str):
        super().__init__(model_id, "fixer")

    @observe(name="fixer")
    def run(self, plan: TriageOutput, source_code: dict[str, str]) -> FixerOutput:
        """Implement fixes based on the triage plan."""
        plan_text = "\n".join(
            f"{item.priority}. {item.bug_description} — {item.rationale}"
            for item in sorted(plan.plan, key=lambda x: x.priority)
        )
        code_block = "\n\n".join(
            f"### {path}\n```python\n{content}\n```" for path, content in source_code.items()
        )
        user_prompt = (
            f"Fix plan (in priority order):\n{plan_text}\n\n"
            f"Strategy: {plan.strategy}\n\n"
            f"Source code:\n{code_block}"
        )
        return self.call_llm_structured_safe(SYSTEM_PROMPT, user_prompt, FixerOutput)
