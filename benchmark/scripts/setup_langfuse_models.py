"""One-time setup: configure model pricing in Langfuse for all benchmark models."""

from __future__ import annotations

import base64
import os

import requests
from dotenv import load_dotenv

load_dotenv()

LANGFUSE_HOST = os.environ["LANGFUSE_HOST"]
PUBLIC_KEY = os.environ["LANGFUSE_PUBLIC_KEY"]
SECRET_KEY = os.environ["LANGFUSE_SECRET_KEY"]

auth = base64.b64encode(f"{PUBLIC_KEY}:{SECRET_KEY}".encode()).decode()
headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}

MODELS = [
    {
        "modelName": "claude-opus-4-6-20250514",
        "matchPattern": "(?i)^(claude-opus-4-6.*)$",
        "unit": "TOKENS",
        "pricingTiers": [{
            "name": "Standard",
            "isDefault": True,
            "priority": 0,
            "conditions": [],
            "prices": {
                "input": 0.000015,
                "output": 0.000075,
                "cache_read_input_tokens": 0.0000075,
                "cache_creation_input_tokens": 0.00001875,
            },
        }],
    },
    {
        "modelName": "claude-sonnet-4-6-20250514",
        "matchPattern": "(?i)^(claude-sonnet-4-6.*)$",
        "unit": "TOKENS",
        "pricingTiers": [{
            "name": "Standard",
            "isDefault": True,
            "priority": 0,
            "conditions": [],
            "prices": {
                "input": 0.000003,
                "output": 0.000015,
                "cache_read_input_tokens": 0.0000015,
                "cache_creation_input_tokens": 0.00000375,
            },
        }],
    },
    {
        "modelName": "claude-haiku-4-5-20251001",
        "matchPattern": "(?i)^(claude-haiku-4-5.*)$",
        "unit": "TOKENS",
        "pricingTiers": [{
            "name": "Standard",
            "isDefault": True,
            "priority": 0,
            "conditions": [],
            "prices": {
                "input": 0.0000008,
                "output": 0.000004,
                "cache_read_input_tokens": 0.0000004,
                "cache_creation_input_tokens": 0.000001,
            },
        }],
    },
    {
        "modelName": "gpt-4o",
        "matchPattern": "(?i)^(gpt-4o)$",
        "unit": "TOKENS",
        "inputPrice": 0.0000025,
        "outputPrice": 0.000010,
    },
    {
        "modelName": "gpt-4o-mini",
        "matchPattern": "(?i)^(gpt-4o-mini)$",
        "unit": "TOKENS",
        "inputPrice": 0.00000015,
        "outputPrice": 0.0000006,
    },
    {
        "modelName": "deepseek/deepseek-chat",
        "matchPattern": "(?i)^(deepseek/deepseek-chat)$",
        "unit": "TOKENS",
        "inputPrice": 0.00000027,
        "outputPrice": 0.0000011,
    },
]


def main():
    print(f"Configuring model pricing on {LANGFUSE_HOST}...\n")
    for model in MODELS:
        resp = requests.post(
            f"{LANGFUSE_HOST}/api/public/models",
            headers=headers,
            json=model,
            timeout=10,
        )
        status = "OK" if resp.status_code in (200, 201) else f"FAILED ({resp.status_code}: {resp.text[:100]})"
        print(f"  {model['modelName']}: {status}")

    print("\nDone. Verify at: {LANGFUSE_HOST}/project/settings/models")


if __name__ == "__main__":
    main()
