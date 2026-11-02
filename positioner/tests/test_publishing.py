"""Tests for positioner.publishing (Milestone 3 — Merchant Publishing).

All network and credential calls are mocked at the method level.
No real Google auth, no real env vars, no real network.

Run: python -m unittest positioner.tests.test_publishing -v
     (from workspace root c:\\Users\\u645020\\Documents\\MIA\\UdeSA-computer-vision-plus)
"""

# ── 1. sys.path: make positioner importable from workspace root ───────────────
import sys
import os

_WS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _WS_ROOT not in sys.path:
    sys.path.insert(0, _WS_ROOT)

# ── 2. imports ────────────────────────────────────────────────────────────────
import unittest  # noqa: E402
from unittest.mock import patch, MagicMock  # noqa: E402

from google.api_core import exceptions as google_exceptions  # noqa: E402
from google.shopping import merchant_products_v1 as merchant  # noqa: E402

from positioner.publishing.environment import Environment, get_environment  # noqa: E402
from positioner.publishing.credential_loader import (  # noqa: E402
    Credentials,
    CredentialError,
    load_credentials,
)
from positioner.publishing.merchant_client import (  # noqa: E402
    MerchantClient,
    UploadResult,
    ProductStatus,
)
from positioner.feed.schema_mapper import MerchantProduct  # noqa: E402
from positioner.feed.validator import ValidationResult  # noqa: E402
from positioner.feed.report import build_report  # noqa: E402


# ── 3. Test class ─────────────────────────────────────────────────────────────
class PublishingTests(unittest.TestCase):

    # ------------------------------------------------------------------ #
    #  test_credentials_load_from_env                                     #
    # ------------------------------------------------------------------ #
    def test_credentials_load_from_env(self) -> None:
        """Credentials are populated from GOOGLE_SERVICE_ACCOUNT_PATH and MERCHANT_ID."""
        with patch.dict(os.environ, {
            'GOOGLE_SERVICE_ACCOUNT_PATH': '/fake/service_account.json',
            'MERCHANT_ID': 'test-merchant-42',
        }):
            creds = load_credentials()

        self.assertEqual(creds.service_account_path, '/fake/service_account.json')
        self.assertEqual(creds.merchant_id, 'test-merchant-42')

    # ------------------------------------------------------------------ #
    #  test_credentials_missing_fails_fast                                #
    # ------------------------------------------------------------------ #
    def test_credentials_missing_fails_fast(self) -> None:
        """CredentialError is raised before any network call when env vars are absent."""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(CredentialError):
                load_credentials()

    # ------------------------------------------------------------------ #
    #  test_environment_defaults_to_test                                  #
    # ------------------------------------------------------------------ #
    def test_environment_defaults_to_test(self) -> None:
        """get_environment() returns Environment.TEST when MERCHANT_ENV is not set."""
        with patch.dict(os.environ, {}, clear=True):
            env = get_environment()
        self.assertEqual(env, Environment.TEST)

    # ------------------------------------------------------------------ #
    #  test_upload_only_valid_rows                                        #
    # ------------------------------------------------------------------ #
    def test_upload_only_valid_rows(self) -> None:
        """upload_feed calls _upload_product exactly K times for K valid rows."""
        # 2 valid rows, 1 invalid row
        validation_results = [
            ValidationResult(row_id='r1', valid=True,  reasons=[]),
            ValidationResult(row_id='r2', valid=True,  reasons=[]),
            ValidationResult(row_id='r3', valid=False, reasons=['gtin_format']),
        ]
        report = build_report(validation_results)

        products = [
            MerchantProduct(id='r1'),
            MerchantProduct(id='r2'),
            MerchantProduct(id='r3'),
        ]

        creds = Credentials(
            service_account_path='/fake/key.json',
            merchant_id='merchant-1',
        )
        client = MerchantClient(creds, Environment.TEST)

        with patch.object(
            client,
            '_upload_product',
            return_value=UploadResult(product_id='r1', success=True),
        ) as mock_upload:
            client.upload_feed(report, products)
            self.assertEqual(mock_upload.call_count, 2)

    # ------------------------------------------------------------------ #
    #  test_upload_partial_failure_reported                               #
    # ------------------------------------------------------------------ #
    def test_upload_partial_failure_reported(self) -> None:
        """upload_feed continues after a per-product failure and reports both results."""
        validation_results = [
            ValidationResult(row_id='r1', valid=True, reasons=[]),
            ValidationResult(row_id='r2', valid=True, reasons=[]),
        ]
        report = build_report(validation_results)

        products = [
            MerchantProduct(id='r1'),
            MerchantProduct(id='r2'),
        ]

        creds = Credentials(
            service_account_path='/fake/key.json',
            merchant_id='merchant-1',
        )
        client = MerchantClient(creds, Environment.TEST)

        def _upload_side_effect(product: MerchantProduct) -> UploadResult:
            if product.id == 'r1':
                return UploadResult(product_id='r1', success=True)
            raise Exception("API rejected product")

        with patch.object(client, '_upload_product', side_effect=_upload_side_effect):
            upload_results = client.upload_feed(report, products)

        self.assertEqual(len(upload_results), 2)

        success = next(r for r in upload_results if r.product_id == 'r1')
        failure = next(r for r in upload_results if r.product_id == 'r2')

        self.assertTrue(success.success)
        self.assertFalse(failure.success)
        self.assertIsNotNone(failure.error)

    # ------------------------------------------------------------------ #
    #  test_status_readback_returns_statuses                              #
    # ------------------------------------------------------------------ #
    def test_status_readback_returns_statuses(self) -> None:
        """get_product_statuses returns one ProductStatus per requested ID."""
        creds = Credentials(
            service_account_path='/fake/key.json',
            merchant_id='merchant-1',
        )
        client = MerchantClient(creds, Environment.TEST)

        expected = ProductStatus(
            product_id='p1',
            status='approved',
            issues=[],
        )

        with patch.object(client, '_get_status', return_value=expected) as mock_get:
            results = client.get_product_statuses(['p1'])
            mock_get.assert_called_once_with('p1')

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].product_id, 'p1')
        self.assertEqual(results[0].status, 'approved')


# ── 4. Merchant API calls (gapic clients mocked, no network) ──────────────────
def _full_product(product_id: str = 'r1') -> MerchantProduct:
    """A product shaped like a pants_google_500.csv row after M2."""
    return MerchantProduct(
        id=product_id,
        title='ModernFit Pantalón mujer de seda gris talle XS',
        description='Pantalón de seda en color gris, rayado.',
        google_product_category='Apparel & Accessories > Clothing > Pants',
        gender='female',
        age_group='adult',
        size='XS',
        color='gray',
        material='Silk',
        link='https://matlock.github.io/?category=pants&product=11876597',
        image_link='https://example.com/11876597.jpg',
        price='45999.90 ARS',
        availability='in_stock',
        brand='ModernFit',
        condition='new',
        gtin='7790392405141',
        pattern='Striped',
    )


class MerchantApiTests(unittest.TestCase):

    def _client(self, data_source_id='ds-7') -> MerchantClient:
        creds = Credentials(
            service_account_path='/fake/key.json',
            merchant_id='merchant-1',
            data_source_id=data_source_id,
        )
        client = MerchantClient(creds, Environment.TEST)
        client._inputs_client = MagicMock()
        client._products_client = MagicMock()
        return client

    def test_upload_sends_product_to_data_source(self) -> None:
        """_upload_product inserts the converted product into the configured data source."""
        client = self._client()

        result = client._upload_product(_full_product())

        self.assertTrue(result.success)
        request = client._inputs_client.insert_product_input.call_args.kwargs['request']
        self.assertEqual(request.parent, 'accounts/merchant-1')
        self.assertEqual(request.data_source, 'accounts/merchant-1/dataSources/ds-7')

        product_input = request.product_input
        self.assertEqual(product_input.offer_id, 'r1')
        self.assertEqual(product_input.content_language, 'es')
        self.assertEqual(product_input.feed_label, 'AR')

        attrs = product_input.product_attributes
        self.assertEqual(attrs.price.amount_micros, 45_999_900_000)
        self.assertEqual(attrs.price.currency_code, 'ARS')
        self.assertEqual(list(attrs.gtins), ['7790392405141'])
        self.assertEqual(attrs.availability, merchant.Availability.IN_STOCK)
        self.assertEqual(attrs.condition, merchant.Condition.NEW)
        self.assertEqual(attrs.gender, merchant.Gender.FEMALE)
        self.assertEqual(attrs.age_group, merchant.AgeGroup.ADULT)
        self.assertEqual(attrs.material, 'Silk')

    def test_upload_without_data_source_aborts(self) -> None:
        """A missing MERCHANT_DATA_SOURCE_ID aborts upload_feed instead of failing every product."""
        client = self._client(data_source_id=None)
        report = build_report([ValidationResult(row_id='r1', valid=True, reasons=[])])

        with self.assertRaises(CredentialError):
            client.upload_feed(report, [_full_product()])
        client._inputs_client.insert_product_input.assert_not_called()

    def test_upload_invalid_enum_is_a_product_failure(self) -> None:
        """An availability value the API does not accept fails only that product."""
        client = self._client()
        bad = _full_product('r2')
        bad.availability = 'maybe'
        report = build_report([
            ValidationResult(row_id='r1', valid=True, reasons=[]),
            ValidationResult(row_id='r2', valid=True, reasons=[]),
        ])

        results = client.upload_feed(report, [_full_product('r1'), bad])

        self.assertTrue(results[0].success)
        self.assertFalse(results[1].success)
        self.assertIn('maybe', results[1].error)
        self.assertEqual(client._inputs_client.insert_product_input.call_count, 1)

    def test_status_reads_product_by_language_label_and_offer(self) -> None:
        """_get_status asks for accounts/{id}/products/{lang}~{label}~{offer}."""
        client = self._client()
        client._products_client.get_product.return_value = merchant.Product(
            product_status=merchant.ProductStatus(
                destination_statuses=[
                    merchant.ProductStatus.DestinationStatus(approved_countries=['AR']),
                ],
            ),
        )

        status = client._get_status('p1')

        client._products_client.get_product.assert_called_once_with(
            name='accounts/merchant-1/products/es~AR~p1',
        )
        self.assertEqual(status.status, 'approved')
        self.assertEqual(status.issues, [])

    def test_status_disapproved_lists_issues(self) -> None:
        """Any disapproved destination makes the product disapproved, with its issues."""
        client = self._client()
        client._products_client.get_product.return_value = merchant.Product(
            product_status=merchant.ProductStatus(
                destination_statuses=[
                    merchant.ProductStatus.DestinationStatus(approved_countries=['AR']),
                    merchant.ProductStatus.DestinationStatus(disapproved_countries=['AR']),
                ],
                item_level_issues=[
                    merchant.ProductStatus.ItemLevelIssue(
                        code='invalid_gtin',
                        description='Invalid GTIN',
                        attribute='gtin',
                    ),
                ],
            ),
        )

        status = client._get_status('p1')

        self.assertEqual(status.status, 'disapproved')
        self.assertEqual(status.issues, ['invalid_gtin: Invalid GTIN (gtin)'])

    def test_status_not_found_is_pending(self) -> None:
        """A product Merchant Center has not processed yet is reported as pending."""
        client = self._client()
        client._products_client.get_product.side_effect = google_exceptions.NotFound('nope')

        status = client._get_status('p1')

        self.assertEqual(status.status, 'pending')
        self.assertEqual(len(status.issues), 1)

    def test_bad_key_file_raises_credential_error(self) -> None:
        """A key path that does not exist surfaces as CredentialError, not a raw OSError."""
        creds = Credentials(
            service_account_path='/does/not/exist.json',
            merchant_id='merchant-1',
            data_source_id='ds-7',
        )
        client = MerchantClient(creds, Environment.TEST)

        with self.assertRaises(CredentialError):
            client._upload_product(_full_product())


if __name__ == '__main__':
    unittest.main()
