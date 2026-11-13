"""Tests for positioner.automation (Milestone 4 — URL to Merchant Center).

Milestone 1 is replaced by a fake `enrich` function, so no model, GPU or image
download runs. The Merchant client is real, with `_upload_product` and
`_get_status` patched, so no Google auth and no network.

Run: python -m unittest positioner.tests.test_automation -v
"""

# ── 1. sys.path: make positioner importable from workspace root ───────────────
import sys
import os

_WS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _WS_ROOT not in sys.path:
    sys.path.insert(0, _WS_ROOT)

# ── 2. imports ────────────────────────────────────────────────────────────────
import tempfile  # noqa: E402
import unittest  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

from positioner.automation.batch import (  # noqa: E402
    ERROR,
    BatchRow,
    read_rows,
    run_batch,
    wait_for_statuses,
)
from positioner.automation.pipeline import (  # noqa: E402
    DOWNLOAD_FAILED,
    DRY_RUN,
    INVALID,
    UPLOAD_FAILED,
    UPLOADED,
    product_id_from_url,
    run_pipeline,
    wait_for_status,
)
from positioner.enrichment.models import EnrichedProduct  # noqa: E402
from positioner.publishing.credential_loader import Credentials  # noqa: E402
from positioner.publishing.environment import Environment  # noqa: E402
from positioner.publishing.merchant_client import (  # noqa: E402
    MerchantClient,
    ProductStatus,
    UploadResult,
)

IMAGE_URL = 'https://example.com/fotos/pantalon-negro.jpg'


def _business(**overrides) -> dict:
    """Brand-declared fields of a garment that passes validation."""
    business = {
        'brand': 'StyleCo',
        'price': '45999.00 ARS',
        'availability': 'in_stock',
        'link': 'https://matlock.github.io/productos/pantalon-negro',
        'condition': 'new',
        'size': 'M',
        'gender': 'female',
        'age_group': 'adult',
    }
    business.update(overrides)
    return business


def _enriched(status: str = 'ok', **overrides) -> EnrichedProduct:
    """What Milestone 1 returns for a downloaded and attributed photo."""
    fields = dict(
        gender='female',
        color='black',
        predicted_color='black',
        google_product_category='Apparel & Accessories > Clothing > Pants',
        title='StyleCo Women Pants Slim-Fit-Pant Black M',
        description='Pantalón negro de calce ajustado.',
        status=status,
    )
    fields.update(overrides)
    return EnrichedProduct(**fields)


def _client() -> MerchantClient:
    creds = Credentials(
        service_account_path='/fake/key.json',
        merchant_id='123',
        data_source_id='456',
    )
    return MerchantClient(creds, Environment.TEST)


class AutomationPipelineTests(unittest.TestCase):

    # ------------------------------------------------------------------ #
    #  test_pipeline_missing_business_field_fails_before_download         #
    # ------------------------------------------------------------------ #
    def test_pipeline_missing_business_field_fails_before_download(self) -> None:
        """A missing price aborts the run before Milestone 1 downloads anything."""
        enrich = MagicMock(return_value=_enriched())
        business = _business()
        del business['price']

        with self.assertRaisesRegex(ValueError, 'price'):
            run_pipeline(IMAGE_URL, business, client=_client(), enrich=enrich)

        enrich.assert_not_called()

    # ------------------------------------------------------------------ #
    #  test_pipeline_enriches_from_image_url                              #
    # ------------------------------------------------------------------ #
    def test_pipeline_enriches_from_image_url(self) -> None:
        """Milestone 1 gets the URL, and the product carries what it inferred."""
        enrich = MagicMock(return_value=_enriched())

        result = run_pipeline(IMAGE_URL, _business(), dry_run=True, enrich=enrich)

        row = enrich.call_args.args[0]
        self.assertEqual(row['image_url'], IMAGE_URL)
        self.assertEqual(row['brand'], 'StyleCo')
        self.assertEqual(result.product.image_link, IMAGE_URL)
        self.assertEqual(result.product.title, 'StyleCo Women Pants Slim-Fit-Pant Black M')
        self.assertEqual(result.product.description, 'Pantalón negro de calce ajustado.')
        self.assertEqual(
            result.product.google_product_category,
            'Apparel & Accessories > Clothing > Pants',
        )
        self.assertEqual(result.product.color, 'black')

    # ------------------------------------------------------------------ #
    #  test_pipeline_stops_when_download_fails                            #
    # ------------------------------------------------------------------ #
    def test_pipeline_stops_when_download_fails(self) -> None:
        """A 'partial' enrichment (no image) ends the run without uploading."""
        enrich = MagicMock(return_value=_enriched(status='partial'))
        client = _client()

        with patch.object(client, '_upload_product') as upload:
            result = run_pipeline(IMAGE_URL, _business(), client=client, enrich=enrich)

        self.assertEqual(result.stage, DOWNLOAD_FAILED)
        self.assertIsNone(result.product)
        self.assertIn(IMAGE_URL, result.reasons[0])
        upload.assert_not_called()

    # ------------------------------------------------------------------ #
    #  test_pipeline_skips_upload_when_invalid                            #
    # ------------------------------------------------------------------ #
    def test_pipeline_skips_upload_when_invalid(self) -> None:
        """A product without a size fails validation and is not uploaded."""
        enrich = MagicMock(return_value=_enriched())
        client = _client()
        business = _business()
        del business['size']

        with patch.object(client, '_upload_product') as upload:
            result = run_pipeline(IMAGE_URL, business, client=client, enrich=enrich)

        self.assertEqual(result.stage, INVALID)
        self.assertIn('missing_size', result.reasons)
        upload.assert_not_called()

    # ------------------------------------------------------------------ #
    #  test_pipeline_uploads_valid_product                                #
    # ------------------------------------------------------------------ #
    def test_pipeline_uploads_valid_product(self) -> None:
        """A valid product is uploaded exactly once, under the given ID."""
        enrich = MagicMock(return_value=_enriched())
        client = _client()

        with patch.object(
            client, '_upload_product',
            return_value=UploadResult(product_id='p-1', success=True),
        ) as upload:
            result = run_pipeline(
                IMAGE_URL, _business(), client=client, product_id='p-1', enrich=enrich,
            )

        self.assertEqual(result.stage, UPLOADED)
        self.assertTrue(result.upload.success)
        upload.assert_called_once()
        self.assertEqual(upload.call_args.args[0].id, 'p-1')

    # ------------------------------------------------------------------ #
    #  test_pipeline_reports_upload_error                                 #
    # ------------------------------------------------------------------ #
    def test_pipeline_reports_upload_error(self) -> None:
        """An API rejection ends the run as 'upload_failed' with the API error."""
        enrich = MagicMock(return_value=_enriched())
        client = _client()

        with patch.object(
            client, '_upload_product',
            side_effect=RuntimeError('400 invalid link domain'),
        ):
            result = run_pipeline(IMAGE_URL, _business(), client=client, enrich=enrich)

        self.assertEqual(result.stage, UPLOAD_FAILED)
        self.assertFalse(result.upload.success)
        self.assertEqual(result.reasons, ['400 invalid link domain'])

    # ------------------------------------------------------------------ #
    #  test_product_id_is_stable_for_same_url                             #
    # ------------------------------------------------------------------ #
    def test_product_id_is_stable_for_same_url(self) -> None:
        """Two runs on one URL use one offer ID; another URL gets another ID."""
        enrich = MagicMock(return_value=_enriched())

        first = run_pipeline(IMAGE_URL, _business(), dry_run=True, enrich=enrich)
        second = run_pipeline(IMAGE_URL, _business(), dry_run=True, enrich=enrich)

        self.assertEqual(first.product_id, second.product_id)
        self.assertEqual(first.product.id, first.product_id)
        self.assertNotEqual(
            first.product_id,
            product_id_from_url('https://example.com/fotos/otra.jpg'),
        )

    # ------------------------------------------------------------------ #
    #  test_pipeline_dry_run_makes_no_upload                              #
    # ------------------------------------------------------------------ #
    def test_pipeline_dry_run_makes_no_upload(self) -> None:
        """Dry run returns the validated product and never calls the API."""
        enrich = MagicMock(return_value=_enriched())
        client = _client()

        with patch.object(client, '_upload_product') as upload, \
                patch.object(client, '_get_status') as get_status:
            result = run_pipeline(
                IMAGE_URL, _business(), client=client, dry_run=True, enrich=enrich,
            )

        self.assertEqual(result.stage, DRY_RUN)
        self.assertTrue(result.validation.valid)
        self.assertIsNone(result.upload)
        upload.assert_not_called()
        get_status.assert_not_called()

    # ------------------------------------------------------------------ #
    #  test_wait_for_status_returns_verdict                               #
    # ------------------------------------------------------------------ #
    def test_wait_for_status_returns_verdict(self) -> None:
        """Polling continues through 'pending' and returns 'approved'."""
        client = _client()
        statuses = [
            ProductStatus(product_id='p-1', status='pending'),
            ProductStatus(product_id='p-1', status='pending'),
            ProductStatus(product_id='p-1', status='approved'),
        ]
        sleep = MagicMock()

        with patch.object(client, '_get_status', side_effect=statuses):
            status = wait_for_status(
                client, 'p-1', timeout_s=300, interval_s=15,
                sleep=sleep, clock=lambda: 0,
            )

        self.assertEqual(status.status, 'approved')
        self.assertEqual(sleep.call_count, 2)

    # ------------------------------------------------------------------ #
    #  test_wait_for_status_gives_up_after_timeout                        #
    # ------------------------------------------------------------------ #
    def test_wait_for_status_gives_up_after_timeout(self) -> None:
        """A product still pending at the time limit is returned as 'pending'."""
        client = _client()
        now = [0.0]

        def sleep(seconds: float) -> None:
            now[0] += seconds

        with patch.object(
            client, '_get_status',
            return_value=ProductStatus(product_id='p-1', status='pending'),
        ) as get_status:
            status = wait_for_status(
                client, 'p-1', timeout_s=60, interval_s=15,
                sleep=sleep, clock=lambda: now[0],
            )

        self.assertEqual(status.status, 'pending')
        # Polls at t = 0, 15, 30, 45 and 60; the next one would pass the limit.
        self.assertEqual(get_status.call_count, 5)


def _write_csv(text: str) -> str:
    """Write a CSV to a temporary file and return its path."""
    file = tempfile.NamedTemporaryFile(
        'w', suffix='.csv', delete=False, encoding='utf-8', newline='',
    )
    with file:
        file.write(text)
    return file.name


CSV_HEADER = 'id,image_url,brand,price,link,size,gender,title\n'


def _row(product_id: str = 'p-1', **overrides) -> BatchRow:
    return BatchRow(product_id, f'https://example.com/{product_id}.jpg', _business(**overrides))


class BatchTests(unittest.TestCase):

    def tearDown(self) -> None:
        for path in getattr(self, '_paths', []):
            os.unlink(path)

    def _csv(self, text: str) -> str:
        path = _write_csv(text)
        self._paths = [*getattr(self, '_paths', []), path]
        return path

    # ------------------------------------------------------------------ #
    #  test_read_rows_takes_brand_fields_from_csv                         #
    # ------------------------------------------------------------------ #
    def test_read_rows_takes_brand_fields_from_csv(self) -> None:
        """Each row gives its ID, URL and brand fields, with defaults filled in."""
        path = self._csv(
            CSV_HEADER
            + '11876597,https://example.com/a.jpg,StyleCo,45999.00 ARS,'
              'https://matlock.github.io/?product=1,M,female,ignored title\n'
        )

        rows = read_rows(path)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].product_id, '11876597')
        self.assertEqual(rows[0].image_url, 'https://example.com/a.jpg')
        self.assertEqual(rows[0].business['price'], '45999.00 ARS')
        self.assertEqual(rows[0].business['availability'], 'in_stock')
        self.assertEqual(rows[0].business['condition'], 'new')
        self.assertEqual(rows[0].business['age_group'], 'adult')
        self.assertNotIn('title', rows[0].business)

    # ------------------------------------------------------------------ #
    #  test_read_rows_derives_id_from_url                                 #
    # ------------------------------------------------------------------ #
    def test_read_rows_derives_id_from_url(self) -> None:
        """Without an id column, the ID comes from the URL; 'url' is accepted."""
        path = self._csv(
            'url,brand,price,link,size,gender\n'
            'https://example.com/a.jpg,StyleCo,10.00 ARS,https://matlock.github.io/,M,male\n'
        )

        rows = read_rows(path)

        self.assertEqual(rows[0].product_id, product_id_from_url('https://example.com/a.jpg'))

    # ------------------------------------------------------------------ #
    #  test_read_rows_rejects_bad_csv                                     #
    # ------------------------------------------------------------------ #
    def test_read_rows_rejects_bad_csv(self) -> None:
        """Missing columns and repeated IDs fail before any row is processed."""
        no_size = self._csv(
            'image_url,brand,price,link,gender\n'
            'https://example.com/a.jpg,StyleCo,10.00 ARS,https://matlock.github.io/,male\n'
        )
        repeated = self._csv(
            CSV_HEADER
            + 'p-1,https://example.com/a.jpg,S,10.00 ARS,https://m.io/,M,male,\n'
            + 'p-1,https://example.com/b.jpg,S,10.00 ARS,https://m.io/,M,male,\n'
        )

        with self.assertRaisesRegex(ValueError, 'size'):
            read_rows(no_size)
        with self.assertRaisesRegex(ValueError, 'line 3'):
            read_rows(repeated)

    # ------------------------------------------------------------------ #
    #  test_batch_skips_row_without_declared_fields                       #
    # ------------------------------------------------------------------ #
    def test_batch_skips_row_without_declared_fields(self) -> None:
        """A row without size is 'invalid' and never reaches the models."""
        enrich = MagicMock(return_value=_enriched())
        row = _row()
        del row.business['size']

        [result] = run_batch([row], dry_run=True, enrich=enrich)

        self.assertEqual(result.stage, INVALID)
        self.assertEqual(result.reasons, ['missing_size'])
        enrich.assert_not_called()

    # ------------------------------------------------------------------ #
    #  test_batch_continues_after_failed_row                              #
    # ------------------------------------------------------------------ #
    def test_batch_continues_after_failed_row(self) -> None:
        """An error in one row is recorded and the next rows are still uploaded."""
        enrich = MagicMock(side_effect=[RuntimeError('LLM timeout'), _enriched()])
        client = _client()
        seen = []

        with patch.object(
            client, '_upload_product',
            return_value=UploadResult(product_id='p-2', success=True),
        ) as upload:
            results = run_batch(
                [_row('p-1'), _row('p-2')], client=client, enrich=enrich,
                on_result=lambda index, result: seen.append(index),
            )

        self.assertEqual([r.stage for r in results], [ERROR, UPLOADED])
        self.assertEqual(results[0].reasons, ['LLM timeout'])
        self.assertEqual(seen, [0, 1])
        upload.assert_called_once()
        self.assertEqual(upload.call_args.args[0].id, 'p-2')

    # ------------------------------------------------------------------ #
    #  test_wait_for_statuses_polls_only_pending                          #
    # ------------------------------------------------------------------ #
    def test_wait_for_statuses_polls_only_pending(self) -> None:
        """Products with a verdict are not asked for again."""
        client = _client()
        answers = {
            'p-1': iter(['approved']),
            'p-2': iter(['pending', 'disapproved']),
        }

        def get_status(product_id: str) -> ProductStatus:
            return ProductStatus(product_id=product_id, status=next(answers[product_id]))

        with patch.object(client, '_get_status', side_effect=get_status) as calls:
            statuses = wait_for_statuses(
                client, ['p-1', 'p-2'], sleep=MagicMock(), clock=lambda: 0,
            )

        self.assertEqual(statuses['p-1'].status, 'approved')
        self.assertEqual(statuses['p-2'].status, 'disapproved')
        self.assertEqual(calls.call_count, 3)


if __name__ == '__main__':
    unittest.main()
