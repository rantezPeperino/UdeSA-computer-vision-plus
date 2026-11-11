"""Builds the Milestone 2 sample from the MatLock/UdeSA-computer-vision prototype.

Downloads the three img-puller CSVs and the multilabel models' labels.json files
from GitHub, pinned to a commit, and saves them byte for byte, unmodified, into
data/muestra/. Records the SHA-256 of each file in data/muestra/origen.csv.

The output file names and the origen.csv columns stay in Spanish: they are the
committed data the Milestone 2 deliverables and the EDA notebook read.

Usage (from the repo root):
    python scripts/build_sample.py
"""

import csv
import hashlib
from datetime import date
from pathlib import Path

import requests

REPO = "MatLock/UdeSA-computer-vision"
COMMIT = "b9b3b2b7e023b668233a5b3ff39efee1f66123ec"
RAW = f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/"

FILES = {
    "tops_tags.csv": "img-puller/data/tops_tags.csv",
    "shoes_tags.csv": "img-puller/data/shoes_tags.csv",
    "pants_tags.csv": "img-puller/data/pants_tags.csv",
    "taxonomia/tops.labels.json":
        "deep-tagger-api/deep_learning/torch_state/baseline_v1/multilabel_classifier_tops_v1.labels.json",
    "taxonomia/shoes.labels.json":
        "deep-tagger-api/deep_learning/torch_state/baseline_v1/multilabel_classifier_shoes_v1.labels.json",
    "taxonomia/pants.labels.json":
        "deep-tagger-api/deep_learning/torch_state/baseline_v1/multilabel_classifier_pants_v1.labels.json",
}

ROOT = Path(__file__).resolve().parent.parent
DESTINATION = ROOT / "data" / "muestra"


def main():
    rows = []
    for local, remote in FILES.items():
        resp = requests.get(RAW + remote, timeout=60)
        resp.raise_for_status()
        dest = DESTINATION / local
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        sha = hashlib.sha256(resp.content).hexdigest()
        rows.append({"archivo": local, "origen": f"{REPO}@{COMMIT}:{remote}",
                     "bytes": len(resp.content), "sha256": sha})
        print(f"{local}: {len(resp.content):,} bytes  sha256={sha[:12]}…")

    with open(DESTINATION / "origen.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["archivo", "origen", "bytes", "sha256", "fecha_extraccion"])
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "fecha_extraccion": date.today().isoformat()})


if __name__ == "__main__":
    main()
