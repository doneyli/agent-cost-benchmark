"""Base agent with Langfuse tracing and provider-agnostic LLM calls."""

from __future__ import annotations

import json
import os
from typing import TypeVar

import anthropic
from langfuse import Langfuse, observe
from langfuse.openai import openai
from pydantic import BaseModel, ValidationError

from benchmark.config import MODEL_LOOKUP, TEMPERATURE

T = TypeVar("T", bound=BaseModel)

# ---------------------------------------------------------------------------
# Provider clients (initialized lazily)
# ---------------------------------------------------------------------------

_anthropic_client: anthropic.Anthropic | None = None
_openai_client: openai.OpenAI | None = None
_openrouter_client: openai.OpenAI | None = None
_langfuse: Langfuse | None = None


def get_anthropic_client() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic()
    return _anthropic_client


def get_openai_client() -> openai.OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = openai.OpenAI()
    return _openai_client


def get_openrouter_client() -> openai.OpenAI:
    global _openrouter_client
    if _openrouter_client is None:
        _openrouter_client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
        )
    return _openrouter_client


def get_langfuse() -> Langfuse:
    global _langfuse
    if _langfuse is None:
        _langfuse = Langfuse()
    return _langfuse


# ---------------------------------------------------------------------------
# Base agent
# ---------------------------------------------------------------------------

class UsageAccumulator:
    """Tracks cumulative token usage and cost across all LLM calls in a run."""

    def __init__(self):
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_cache_read_tokens: int = 0
        self.total_cache_creation_tokens: int = 0
        self.calls: int = 0

    def record(self, input_tokens: int, output_tokens: int,
               cache_read: int = 0, cache_creation: int = 0) -> None:
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cache_read_tokens += cache_read
        self.total_cache_creation_tokens += cache_creation
        self.calls += 1

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    def compute_cost(self, config: "ModelConfig") -> float:
        return (
            self.total_input_tokens * config.input_price_per_m / 1_000_000
            + self.total_output_tokens * config.output_price_per_m / 1_000_000
        )

    def to_dict(self) -> dict:
        return {
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "cache_read_tokens": self.total_cache_read_tokens,
            "cache_creation_tokens": self.total_cache_creation_tokens,
            "llm_calls": self.calls,
        }


class BaseAgent:
    """Provider-agnostic agent with Langfuse tracing and structured output."""

    def __init__(self, model_id: str, agent_name: str, usage: UsageAccumulator | None = None):
        self.model_id = model_id
        self.agent_name = agent_name
        self.config = MODEL_LOOKUP[model_id]
        self.provider = self.config.provider
        self.usage = usage or UsageAccumulator()

    # -- Unstructured output -------------------------------------------------

    @observe(as_type="generation")
    def call_llm(self, system_prompt: str, user_prompt: str) -> str:
        if self.provider == "anthropic":
            return self._call_anthropic(system_prompt, user_prompt)
        elif self.provider == "openai":
            return self._call_openai(get_openai_client(), system_prompt, user_prompt)
        else:
            return self._call_openai(
                get_openrouter_client(),
                system_prompt,
                user_prompt,
                extra_body={"usage": {"include": True}},
            )

    # -- Structured output ---------------------------------------------------

    @observe(as_type="generation")
    def call_llm_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
    ) -> T:
        if self.provider == "anthropic":
            return self._structured_anthropic(system_prompt, user_prompt, response_model)
        else:
            client = (
                get_openai_client()
                if self.provider == "openai"
                else get_openrouter_client()
            )
            extra = {"usage": {"include": True}} if self.provider == "openrouter" else None
            return self._structured_openai(client, system_prompt, user_prompt, response_model, extra)

    def call_llm_structured_safe(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
    ) -> T:
        """Structured output with prompt-based fallback."""
        try:
            return self.call_llm_structured(system_prompt, user_prompt, response_model)
        except (json.JSONDecodeError, ValidationError):
            return self._structured_fallback(system_prompt, user_prompt, response_model)

    # -- Provider implementations --------------------------------------------

    def _call_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        client = get_anthropic_client()
        response = client.messages.create(
            model=self.model_id,
            max_tokens=4096,
            temperature=TEMPERATURE,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        input_tok = response.usage.input_tokens
        output_tok = response.usage.output_tokens
        cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0) or 0

        self.usage.record(input_tok, output_tok, cache_read, cache_creation)

        lf = get_langfuse()
        lf.update_current_generation(
            model=self.model_id,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            output=response.content[0].text,
            usage_details={
                "input": input_tok,
                "output": output_tok,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_creation,
            },
        )
        return response.content[0].text

    def _call_openai(
        self,
        client: openai.OpenAI,
        system_prompt: str,
        user_prompt: str,
        extra_body: dict | None = None,
    ) -> str:
        kwargs: dict = {
            "model": self.model_id,
            "temperature": TEMPERATURE,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if extra_body:
            kwargs["extra_body"] = extra_body

        response = client.chat.completions.create(**kwargs)

        if response.usage:
            self.usage.record(
                response.usage.prompt_tokens or 0,
                response.usage.completion_tokens or 0,
            )

        return response.choices[0].message.content or ""

    def _structured_anthropic(
        self, system_prompt: str, user_prompt: str, response_model: type[T]
    ) -> T:
        client = get_anthropic_client()
        tool_schema = {
            "name": "structured_response",
            "description": "Return your analysis in this exact format",
            "input_schema": response_model.model_json_schema(),
        }

        response = client.messages.create(
            model=self.model_id,
            max_tokens=4096,
            temperature=TEMPERATURE,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[tool_schema],
            tool_choice={"type": "tool", "name": "structured_response"},
        )

        tool_block = next(b for b in response.content if b.type == "tool_use")

        input_tok = response.usage.input_tokens
        output_tok = response.usage.output_tokens
        cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0) or 0

        self.usage.record(input_tok, output_tok, cache_read, cache_creation)

        lf = get_langfuse()
        lf.update_current_generation(
            model=self.model_id,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            output=json.dumps(tool_block.input),
            usage_details={
                "input": input_tok,
                "output": output_tok,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_creation,
            },
        )

        return response_model.model_validate(tool_block.input)

    def _structured_openai(
        self,
        client: openai.OpenAI,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        extra_body: dict | None = None,
    ) -> T:
        kwargs: dict = {
            "model": self.model_id,
            "temperature": TEMPERATURE,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_response",
                    "strict": True,
                    "schema": response_model.model_json_schema(),
                },
            },
        }
        if extra_body:
            kwargs["extra_body"] = extra_body

        response = client.chat.completions.create(**kwargs)

        if response.usage:
            self.usage.record(
                response.usage.prompt_tokens or 0,
                response.usage.completion_tokens or 0,
            )

        parsed = json.loads(response.choices[0].message.content or "{}")
        return response_model.model_validate(parsed)

    def _structured_fallback(
        self, system_prompt: str, user_prompt: str, response_model: type[T]
    ) -> T:
        """Prompt-based JSON fallback for models that fail native structured output."""
        schema_str = json.dumps(response_model.model_json_schema(), indent=2)
        fallback_prompt = (
            f"{user_prompt}\n\n"
            f"IMPORTANT: Return your response as valid JSON matching this schema:\n"
            f"```json\n{schema_str}\n```\n"
            f"Return ONLY the JSON object, no other text."
        )
        raw = self.call_llm(system_prompt, fallback_prompt)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        return response_model.model_validate_json(raw)
