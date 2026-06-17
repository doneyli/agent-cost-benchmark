"""Reviewer agent — code reviews the changes."""

from __future__ import annotations

from pathlib import Path

from langfuse import observe

from benchmark.agents.base import BaseAgent, UsageAccumulator
from benchmark.schemas.agents import FixerOutput, ReviewerOutput

SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "reviewer.md").read_text()


class ReviewerAgent(BaseAgent):
    def __init__(self, model_id: str, usage: UsageAccumulator | None = None):
        super().__init__(model_id, "reviewer", usage=usage)

    @observe(name="reviewer")
    def run(
        self,
        original_code: dict[str, str],
        fixes: FixerOutput,
        test_code: str,
    ) -> ReviewerOutput:
        """Review the fixes and tests."""
        original_block = "\n\n".join(
            f"### {path}\n```python\n{content}\n```"
            for path, content in original_code.items()
        )
        fixed_block = "\n\n".join(
            f"### {f.path}\n```python\n{f.content}\n```" for f in fixes.fixed_files
        )
        user_prompt = (
            f"## Original code\n{original_block}\n\n"
            f"## Fixed code\n{fixed_block}\n\n"
            f"## Generated tests\n```python\n{test_code}\n```\n\n"
            f"## Bugs addressed\n{', '.join(fixes.bugs_addressed)}\n\n"
            f"Review these changes."
        )
        return self.call_llm_structured_safe(SYSTEM_PROMPT, user_prompt, ReviewerOutput)
