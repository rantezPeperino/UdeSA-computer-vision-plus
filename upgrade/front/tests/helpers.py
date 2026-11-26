"""Shared fakes for the monitor tests: no model, no network, no credentials.

The models are replaced by a fake `positioner.enrichment.field_generator` in
sys.modules, the same trick the repo's tests use. The Merchant client is the
real class with `_upload_product` and `_get_status` overridden.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

FRONT = Path(__file__).resolve().parents[1]
ROOT = FRONT.parents[1]
for path in (str(FRONT), str(ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from positioner.enrichment.models import EnrichedProduct  # noqa: E402
from positioner.publishing.credential_loader import Credentials  # noqa: E402
from positioner.publishing.environment import Environment  # noqa: E402
from positioner.publishing.merchant_client import (  # noqa: E402
    MerchantClient,
    ProductStatus,
    UploadResult,
)

HEADER = 'id,image_url,brand,price,link,size,gender,color'

# One row per outcome the pipeline can give.
ROWS = [
    '1001,https://example.com/a.jpg,StyleCo,45999.00 ARS,https://example.com/p/1,M,female,black',
    '1002,https://example.com/b.jpg,StyleCo,45999.00 ARS,https://example.com/p/2,,female,black',
    '1003,https://example.com/roto.jpg,StyleCo,45999.00 ARS,https://example.com/p/3,L,male,',
    '1004,https://example.com/d.jpg,StyleCo,45.999,https://example.com/p/4,S,male,white',
    '1005,https://example.com/e.jpg,StyleCo,30000.00 ARS,https://example.com/p/5,S,unisex,',
]

calls = {'enrich': 0}
on_enrich = []  # callables run on each enrich call (used to interrupt)


def fake_enrich(row: dict) -> EnrichedProduct:
    calls['enrich'] += 1
    for hook in list(on_enrich):
        hook(calls['enrich'])
    if 'roto' in row['image_url']:
        return EnrichedProduct(gender=row.get('gender'), color=row.get('color') or None,
                               title='', description='x', status='partial')
    color = row.get('color') or 'gray'
    return EnrichedProduct(
        gender=row.get('gender'),
        color=color,
        predicted_color='gray',
        google_product_category='Apparel & Accessories > Clothing > Tops',
        title=f"{row.get('brand')} {row.get('gender')} T-shirt/top {color} {row.get('size')}",
        description='Descripción de prueba.',
        status='ok',
    )


def install_fake_models() -> None:
    module = types.ModuleType('positioner.enrichment.field_generator')
    module.enrich_product = fake_enrich
    sys.modules['positioner.enrichment.field_generator'] = module


class FakeClient(MerchantClient):
    """Uploads always succeed; 1001 is approved, 1005 disapproved, anything else pending."""

    def __init__(self) -> None:
        super().__init__(Credentials(service_account_path='/fake/key.json',
                                     merchant_id='123', data_source_id='456'),
                         Environment.TEST)

    def _upload_product(self, product):
        return UploadResult(product_id=product.id, success=True)

    def _get_status(self, product_id):
        status = {'1001': 'approved', '1005': 'disapproved'}.get(product_id, 'pending')
        issues = ['Imagen demasiado chica'] if status == 'disapproved' else []
        return ProductStatus(product_id=product_id, status=status, issues=issues)


def fake_connect():
    """Stands in for the script's connect(), printing what it prints."""
    print('Description generated with: anthropic')
    print('Merchant Center: account 123, environment test')
    return FakeClient()


def write_csv(folder: Path, name: str, rows=None, header: str = HEADER) -> Path:
    path = folder / name
    path.write_text('\n'.join([header, *(ROWS if rows is None else rows)]) + '\n',
                    encoding='utf-8')
    return path
