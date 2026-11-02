"""Load Google Merchant credentials from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from google.oauth2 import service_account

# OAuth scope required by the Merchant API.
MERCHANT_SCOPE = 'https://www.googleapis.com/auth/content'


class CredentialError(Exception):
    """Raised when required credential env vars are missing."""


@dataclass
class Credentials:
    """Google Merchant Center credentials loaded from environment."""
    service_account_path: str
    merchant_id: str
    # API data source that receives uploads; only needed to upload products.
    data_source_id: Optional[str] = None


def load_credentials() -> Credentials:
    """Load credentials from environment variables.

    Reads GOOGLE_SERVICE_ACCOUNT_PATH and MERCHANT_ID (required) and
    MERCHANT_DATA_SOURCE_ID (optional — uploads fail without it, status
    readback does not need it).
    Raises CredentialError on the first missing required variable.
    Makes NO Google auth calls — only loads and validates the config.

    Returns:
        Credentials dataclass populated from env vars.

    Raises:
        CredentialError: if GOOGLE_SERVICE_ACCOUNT_PATH or MERCHANT_ID is unset.
    """
    values: dict[str, str] = {}
    for var_name in ('GOOGLE_SERVICE_ACCOUNT_PATH', 'MERCHANT_ID'):
        value = os.environ.get(var_name)
        if not value:
            raise CredentialError(f"Missing env var: {var_name}")
        values[var_name] = value

    return Credentials(
        service_account_path=values['GOOGLE_SERVICE_ACCOUNT_PATH'],
        merchant_id=values['MERCHANT_ID'],
        data_source_id=os.environ.get('MERCHANT_DATA_SOURCE_ID') or None,
    )


def build_google_credentials(credentials: Credentials) -> service_account.Credentials:
    """Build Google auth credentials from the service-account key file.

    Reads the key file from disk; makes NO network calls (the token is
    fetched by the API client on its first request).

    Args:
        credentials: loaded service-account path and merchant ID.

    Returns:
        google.oauth2 service-account credentials scoped for the Merchant API.

    Raises:
        CredentialError: if the key file is missing or is not a valid key.
    """
    try:
        return service_account.Credentials.from_service_account_file(
            credentials.service_account_path,
            scopes=[MERCHANT_SCOPE],
        )
    except (OSError, ValueError) as exc:
        raise CredentialError(
            f"Cannot load service-account key from "
            f"{credentials.service_account_path}: {exc}"
        ) from exc
