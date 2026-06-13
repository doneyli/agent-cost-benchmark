"""Tester agent — generates test cases for the fixes."""

from __future__ import annotations

from pathlib import Path

from langfuse import observe

from benchmark.agents.base import BaseAgent
from benchmark.schemas.agents import FixerOutput

SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "tester.md").read_text()


class TesterAgent(BaseAgent):
    def __init__(self, model_id: str):
        super().__init__(model_id, "tester")

    @observe(name="tester")
    def run(self, fixes: FixerOutput) -> str:
        """Generate test code for the applied fixes. Returns raw test file content."""
        changes_text = "\n".join(
            f"File: {f.path}\n  Changes: {', '.join(f.changes_made)}"
            for f in fixes.fixed_files
        )
        fixed_code = "\n\n".join(
            f"### {f.path}\n```python\n{f.content}\n```" for f in fixes.fixed_files
        )
        user_prompt = (
            f"The following bugs were fixed:\n{', '.join(fixes.bugs_addressed)}\n\n"
            f"Changes made:\n{changes_text}\n\n"
            f"Fixed code:\n{fixed_code}\n\n"
            f"Write pytest test cases that verify each fix."
        )
        return self.call_llm(SYSTEM_PROMPT, user_prompt)
