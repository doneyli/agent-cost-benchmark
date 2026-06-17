"""Scout agent — analyzes codebase and identifies bugs."""

from __future__ import annotations

from pathlib import Path

from langfuse import observe

from benchmark.agents.base import BaseAgent, UsageAccumulator
from benchmark.schemas.agents import ScoutOutput

SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "scout.md").read_text()


class ScoutAgent(BaseAgent):
    def __init__(self, model_id: str, usage: UsageAccumulator | None = None):
        super().__init__(model_id, "scout", usage=usage)

    @observe(name="scout")
    def run(self, source_code: dict[str, str]) -> ScoutOutput:
        """Analyze source code and return structured bug findings."""
        code_block = "\n\n".join(
            f"### {path}\n```python\n{content}\n```" for path, content in source_code.items()
        )
        user_prompt = (
            "Analyze the following Python codebase and identify all bugs.\n\n" + code_block
        )
        return self.call_llm_structured_safe(SYSTEM_PROMPT, user_prompt, ScoutOutput)
