"""Batch automation: every row of a CSV, from image URL to Merchant Center.

Runs the single-garment pipeline (pipeline.run_pipeline) once per row:

    CSV (image URL + brand data per row)
       │  read and check the columns      read_rows
       ▼
    per row: check the brand data, attribute, validate, upload
       │                                  run_batch
       ▼
    wait for Google's verdict on every uploaded product
                                          wait_for_statuses

A row that fails does not stop the others: its result says at which stage it
ended and why. Only a credentials error stops the batch, since it would fail
every remaining row the same way.
"""
from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Union

from positioner.automation.pipeline import (
    INVALID,
    EnrichFn,
    PipelineResult,
    product_id_from_url,
    run_pipeline,
)
from positioner.feed.schema_mapper import REQUIRED_BUSINESS_FIELDS
from positioner.publishing.credential_loader import CredentialError
from positioner.publishing.merchant_client import MerchantClient, ProductStatus

# Stage of a row that raised an unexpected error (a model or the LLM API).
ERROR = 'error'

# Column with the photo URL: the synthetic feeds call it image_url.
URL_COLUMNS = ('image_url', 'url')

# Brand-declared columns read from the CSV. Any other column (title,
# description, google_product_category, ...) is ignored: the pipeline
# generates those from the photo.
BRAND_COLUMNS = (
    'brand', 'price', 'link', 'size', 'gender', 'color', 'material',
    'pattern', 'gtin', 'availability', 'condition', 'age_group',
)

# Used when the row leaves them empty; same defaults as publish_from_url.py.
DEFAULTS = {'availability': 'in_stock', 'condition': 'new', 'age_group': 'adult'}

# Required by the validator for apparel and never inferred from the photo.
# Checked before attributing, so a row without them costs no model or LLM call.
DECLARED_ONLY = ('size', 'gender')

# Columns the CSV must have. availability and condition have defaults.
REQUIRED_COLUMNS = ('brand', 'price', 'link', *DECLARED_ONLY)


@dataclass
class BatchRow:
    """One garment read from the CSV."""
    product_id: str
    image_url: str
    business: dict


def read_rows(path: Union[str, Path]) -> List[BatchRow]:
    """Read the garments of a CSV, one per row.

    The CSV needs a photo URL column ('image_url' or 'url') and the columns
    in REQUIRED_COLUMNS. 'id' is optional: when the cell is empty the ID is
    derived from the URL, so re-running the CSV updates the same products.

    Raises:
        ValueError: if a column is missing, a row has no URL, or two rows
                    share a product ID. Checked before any work starts.
    """
    with open(path, newline='', encoding='utf-8-sig') as file:
        reader = csv.DictReader(file)
        columns = set(reader.fieldnames or [])
        url_column = next((c for c in URL_COLUMNS if c in columns), None)
        if url_column is None:
            raise ValueError(f"{path}: no photo URL column ('image_url' or 'url')")
        missing = [c for c in REQUIRED_COLUMNS if c not in columns]
        if missing:
            raise ValueError(f"{path}: missing columns: {', '.join(missing)}")

        rows: List[BatchRow] = []
        seen: Dict[str, int] = {}
        # Line 1 is the header.
        for line, record in enumerate(reader, start=2):
            image_url = (record.get(url_column) or '').strip()
            if not image_url:
                raise ValueError(f'{path}, line {line}: empty photo URL')
            product_id = (record.get('id') or '').strip() or product_id_from_url(image_url)
            if product_id in seen:
                raise ValueError(
                    f'{path}, line {line}: product ID {product_id} '
                    f'already used on line {seen[product_id]}'
                )
            seen[product_id] = line
            business = dict(DEFAULTS)
            for column in BRAND_COLUMNS:
                value = (record.get(column) or '').strip()
                if value:
                    business[column] = value
            rows.append(BatchRow(product_id, image_url, business))
    return rows


def run_batch(
    rows: Sequence[BatchRow],
    client: Optional[MerchantClient] = None,
    dry_run: bool = False,
    enrich: Optional[EnrichFn] = None,
    on_result: Optional[Callable[[int, PipelineResult], None]] = None,
) -> List[PipelineResult]:
    """Run the pipeline on every row and return one result per row, in order.

    Args:
        rows:      output of read_rows.
        client:    Merchant Center client. Required unless dry_run is True.
        dry_run:   build and validate every product without uploading it.
        enrich:    M1 function; defaults to enrich_product.
        on_result: called with (index, result) after each row, to report
                   progress.

    Raises:
        CredentialError: if the Merchant credentials are not configured.
    """
    results: List[PipelineResult] = []
    for index, row in enumerate(rows):
        result = _run_row(row, client, dry_run, enrich)
        results.append(result)
        if on_result is not None:
            on_result(index, result)
    return results


def _run_row(
    row: BatchRow,
    client: Optional[MerchantClient],
    dry_run: bool,
    enrich: Optional[EnrichFn],
) -> PipelineResult:
    missing = [
        f'missing_{name}' for name in (*REQUIRED_BUSINESS_FIELDS, *DECLARED_ONLY)
        if not row.business.get(name)
    ]
    if missing:
        return PipelineResult(row.product_id, row.image_url, INVALID, reasons=missing)
    try:
        return run_pipeline(
            row.image_url, row.business,
            client=client, product_id=row.product_id, dry_run=dry_run, enrich=enrich,
        )
    except CredentialError:
        raise
    except Exception as error:
        return PipelineResult(row.product_id, row.image_url, ERROR, reasons=[str(error)])


def wait_for_statuses(
    client: MerchantClient,
    product_ids: Sequence[str],
    timeout_s: float = 300,
    interval_s: float = 15,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Dict[str, ProductStatus]:
    """Poll Merchant Center until no product is 'pending', or time runs out.

    Each round asks only for the products still pending.

    Returns:
        The last status read for each product ID.
    """
    deadline = clock() + timeout_s
    statuses: Dict[str, ProductStatus] = {}
    pending = list(product_ids)
    while pending:
        for product_id, status in zip(pending, client.get_product_statuses(pending)):
            statuses[product_id] = status
        pending = [pid for pid in pending if statuses[pid].status == 'pending']
        if not pending or clock() + interval_s > deadline:
            break
        sleep(interval_s)
    return statuses
