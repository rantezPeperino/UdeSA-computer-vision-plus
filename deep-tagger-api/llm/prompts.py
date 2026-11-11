"""Prompt shared by every LLM client, so Claude and OpenAI get the same request."""

FALLBACK_DESCRIPTION = "Lorem ipsum dolor sit amet."


def build_description_prompt(product_type: str, title: str, tags: dict) -> str:
  tags_text = ", ".join(f"{k}: {v}" for k, v in tags.items())
  return (
    f"Generate a short, compelling product description for an e-commerce listing.\n"
    f"Product type: {product_type}\n"
    f"Title: {title}\n"
    f"Tags: {tags_text}\n"
    f"Write only the description, 2-3 sentences max."
  )
