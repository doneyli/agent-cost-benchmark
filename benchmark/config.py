"""Model matrix, provider configs, and Langfuse setup."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Model matrix
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelConfig:
    model_id: str
    provider: str  # "anthropic" | "openai" | "openrouter"
    tier: str  # "premium" | "mid" | "value"
    input_price_per_m: float  # USD per 1M input tokens
    output_price_per_m: float  # USD per 1M output tokens
    display_name: str = ""

    def __post_init__(self):
        if not self.display_name:
            object.__setattr__(self, "display_name", self.model_id)


MODEL_MATRIX: list[ModelConfig] = [
    # Anthropic
    ModelConfig(
        model_id="claude-opus-4-6-20250514",
        provider="anthropic",
        tier="premium",
        input_price_per_m=15.0,
        output_price_per_m=75.0,
        display_name="Claude Opus 4.6",
    ),
    ModelConfig(
        model_id="claude-sonnet-4-6-20250514",
        provider="anthropic",
        tier="mid",
        input_price_per_m=3.0,
        output_price_per_m=15.0,
        display_name="Claude Sonnet 4.6",
    ),
    ModelConfig(
        model_id="claude-haiku-4-5-20251001",
        provider="anthropic",
        tier="value",
        input_price_per_m=0.80,
        output_price_per_m=4.0,
        display_name="Claude Haiku 4.5",
    ),
    # OpenAI
    ModelConfig(
        model_id="gpt-4o",
        provider="openai",
        tier="mid",
        input_price_per_m=2.50,
        output_price_per_m=10.0,
        display_name="GPT-4o",
    ),
    ModelConfig(
        model_id="gpt-4o-mini",
        provider="openai",
        tier="value",
        input_price_per_m=0.15,
        output_price_per_m=0.60,
        display_name="GPT-4o mini",
    ),
    # Open-weight via OpenRouter
    ModelConfig(
        model_id="deepseek/deepseek-chat",
        provider="openrouter",
        tier="value",
        input_price_per_m=0.27,
        output_price_per_m=1.10,
        display_name="DeepSeek V3",
    ),
]

MODEL_LOOKUP: dict[str, ModelConfig] = {m.model_id: m for m in MODEL_MATRIX}

# Run order: cheapest first so failures are cheap
RUN_ORDER = [m.model_id for m in sorted(MODEL_MATRIX, key=lambda m: m.output_price_per_m)]

# ---------------------------------------------------------------------------
# Provider configs (rate limits, retries)
# ---------------------------------------------------------------------------

@dataclass
class ProviderConfig:
    delay_between_runs: float  # seconds between benchmark runs
    delay_between_calls: float  # seconds between individual API calls
    max_retries: int
    retry_backoff_base: float  # exponential backoff base (seconds)


PROVIDER_CONFIGS: dict[str, ProviderConfig] = {
    "anthropic": ProviderConfig(
        delay_between_runs=5.0,
        delay_between_calls=0.5,
        max_retries=3,
        retry_backoff_base=2.0,
    ),
    "openai": ProviderConfig(
        delay_between_runs=3.0,
        delay_between_calls=0.3,
        max_retries=3,
        retry_backoff_base=1.5,
    ),
    "openrouter": ProviderConfig(
        delay_between_runs=10.0,
        delay_between_calls=1.0,
        max_retries=5,
        retry_backoff_base=3.0,
    ),
}


def with_retry(func, provider: str, *args, **kwargs):
    """Execute with exponential backoff retry on rate limits."""
    config = PROVIDER_CONFIGS[provider]
    last_error = None

    for attempt in range(config.max_retries):
        try:
            result = func(*args, **kwargs)
            time.sleep(config.delay_between_calls)
            return result
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            if "rate_limit" in error_str or "429" in error_str:
                wait = config.retry_backoff_base ** (attempt + 1)
                print(f"  Rate limited ({provider}), waiting {wait:.1f}s...")
                time.sleep(wait)
            else:
                raise

    raise last_error  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Langfuse
# ---------------------------------------------------------------------------

LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "")
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")

# Budget ceiling for the entire benchmark suite (USD)
MAX_BUDGET_USD = 75.0

# Benchmark settings
TEMPERATURE = 0.0
RUNS_PER_MODEL = 3
MAX_GOAL_TURNS = 30
MAX_GOAL_BUDGET_PER_RUN = 10.0
