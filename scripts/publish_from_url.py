"""Milestone 4: from the URL of a photo to a product in Google Merchant Center.

Given the URL of a garment photo and the fields only the brand knows:

  1. checks that the brand's required fields are present,
  2. downloads the image and attributes it with the prototype's models (stage 1),
  3. builds the Merchant Center row and validates it (stage 2),
  4. uploads it to Merchant Center (stage 3),
  5. waits for Google to approve or disapprove it.

Stops at the first stage that fails and says which one. The same URL always gives
the same product ID, so running it twice updates the product instead of
duplicating it.

Needs the deep-tagger-api dependencies (torch, transformers, etc.) and, to upload,
the environment variables in upgrade/MERCHANT_SETUP.md:
    GOOGLE_SERVICE_ACCOUNT_PATH, MERCHANT_ID, MERCHANT_DATA_SOURCE_ID
plus a key to generate the description: OPENAI_API_KEY or ANTHROPIC_API_KEY
(LLM_PROVIDER=openai|anthropic picks one when both are set; see
deep-tagger-api/llm/description_client.py).

Usage (from the repo root):
    python scripts/publish_from_url.py <url> --brand StyleCo --price "45999.00 ARS" \\
        --link "https://matlock.github.io/?product=1" --size M --gender female
    python scripts/publish_from_url.py <url> ... --dry-run     # uploads nothing
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# enrich_product imports the deep-tagger-api modules as top-level packages.
sys.path.insert(0, str(ROOT / "deep-tagger-api"))

from positioner.automation.pipeline import (  # noqa: E402
    UPLOADED,
    product_id_from_url,
    run_pipeline,
    wait_for_status,
)
from positioner.automation.connect import SetupError, connect  # noqa: E402
from positioner.publishing.credential_loader import CredentialError  # noqa: E402

STAGES = {
    "download_failed": "Could not download the image",
    "invalid": "The product failed validation",
    "dry_run": "Dry run: the product is valid, nothing was uploaded",
    "uploaded": "Uploaded to Merchant Center",
    "upload_failed": "Merchant Center rejected the upload",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url", help="public URL of the garment photo")
    parser.add_argument("--id", help="product ID; derived from the URL by default")

    brand = parser.add_argument_group("brand-declared fields")
    brand.add_argument("--brand", required=True)
    brand.add_argument("--price", required=True, help='with currency, e.g. "45999.00 ARS"')
    brand.add_argument("--link", required=True, help="product page, on the domain of the account's website")
    brand.add_argument("--size")
    brand.add_argument("--gender", choices=["female", "male", "unisex"])
    brand.add_argument("--color", help="when not declared, the K-Means prediction is used")
    brand.add_argument("--material")
    brand.add_argument("--pattern")
    brand.add_argument("--gtin")
    brand.add_argument("--availability", default="in_stock")
    brand.add_argument("--condition", default="new")
    brand.add_argument("--age-group", default="adult", help="Google's age_group")

    parser.add_argument("--dry-run", action="store_true", help="build and validate the product without uploading it")
    parser.add_argument("--wait", type=int, default=300, metavar="SECONDS",
                        help="how long to wait for Google's verdict (0 to not wait; default 300)")
    return parser.parse_args()


def brand_fields(args: argparse.Namespace) -> dict:
    fields = {
        "brand": args.brand,
        "price": args.price,
        "link": args.link,
        "size": args.size,
        "gender": args.gender,
        "color": args.color,
        "material": args.material,
        "pattern": args.pattern,
        "gtin": args.gtin,
        "availability": args.availability,
        "condition": args.condition,
        "age_group": args.age_group,
    }
    return {k: v for k, v in fields.items() if v}


def print_product(result) -> None:
    enriched = result.enriched
    print("\nAttributes inferred from the photo:")
    print(f"  Google category:  {enriched.google_product_category or '-'}")
    print(f"  predicted color:  {enriched.predicted_color or '-'}")
    print(f"  title:            {enriched.title or '-'}")
    print(f"  description:      {enriched.description or '-'}")
    if enriched.status == "needs_category_review":
        print("  (the product type is not in the Google category map: review it)")


def main() -> int:
    args = parse_args()
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        client = connect(args.dry_run)
    except SetupError as error:
        print(error, file=sys.stderr)
        return 2

    product_id = args.id or product_id_from_url(args.url)
    print(f"Product {product_id} from {args.url}")
    print("Loading the models and processing the image…")

    try:
        result = run_pipeline(
            args.url, brand_fields(args),
            client=client, product_id=product_id, dry_run=args.dry_run,
        )
    except ValueError as error:
        # Mostly a required brand field that is missing.
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except CredentialError as error:
        print(f"Merchant Center credentials: {error}", file=sys.stderr)
        return 2

    if result.enriched is not None and result.stage != "download_failed":
        print_product(result)

    print(f"\n{STAGES[result.stage]}")
    for reason in result.reasons:
        print(f"  - {reason}")

    if result.stage != UPLOADED:
        return 0 if args.dry_run and result.stage == "dry_run" else 1

    if args.wait <= 0:
        print("Not waiting for Google's verdict. It shows up in Merchant Center → Products.")
        return 0

    print(f"Waiting for Google's verdict (up to {args.wait} s)…")
    status = wait_for_status(client, product_id, timeout_s=args.wait)
    print(f"Status in Merchant Center: {status.status}")
    for issue in status.issues:
        print(f"  - {issue}")
    return 1 if status.status == "disapproved" else 0


if __name__ == "__main__":
    sys.exit(main())
