"""Triage agent — prioritizes bug findings into a fix plan."""

from __future__ import annotations

from pathlib import Path

from langfuse import observe

from benchmark.agents.base import BaseAgent, UsageAccumulator
from benchmark.schemas.agents import ScoutOutput, TriageOutput

SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "triage.md").read_text()


class TriageAgent(BaseAgent):
    def __init__(self, model_id: str, usage: UsageAccumulator | None = None):
        super().__init__(model_id, "triage", usage=usage)

    @observe(name="triage")
    def run(self, findings: ScoutOutput) -> TriageOutput:
        """Create a prioritized fix plan from scout findings."""
        findings_text = "\n".join(
            f"- [{f.severity.upper()}] [{f.category}] {f.file}:{f.line} — {f.description}"
            for f in findings.findings
        )
        user_prompt = (
            f"Here are the bug findings to triage and prioritize:\n\n{findings_text}\n\n"
            f"Summary: {findings.summary}"
        )
        return self.call_llm_structured_safe(SYSTEM_PROMPT, user_prompt, TriageOutput)
