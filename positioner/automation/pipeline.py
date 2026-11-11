"""End-to-end automation: from an image URL to a product in Merchant Center.

Chains the first three milestones for a single garment:

    image URL + brand data
       │  check the brand data           (M2 validate_business_fields)
       ▼
    download + attribute the image       (M1 enrich_product)
       ▼
    map + validate the Merchant row      (M2 map_to_merchant, validate_row)
       ▼
    upload to Merchant Center            (M3 MerchantClient.upload_feed)
       ▼
    wait for Google's verdict            (M3 MerchantClient.get_product_statuses)

The pipeline stops at the first stage that fails and says which one, so
nothing incomplete reaches Google.

M1 needs the deep-tagger-api models, so enrich_product is imported only when
the caller does not pass its own `enrich` function. Tests pass a fake one.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from positioner.enrichment.models import EnrichedProduct
from positioner.feed.report import build_report
from positioner.feed.schema_mapper import (
    MerchantProduct,
    map_to_merchant,
    validate_business_fields,
)
from positioner.feed.validator import ValidationResult, validate_row
from positioner.publishing.merchant_client import (
    MerchantClient,
    ProductStatus,
    UploadResult,
)

EnrichFn = Callable[[dict], EnrichedProduct]

# Stages where a run can end.
DOWNLOAD_FAILED = 'download_failed'
INVALID = 'invalid'
DRY_RUN = 'dry_run'
UPLOADED = 'uploaded'
UPLOAD_FAILED = 'upload_failed'


@dataclass
class PipelineResult:
    """What happened to one garment, stage by stage.

    stage is where the run ended: 'download_failed', 'invalid', 'dry_run',
    'uploaded' or 'upload_failed'. Fields of later stages stay None.
    """
    product_id: str
    image_url: str
    stage: str
    enriched: Optional[EnrichedProduct] = None
    product: Optional[MerchantProduct] = None
    validation: Optional[ValidationResult] = None
    upload: Optional[UploadResult] = None
    reasons: List[str] = field(default_factory=list)


def product_id_from_url(image_url: str) -> str:
    """Derive a stable offer ID from the image URL.

    The same URL always gives the same ID, so running the pipeline twice on
    one image updates the product in Merchant Center instead of duplicating it.
    """
    digest = hashlib.sha1(image_url.strip().encode('utf-8')).hexdigest()[:12]
    return f'url-{digest}'


def run_pipeline(
    image_url: str,
    business: dict,
    client: Optional[MerchantClient] = None,
    product_id: Optional[str] = None,
    dry_run: bool = False,
    enrich: Optional[EnrichFn] = None,
) -> PipelineResult:
    """Download, attribute and upload one garment.

    Args:
        image_url:  public URL of the garment photo.
        business:   fields declared by the brand (price, brand, link,
                    availability, condition, size, gender, ...). Any
                    'image_url' key in it is ignored in favor of image_url.
        client:     Merchant Center client. Required unless dry_run is True.
        product_id: offer ID; derived from the URL when None.
        dry_run:    build and validate the product without uploading it.
        enrich:     M1 function; defaults to enrich_product.

    Returns:
        PipelineResult saying where the run ended and why.

    Raises:
        ValueError: if a required brand field is missing (before downloading
                    anything), or if client is None and dry_run is False.
        CredentialError: if the Merchant credentials are not configured.
    """
    if client is None and not dry_run:
        raise ValueError('A MerchantClient is required unless dry_run is True')

    # 1. Brand data first: it is free to check and the download is not.
    validate_business_fields(business)

    if enrich is None:
        from positioner.enrichment.field_generator import enrich_product
        enrich = enrich_product

    row = {**business, 'image_url': image_url}
    product_id = product_id or product_id_from_url(image_url)
    result = PipelineResult(product_id=product_id, image_url=image_url, stage='')

    # 2. Download and attribute the image.
    result.enriched = enrich(row)
    if result.enriched.status == 'partial':
        result.stage = DOWNLOAD_FAILED
        result.reasons = [f'could not download the image at {image_url}']
        return result

    # 3. Build the Merchant Center row and validate it.
    result.product = map_to_merchant(result.enriched, row, row_id=product_id)
    result.validation = validate_row(result.product)
    if not result.validation.valid:
        result.stage = INVALID
        result.reasons = list(result.validation.reasons)
        return result

    if dry_run:
        result.stage = DRY_RUN
        return result

    # 4. Upload. upload_feed returns one result per valid product: here, one.
    report = build_report([result.validation])
    result.upload = client.upload_feed(report, [result.product])[0]
    if result.upload.success:
        result.stage = UPLOADED
    else:
        result.stage = UPLOAD_FAILED
        result.reasons = [result.upload.error or 'unknown upload error']
    return result


def wait_for_status(
    client: MerchantClient,
    product_id: str,
    timeout_s: float = 300,
    interval_s: float = 15,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> ProductStatus:
    """Poll Merchant Center until Google approves or disapproves the product.

    Google takes from 30 seconds to a few minutes to process a new product,
    and reports it as 'pending' meanwhile.

    Returns:
        The first status that is not 'pending', or the last 'pending' one
        when timeout_s runs out.
    """
    deadline = clock() + timeout_s
    while True:
        status = client.get_product_statuses([product_id])[0]
        if status.status != 'pending' or clock() + interval_s > deadline:
            return status
        sleep(interval_s)
