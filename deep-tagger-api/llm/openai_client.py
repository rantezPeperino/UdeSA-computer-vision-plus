import os
from openai import OpenAI

from llm.prompts import FALLBACK_DESCRIPTION, build_description_prompt

# Overridable with OPENAI_MODEL, in case this one is retired or another is preferred.
DEFAULT_MODEL = "gpt-5-mini"

_api_key = os.environ.get("OPENAI_API_KEY")
_client = OpenAI(api_key=_api_key) if _api_key else None


def generate_product_description(product_type: str, title: str, tags: dict) -> str:
  if not _client:
    return FALLBACK_DESCRIPTION

  response = _client.responses.create(
    model=os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL,
    input=build_description_prompt(product_type, title, tags),
  )
  return response.output_text.strip()
