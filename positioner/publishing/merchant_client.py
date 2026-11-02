"""Merchant Center client: upload feed and read back product statuses."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from google.api_core import exceptions as google_exceptions
from google.shopping import merchant_products_v1 as merchant
from google.shopping.type import Price

from positioner.feed.report import ValidationReport
from positioner.feed.schema_mapper import MerchantProduct
from positioner.publishing.credential_loader import (
    CredentialError,
    Credentials,
    build_google_credentials,
)
from positioner.publishing.environment import Environment


@dataclass
class UploadResult:
    """Outcome of uploading a single product."""
    product_id: str
    success: bool
    error: Optional[str] = None


@dataclass
class ProductStatus:
    """Approval/disapproval status for a single product."""
    product_id: str
    status: str
    issues: List[str] = field(default_factory=list)


class MerchantClient:
    """Orchestrates feed upload and status readback against Merchant Center."""

    def __init__(
        self,
        credentials: Credentials,
        environment: Environment,
        content_language: str = 'en',
        feed_label: str = 'US',
    ) -> None:
        """Store config. Makes NO network calls.

        Args:
            credentials:      loaded service-account path and merchant ID.
            environment:      TEST or PRODUCTION.
            content_language: ISO 639-1 language of titles/descriptions.
            feed_label:       Merchant Center feed label (usually the target country).
        """
        self.credentials = credentials
        self.environment = environment
        self.content_language = content_language
        self.feed_label = feed_label
        # API clients are built on first use so the constructor never reads the key file.
        self._inputs_client: Optional[merchant.ProductInputsServiceClient] = None
        self._products_client: Optional[merchant.ProductsServiceClient] = None

    def upload_feed(
        self,
        report: ValidationReport,
        products: List[MerchantProduct],
    ) -> List[UploadResult]:
        """Upload only valid products from the feed.

        Valid-vs-invalid matching rule:
            invalid_ids = {r.row_id for r in report.invalid_rows}
            A product is uploaded when product.id NOT IN invalid_ids.

        Continues on partial failure; returns a per-product UploadResult list
        covering only the valid products.  A CredentialError aborts the whole
        upload, since it would fail every product the same way.

        Args:
            report:   ValidationReport produced by build_report().
            products: all MerchantProduct objects corresponding to the report.

        Returns:
            List[UploadResult] — one entry per valid product attempted.

        Raises:
            CredentialError: if the key file or data source is not configured.
        """
        invalid_ids = {r.row_id for r in report.invalid_rows}
        valid_products = [p for p in products if p.id not in invalid_ids]

        results: List[UploadResult] = []
        for product in valid_products:
            try:
                result = self._upload_product(product)
                results.append(result)
            except CredentialError:
                raise
            except Exception as exc:
                results.append(
                    UploadResult(
                        product_id=product.id,
                        success=False,
                        error=str(exc),
                    )
                )
        return results

    def get_product_statuses(self, product_ids: List[str]) -> List[ProductStatus]:
        """Read back approval/disapproval status for each product.

        Args:
            product_ids: list of product IDs to query.

        Returns:
            List[ProductStatus] — one entry per product ID, in input order.
        """
        statuses: List[ProductStatus] = []
        for pid in product_ids:
            status = self._get_status(pid)
            statuses.append(status)
        return statuses

    def _upload_product(self, product: MerchantProduct) -> UploadResult:
        """Insert one product into the configured API data source.

        Args:
            product: a MerchantProduct that passed M2 validation.

        Returns:
            UploadResult with success=True when the API accepted the input.

        Raises:
            CredentialError: if MERCHANT_DATA_SOURCE_ID or the key file is missing.
            ValueError: if a field cannot be converted to the Merchant API format.
            google.api_core.exceptions.GoogleAPICallError: if the API rejects it.
        """
        if not self.credentials.data_source_id:
            raise CredentialError("Missing env var: MERCHANT_DATA_SOURCE_ID")

        account = f"accounts/{self.credentials.merchant_id}"
        request = merchant.InsertProductInputRequest(
            parent=account,
            data_source=f"{account}/dataSources/{self.credentials.data_source_id}",
            product_input=self._to_product_input(product),
        )
        self._get_inputs_client().insert_product_input(request=request)
        return UploadResult(product_id=product.id, success=True)

    def _get_status(self, product_id: str) -> ProductStatus:
        """Read one product's processed status from Merchant Center.

        Merchant Center processes inputs asynchronously, so a product that was
        just uploaded can be missing for a few minutes; it is reported as pending.

        Args:
            product_id: the offer ID used at upload time (MerchantProduct.id).

        Returns:
            ProductStatus with status 'approved', 'disapproved' or 'pending'.
        """
        name = merchant.ProductsServiceClient.product_path(
            self.credentials.merchant_id,
            f"{self.content_language}~{self.feed_label}~{product_id}",
        )
        try:
            product = self._get_products_client().get_product(name=name)
        except google_exceptions.NotFound:
            return ProductStatus(
                product_id=product_id,
                status='pending',
                issues=['not found: not uploaded yet, or still being processed'],
            )
        return _to_product_status(product_id, product.product_status)

    # ── Merchant API clients ──────────────────────────────────────────────────

    def _get_inputs_client(self) -> merchant.ProductInputsServiceClient:
        if self._inputs_client is None:
            self._inputs_client = merchant.ProductInputsServiceClient(
                credentials=build_google_credentials(self.credentials),
            )
        return self._inputs_client

    def _get_products_client(self) -> merchant.ProductsServiceClient:
        if self._products_client is None:
            self._products_client = merchant.ProductsServiceClient(
                credentials=build_google_credentials(self.credentials),
            )
        return self._products_client

    # ── MerchantProduct → Merchant API ────────────────────────────────────────

    def _to_product_input(self, product: MerchantProduct) -> merchant.ProductInput:
        """Convert a MerchantProduct into a Merchant API ProductInput.

        Raises:
            ValueError: if price or an enum field (availability, condition,
                        gender, age_group) has a value the API does not accept.
        """
        attributes = {
            'title': product.title,
            'description': product.description,
            'link': product.link,
            'image_link': product.image_link,
            'brand': product.brand,
            'google_product_category': product.google_product_category,
            'color': product.color,
            'size': product.size,
            'material': product.material,
            'pattern': product.pattern,
        }
        # Proto fields cannot be set to None: send only what the product has.
        attributes = {k: v for k, v in attributes.items() if v}

        if product.gtin:
            attributes['gtins'] = [product.gtin]
        if product.price:
            attributes['price'] = _parse_price(product.price)
        if product.availability:
            attributes['availability'] = _to_enum(merchant.Availability, product.availability)
        if product.condition:
            attributes['condition'] = _to_enum(merchant.Condition, product.condition)
        if product.gender:
            attributes['gender'] = _to_enum(merchant.Gender, product.gender)
        if product.age_group:
            attributes['age_group'] = _to_enum(merchant.AgeGroup, product.age_group)

        return merchant.ProductInput(
            offer_id=product.id,
            content_language=self.content_language,
            feed_label=self.feed_label,
            product_attributes=merchant.ProductAttributes(**attributes),
        )


def _parse_price(price: str) -> Price:
    """Convert a feed price like '25.32 USD' into a Merchant API Price.

    Raises:
        ValueError: if the price is not '<amount> <currency>'.
    """
    try:
        amount, currency = price.split()
        micros = int(Decimal(amount) * 1_000_000)
    except (ValueError, InvalidOperation) as exc:
        raise ValueError(f"Invalid price '{price}'") from exc
    return Price(amount_micros=micros, currency_code=currency)


def _to_enum(enum_type, value: str):
    """Map a feed value like 'in_stock' or 'in stock' to its Merchant API enum.

    Raises:
        ValueError: if the value is not a member of enum_type.
    """
    key = value.strip().upper().replace(' ', '_')
    try:
        return enum_type[key]
    except KeyError:
        raise ValueError(
            f"Invalid {enum_type.__name__} '{value}'"
        ) from None


def _to_product_status(product_id: str, status: merchant.ProductStatus) -> ProductStatus:
    """Collapse the per-destination statuses into a single status string.

    A product disapproved in any destination counts as 'disapproved', so a
    partial approval is never hidden; otherwise any approval counts as
    'approved', and the rest is 'pending'.
    """
    disapproved = any(d.disapproved_countries for d in status.destination_statuses)
    approved = any(d.approved_countries for d in status.destination_statuses)
    if disapproved:
        summary = 'disapproved'
    elif approved:
        summary = 'approved'
    else:
        summary = 'pending'

    issues = [
        f"{issue.code}: {issue.description}"
        + (f" ({issue.attribute})" if issue.attribute else '')
        for issue in status.item_level_issues
    ]
    return ProductStatus(product_id=product_id, status=summary, issues=issues)
