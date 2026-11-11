import os
import anthropic

from llm.prompts import FALLBACK_DESCRIPTION, build_description_prompt

_api_key = os.environ.get("ANTHROPIC_API_KEY")
_client = anthropic.Anthropic(api_key=_api_key) if _api_key else None


def generate_product_description(product_type: str, title: str, tags: dict) -> str:
  if not _client:
    return FALLBACK_DESCRIPTION

  message = _client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=256,
    messages=[{"role": "user", "content": build_description_prompt(product_type, title, tags)}],
  )
  return message.content[0].text
