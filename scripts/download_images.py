"""Downloads a stratified subset of the sample's images, with a fixed seed.

Picks N images per category (tops, shoes, pants), with allocation proportional
to `season`, and saves the list to data/muestra/subconjunto_imagenes.csv (it is
committed). The images go to data/images/<category>/<id><ext> at their original
size and are not committed. It is idempotent: it does not download again what is
already there.

The list's file name and columns (categoria, ruta) stay in Spanish: they are
committed data that scripts/build_labeling_sheet.py and the EDA notebook read.

Usage (from the repo root):
    python scripts/download_images.py            # 100 per category
    python scripts/download_images.py --n 50
"""

import argparse
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import requests

SEED = 42
CATEGORIES = ("tops", "shoes", "pants")
ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "muestra"
IMAGES = ROOT / "data" / "images"
LIST_PATH = SAMPLE / "subconjunto_imagenes.csv"
HEADERS = {"User-Agent": "UdeSA-toi-hito2/1.0 (academic project)"}
# Stratum value for rows with an empty season; kept as is so the seeded sample does not change.
EMPTY_STRATUM = "<vacío>"


def choose(df: pd.DataFrame, n: int, stratum: str) -> pd.DataFrame:
    """Stratified sampling with proportional allocation (largest remainder) and a fixed seed."""
    groups = df[stratum].fillna(EMPTY_STRATUM)
    share = groups.value_counts(normalize=True).sort_index()
    quota = share * n
    allocated = np.floor(quota).astype(int)
    missing = n - allocated.sum()
    for key in (quota - allocated).sort_values(ascending=False).index[:missing]:
        allocated[key] += 1
    parts = [df[groups == key].sample(n=k, random_state=SEED) for key, k in allocated.items() if k > 0]
    return pd.concat(parts).sort_values("id")


def download(row) -> str:
    destination = ROOT / row.ruta
    if destination.exists():
        return "already there"
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        resp = requests.get(row.image_url, timeout=30, headers=HEADERS)
        resp.raise_for_status()
        destination.write_bytes(resp.content)
        return "ok"
    except requests.RequestException as e:
        return f"error: {e.__class__.__name__}"
    finally:
        time.sleep(0.2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=100, help="images per category")
    args = parser.parse_args()

    chosen = []
    for cat in CATEGORIES:
        df = pd.read_csv(SAMPLE / f"{cat}_tags.csv", dtype=str)
        subset = choose(df, args.n, "season")[["id", "image_url", "season"]].copy()
        subset.insert(1, "categoria", cat)
        ext = subset["image_url"].map(lambda u: Path(urlparse(u).path).suffix or ".jpg")
        subset["ruta"] = "data/images/" + cat + "/" + subset["id"] + ext
        chosen.append(subset)
    image_list = pd.concat(chosen, ignore_index=True)
    image_list[["id", "categoria", "season", "image_url", "ruta"]].to_csv(LIST_PATH, index=False)

    with ThreadPoolExecutor(max_workers=4) as pool:
        states = list(pool.map(download, image_list.itertuples()))
    print(pd.Series(states).value_counts().to_string())
    print(f"List in {LIST_PATH.relative_to(ROOT)}; images in {IMAGES.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
