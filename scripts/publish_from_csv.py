"""Milestone 4: from a CSV of garments to products in Google Merchant Center.

Takes the path of a local CSV with one garment per row: the public URL of its
photo and the fields only the brand knows. For each row:

  1. checks that the brand's required fields are present,
  2. downloads the image and attributes it with the prototype's models (stage 1),
  3. builds the Merchant Center row and validates it (stage 2),
  4. uploads it to Merchant Center (stage 3).

A row stops at the first stage that fails, and the next rows go on. At the end
it waits for Google to approve or disapprove the uploaded products and writes
one result line per row to a results CSV.

CSV columns:
    image_url (or url)         public URL of the garment photo
    brand, price, link         price with currency, e.g. "45999.00 ARS"
    size, gender               required by Google for apparel; no model infers them
    id                         optional; derived from the URL when empty, so the
                               same photo always updates the same product
    color, material, pattern, gtin, availability, condition, age_group  optional
The synthetic feeds in upgrade/data/ already have this shape.

Needs the deep-tagger-api dependencies (torch, transformers, etc.) and, to upload,
the environment variables in upgrade/MERCHANT_SETUP.md:
    GOOGLE_SERVICE_ACCOUNT_PATH, MERCHANT_ID, MERCHANT_DATA_SOURCE_ID
plus a key to generate the description: OPENAI_API_KEY or ANTHROPIC_API_KEY
(LLM_PROVIDER=openai|anthropic picks one when both are set; see
deep-tagger-api/llm/description_client.py).

Usage (from the repo root):
    python scripts/publish_from_csv.py products.csv --dry-run --limit 3   # uploads nothing
    python scripts/publish_from_csv.py products.csv
    python scripts/publish_from_csv.py products.csv --out results.csv --wait 0
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# enrich_product imports the deep-tagger-api modules as top-level packages.
sys.path.insert(0, str(ROOT / "deep-tagger-api"))

from positioner.automation.batch import read_rows, run_batch, wait_for_statuses  # noqa: E402
from positioner.automation.pipeline import DRY_RUN, UPLOADED  # noqa: E402
from positioner.publishing.credential_loader import CredentialError, load_credentials  # noqa: E402
from positioner.publishing.environment import get_environment  # noqa: E402
from positioner.publishing.merchant_client import MerchantClient  # noqa: E402

RESULT_COLUMNS = [
    "id", "image_url", "stage", "merchant_status", "reasons",
    "title", "google_product_category", "predicted_color", "description",
]


class SetupError(Exception):
    """Something the upload needs is not configured; the message says what."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csv", type=Path, help="local CSV with one garment per row")
    parser.add_argument("--out", type=Path,
                        help="results CSV; default <input>_results.csv next to the input")
    parser.add_argument("--limit", type=int, metavar="N", help="process only the first N rows")
    parser.add_argument("--dry-run", action="store_true",
                        help="build and validate every product without uploading anything")
    parser.add_argument("--wait", type=int, default=300, metavar="SECONDS",
                        help="how long to wait for Google's verdict (0 to not wait; default 300)")
    return parser.parse_args()


def connect() -> MerchantClient:
    """Check the LLM key and build the Merchant client, printing what is used."""
    from llm import description_client  # from deep-tagger-api
    try:
        provider = description_client.provider()
    except ValueError as error:
        raise SetupError(f"LLM_PROVIDER: {error}") from error
    if provider is None:
        raise SetupError(
            "Missing the language model key (OPENAI_API_KEY or ANTHROPIC_API_KEY, "
            "the one matching LLM_PROVIDER if it is set): without it the description "
            "is placeholder text and would be uploaded as such to Merchant Center. "
            "Set it or run with --dry-run."
        )
    print(f"Description generated with: {provider}")

    try:
        credentials = load_credentials()
    except CredentialError as error:
        raise SetupError(
            f"Merchant Center credentials: {error} (see upgrade/MERCHANT_SETUP.md)"
        ) from error
    environment = get_environment()
    print(f"Merchant Center: account {credentials.merchant_id}, environment {environment.value}")
    return MerchantClient(credentials, environment)


def result_line(result, status=None) -> dict:
    enriched = result.enriched
    return {
        "id": result.product_id,
        "image_url": result.image_url,
        "stage": result.stage,
        "merchant_status": status.status if status else "",
        "reasons": "; ".join([*result.reasons, *(status.issues if status else [])]),
        "title": enriched.title if enriched else "",
        "google_product_category": enriched.google_product_category if enriched else "",
        "predicted_color": enriched.predicted_color if enriched else "",
        "description": enriched.description if enriched else "",
    }


def write_results(path: Path, results, statuses) -> None:
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=RESULT_COLUMNS)
        writer.writeheader()
        for result in results:
            writer.writerow(result_line(result, statuses.get(result.product_id)))


def main() -> int:
    args = parse_args()
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    # The CSV is checked before loading anything, so a bad file fails at once.
    try:
        rows = read_rows(args.csv)
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    if args.limit is not None:
        rows = rows[:args.limit]
    out = args.out or args.csv.with_name(f"{args.csv.stem}_results.csv")

    client = None
    if not args.dry_run:
        try:
            client = connect()
        except SetupError as error:
            print(error, file=sys.stderr)
            return 2

    print(f"{len(rows)} products from {args.csv}")
    print("Loading the models and processing the images…")

    results = []

    def report(index, result):
        results.append(result)
        reasons = f" ({'; '.join(result.reasons)})" if result.reasons else ""
        print(f"[{index + 1}/{len(rows)}] {result.product_id}: {result.stage}{reasons}", flush=True)

    statuses = {}
    try:
        run_batch(rows, client=client, dry_run=args.dry_run, on_result=report)
    except CredentialError as error:
        print(f"Merchant Center credentials: {error}", file=sys.stderr)
        return 2
    finally:
        # Also on Ctrl-C: the rows already processed are not lost.
        write_results(out, results, statuses)

    uploaded = [r.product_id for r in results if r.stage == UPLOADED]
    if uploaded and args.wait > 0:
        print(f"\nWaiting for Google's verdict on {len(uploaded)} products (up to {args.wait} s)…")
        try:
            statuses = wait_for_statuses(client, uploaded, timeout_s=args.wait)
        except Exception as error:
            print(f"Could not read the statuses: {error}. "
                  "They show up in Merchant Center → Products.", file=sys.stderr)
        write_results(out, results, statuses)
    elif uploaded:
        print("\nNot waiting for Google's verdict. It shows up in Merchant Center → Products.")

    print("\nSummary:")
    for stage, count in Counter(r.stage for r in results).most_common():
        print(f"  {stage}: {count}")
    if statuses:
        for status, count in Counter(s.status for s in statuses.values()).most_common():
            print(f"  Merchant Center {status}: {count}")
    print(f"Results in {out}")

    ok_stage = DRY_RUN if args.dry_run else UPLOADED
    failed = any(r.stage != ok_stage for r in results)
    disapproved = any(s.status == "disapproved" for s in statuses.values())
    return 1 if failed or disapproved else 0


if __name__ == "__main__":
    sys.exit(main())
