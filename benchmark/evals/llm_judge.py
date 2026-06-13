"""LLM-as-judge evaluators — quality scoring via a fixed judge model."""

from __future__ import annotations

from pathlib import Path

import anthropic
from langfuse import observe

JUDGE_MODEL = "claude-sonnet-4-6-20250514"

_client: anthropic.Anthropic | None = None

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _load_template(name: str) -> str:
    return (TEMPLATES_DIR / f"{name}.txt").read_text()


@observe(name="llm_judge")
def judge(template_name: str, variables: dict[str, str]) -> dict:
    """Run an LLM-as-judge evaluation.

    Returns {"score": int (1-5), "rationale": str}.
    """
    template = _load_template(template_name)

    prompt = template
    for key, value in variables.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", value)

    client = _get_client()
    response = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=500,
        temperature=0.0,
        system=(
            "You are an expert code quality evaluator. "
            "Return your assessment as JSON: {\"score\": <1-5>, \"rationale\": \"<explanation>\"}"
        ),
        messages=[{"role": "user", "content": prompt}],
    )

    import json

    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]

    result = json.loads(text)

    return {
        "score": int(result["score"]),
        "rationale": result.get("rationale", ""),
        "judge_model": JUDGE_MODEL,
        "judge_input_tokens": response.usage.input_tokens,
        "judge_output_tokens": response.usage.output_tokens,
    }
