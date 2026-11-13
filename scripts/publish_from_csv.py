"""Milestone 4 in batch: every garment of a CSV, from its photo URL to Merchant Center.

For each row of the CSV, the same steps as publish_from_url.py: check the brand
fields, download and attribute the photo, build and validate the Merchant Center
row, and upload it. A row that fails does not stop the others. At the end it
waits for Google's verdict on the uploaded products and writes one result line
per row to a results CSV.

CSV columns:
    image_url (or url)         public URL of the garment photo
    brand, price, link         price with currency, e.g. "45999.00 ARS"
    size, gender               required by Google for apparel; no model infers them
    id                         optional; derived from the URL when empty
    color, material, pattern, gtin, availability, condition, age_group  optional
The synthetic feeds in upgrade/data/ already have this shape.

Same requirements as publish_from_url.py: the deep-tagger-api dependencies and,
to upload, the Merchant Center variables in upgrade/MERCHANT_SETUP.md plus an
LLM key (OPENAI_API_KEY or ANTHROPIC_API_KEY).

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
from positioner.automation.connect import SetupError, connect  # noqa: E402
from positioner.automation.pipeline import DRY_RUN, UPLOADED  # noqa: E402
from positioner.publishing.credential_loader import CredentialError  # noqa: E402

RESULT_COLUMNS = [
    "id", "image_url", "stage", "merchant_status", "reasons",
    "title", "google_product_category", "predicted_color", "description",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csv", type=Path, help="CSV with one garment per row")
    parser.add_argument("--out", type=Path,
                        help="results CSV; default <input>_results.csv next to the input")
    parser.add_argument("--limit", type=int, metavar="N", help="process only the first N rows")
    parser.add_argument("--dry-run", action="store_true",
                        help="build and validate every product without uploading anything")
    parser.add_argument("--wait", type=int, default=300, metavar="SECONDS",
                        help="how long to wait for Google's verdict (0 to not wait; default 300)")
    return parser.parse_args()


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

    try:
        client = connect(args.dry_run)
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
