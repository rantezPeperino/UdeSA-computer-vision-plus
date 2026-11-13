"""Setup shared by the command-line scripts: the LLM key and Merchant Center.

Imports `llm` from deep-tagger-api, so the caller must have added that
directory to sys.path.
"""
from __future__ import annotations

from typing import Optional

from positioner.publishing.credential_loader import CredentialError, load_credentials
from positioner.publishing.environment import get_environment
from positioner.publishing.merchant_client import MerchantClient


class SetupError(Exception):
    """Something the run needs is not configured; the message says what."""


def connect(dry_run: bool) -> Optional[MerchantClient]:
    """Check the LLM key and build the Merchant client, printing what is used.

    On a dry run nothing is uploaded, so nothing is checked and it returns None.

    Raises:
        SetupError: if the LLM key or the Merchant credentials are missing.
    """
    if dry_run:
        return None

    from llm import description_client  # from deep-tagger-api
    try:
        provider = description_client.provider()
    except ValueError as error:
        raise SetupError(f'LLM_PROVIDER: {error}') from error
    if provider is None:
        raise SetupError(
            'Missing the language model key (OPENAI_API_KEY or ANTHROPIC_API_KEY, '
            'the one matching LLM_PROVIDER if it is set): without it the description '
            'is placeholder text and would be uploaded as such to Merchant Center. '
            'Set it or run with --dry-run.'
        )
    print(f'Description generated with: {provider}')

    try:
        credentials = load_credentials()
    except CredentialError as error:
        raise SetupError(
            f'Merchant Center credentials: {error} (see upgrade/MERCHANT_SETUP.md)'
        ) from error
    environment = get_environment()
    print(f'Merchant Center: account {credentials.merchant_id}, environment {environment.value}')
    return MerchantClient(credentials, environment)
