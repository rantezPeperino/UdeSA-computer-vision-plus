"""Tests for the choice between Claude and OpenAI in llm/description_client.py.

The anthropic and openai libraries are replaced with mocks before importing the
clients, so these tests need no API key and make no network call:

    python -m unittest discover -s deep-tagger-api/tests
"""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.modules.setdefault("anthropic", MagicMock())
sys.modules.setdefault("openai", MagicMock())

from llm import description_client, openai_client  # noqa: E402
from llm.prompts import FALLBACK_DESCRIPTION  # noqa: E402

ARGS = dict(product_type="Pants", title="StyleCo Pants black M", tags={"color": "black"})


class ProviderTests(unittest.TestCase):

  def test_openai_key_alone_selects_openai(self):
    with patch.dict(os.environ, {"OPENAI_API_KEY": "x"}, clear=True):
      self.assertEqual(description_client.provider(), "openai")

  def test_anthropic_wins_when_both_keys_are_set(self):
    with patch.dict(os.environ, {"OPENAI_API_KEY": "x", "ANTHROPIC_API_KEY": "y"}, clear=True):
      self.assertEqual(description_client.provider(), "anthropic")

  def test_llm_provider_overrides_the_default(self):
    env = {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "x", "ANTHROPIC_API_KEY": "y"}
    with patch.dict(os.environ, env, clear=True):
      self.assertEqual(description_client.provider(), "openai")

  def test_llm_provider_without_its_key_gives_none(self):
    with patch.dict(os.environ, {"LLM_PROVIDER": "openai", "ANTHROPIC_API_KEY": "y"}, clear=True):
      self.assertIsNone(description_client.provider())

  def test_unknown_llm_provider_fails(self):
    with patch.dict(os.environ, {"LLM_PROVIDER": "gemini"}, clear=True):
      with self.assertRaises(ValueError):
        description_client.provider()

  def test_no_key_returns_placeholder(self):
    with patch.dict(os.environ, {}, clear=True):
      self.assertEqual(description_client.generate_product_description(**ARGS), FALLBACK_DESCRIPTION)

  def test_openai_selected_calls_openai_client(self):
    with patch.dict(os.environ, {"OPENAI_API_KEY": "x"}, clear=True), \
        patch.object(openai_client, "generate_product_description", return_value="Pantalón negro.") as gen:
      self.assertEqual(description_client.generate_product_description(**ARGS), "Pantalón negro.")
    gen.assert_called_once_with(**ARGS)


class OpenAIClientTests(unittest.TestCase):

  def test_openai_client_sends_prompt_and_returns_text(self):
    client = MagicMock()
    client.responses.create.return_value.output_text = "  Pantalón negro.\n"
    with patch.object(openai_client, "_client", client), \
        patch.dict(os.environ, {"OPENAI_MODEL": "gpt-test"}, clear=True):
      text = openai_client.generate_product_description(**ARGS)

    self.assertEqual(text, "Pantalón negro.")
    kwargs = client.responses.create.call_args.kwargs
    self.assertEqual(kwargs["model"], "gpt-test")
    self.assertIn("Title: StyleCo Pants black M", kwargs["input"])

  def test_openai_client_without_key_returns_placeholder(self):
    with patch.object(openai_client, "_client", None):
      self.assertEqual(openai_client.generate_product_description(**ARGS), FALLBACK_DESCRIPTION)


if __name__ == "__main__":
  unittest.main()
