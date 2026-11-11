"""Generates the product description with Claude or OpenAI, chosen from the environment.

Which provider runs:
  - LLM_PROVIDER=anthropic or LLM_PROVIDER=openai picks one explicitly.
  - Otherwise, the first one with an API key: ANTHROPIC_API_KEY, then OPENAI_API_KEY.
  - With no key, a placeholder description is returned, as before.
"""
import os

from llm import claude_client, openai_client
from llm.prompts import FALLBACK_DESCRIPTION

_CLIENTS = {"anthropic": claude_client, "openai": openai_client}
_KEYS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


def provider() -> str | None:
  """Return the provider that will generate descriptions, or None if no key is set.

  Raises:
    ValueError: if LLM_PROVIDER names an unknown provider.
  """
  chosen = os.environ.get("LLM_PROVIDER", "").strip().lower()
  if chosen:
    if chosen not in _CLIENTS:
      raise ValueError(f"Unknown LLM_PROVIDER '{chosen}': use one of {sorted(_CLIENTS)}")
    return chosen if os.environ.get(_KEYS[chosen]) else None
  return next((name for name, key in _KEYS.items() if os.environ.get(key)), None)


def generate_product_description(product_type: str, title: str, tags: dict) -> str:
  name = provider()
  if name is None:
    return FALLBACK_DESCRIPTION
  return _CLIENTS[name].generate_product_description(product_type=product_type, title=title, tags=tags)
