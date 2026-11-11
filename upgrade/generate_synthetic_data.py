#!/usr/bin/env python3
"""
Generates the synthetic test feed from the first 500 rows of each img-puller CSV.
Adds the fields the brand declares (brand, price, gtin, availability, link,
condition, gender, material, pattern, color, size, age_group) and the ones the
pipeline builds (google_product_category, title, description).

Everything added is synthetic: it is drawn with a fixed seed and does not look at
the photo. It is for testing the feed contract, validation and publishing (M2 to
M4), not for training or evaluating models.

The feed targets Argentina, so titles and descriptions are generated in Spanish:
the dictionaries below map each value to its Spanish wording.

Usage (from the repo root):
    python upgrade/generate_synthetic_data.py
"""

import csv
import random
from pathlib import Path

SEED = 42
MAX_ROWS = 500

SOURCES = {
    "pants": Path("img-puller/data/pants_tags.csv"),
    "shoes": Path("img-puller/data/shoes_tags.csv"),
    "tops": Path("img-puller/data/tops_tags.csv"),
}
OUTPUT_DIR = Path("upgrade/data")

# Links must be on the same domain as the Merchant Center account's website;
# otherwise Google disapproves the product (url_does_not_match_homepage).
# See upgrade/MERCHANT_SETUP.md.
STORE_URL = "https://matlock.github.io/"

# Synthetic pools. The brands are made up; prices are in Argentine pesos.
BRANDS = ["StyleCo", "FashionHub", "TrendWear", "ClassicStyle", "ModernFit", "ElegantLine"]
PRICE_RANGE_ARS = (15000.00, 150000.00)
GTIN_SHARE = 0.5          # the other half has no GTIN, like a private-label garment
GS1_PREFIX_AR = "779"     # GS1 prefix for Argentina

GENDERS = {"female": "mujer", "male": "hombre", "unisex": "unisex"}
MATERIALS = {
    "Cotton": "algodón", "Polyester": "poliéster", "Cotton Blend": "mezcla de algodón",
    "Denim": "denim", "Linen": "lino", "Wool": "lana", "Silk": "seda",
}
PATTERNS = {
    "Solid": "liso", "Striped": "rayado", "Checkered": "a cuadros",
    "Floral": "floreado", "Abstract": "estampado abstracto", "Geometric": "estampado geométrico",
}
COLORS = {
    "black": "negro", "navy blue": "azul marino", "white": "blanco", "gray": "gris",
    "beige": "beige", "khaki": "caqui", "blue": "azul", "red": "rojo", "green": "verde",
}
SIZES = {
    "pants": ["XS", "S", "M", "L", "XL", "XXL"],
    "tops": ["XS", "S", "M", "L", "XL", "XXL"],
    "shoes": [str(n) for n in range(35, 45)],
}

# Same paths as positioner/enrichment/category_mapper.py
CATEGORY_MAP = {
    "pants": "Apparel & Accessories > Clothing > Pants",
    "shoes": "Apparel & Accessories > Shoes",
    "tops": "Apparel & Accessories > Clothing > Tops",
}

PRODUCT_NAMES = {"pants": "Pantalón", "tops": "Top"}
SHOE_NAMES = {
    "Boots": "Botas", "Winter-Boots": "Botas de invierno", "Chelsea-Boots": "Botas Chelsea",
    "Combat-Boots": "Borcegos", "Booties": "Botinetas", "Loafers": "Mocasines",
    "Sandals": "Sandalias", "Slides": "Chinelas", "Flats": "Chatitas",
    "Casual-Sneakers": "Zapatillas", "Pumps": "Zapatos de taco",
}
SEASONS = {
    "Fall": "otoño", "Spring": "primavera", "Summer": "verano", "Winter": "invierno",
    "Tropical-Vacation": "vacaciones en clima cálido",
    "Cold_Weather-Vacation": "vacaciones en clima frío",
}


def generate_gtin(rng: random.Random) -> str:
    """GTIN-13 with the Argentine prefix and a correct GS1 check digit."""
    body = GS1_PREFIX_AR + "".join(str(rng.randint(0, 9)) for _ in range(9))
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(body))
    return body + str((10 - total % 10) % 10)


def product_name(row: dict, product_type: str) -> str:
    if product_type == "shoes":
        return SHOE_NAMES.get(row.get("style_silhouette", ""), "Calzado")
    return PRODUCT_NAMES[product_type]


def enrich_row(row: dict, product_type: str, rng: random.Random) -> dict:
    """Add the synthetic feed fields to the row."""
    product_id = row["id"]

    # Fields the brand declares
    row["brand"] = rng.choice(BRANDS)
    row["price"] = f"{rng.uniform(*PRICE_RANGE_ARS):.2f} ARS"
    row["gtin"] = generate_gtin(rng) if rng.random() < GTIN_SHARE else ""
    row["availability"] = "in_stock"
    row["link"] = f"{STORE_URL}?category={product_type}&product={product_id}"
    row["condition"] = "new"
    row["gender"] = rng.choice(list(GENDERS))
    row["material"] = rng.choice(list(MATERIALS))
    row["pattern"] = rng.choice(list(PATTERNS))
    row["color"] = rng.choice(list(COLORS))
    row["size"] = rng.choice(SIZES[product_type])
    row["age_group"] = "adult"

    # Fields the pipeline builds (Spanish wording, for the Argentine feed)
    row["google_product_category"] = CATEGORY_MAP[product_type]

    name = product_name(row, product_type)
    gender = GENDERS[row["gender"]]
    material = MATERIALS[row["material"]]
    color = COLORS[row["color"]]
    row["title"] = (
        f"{row['brand']} {name} {gender} de {material} {color} talle {row['size']}"
    )[:150]

    description = f"{name} de {material} en color {color}, {PATTERNS[row['pattern']]}."
    season = SEASONS.get(row.get("season", ""))
    if season:
        description += f" Pensado para {season}."
    row["description"] = description

    return row


def process_csv(source: Path, product_type: str, output: Path, rng: random.Random) -> None:
    print(f"Processing {product_type} from {source}...")
    with open(source, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [enrich_row(row, product_type, rng) for _, row in zip(range(MAX_ROWS), reader)]

    if not rows:
        print(f"  ERROR: no rows read from {source}")
        return

    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {len(rows)} rows in {output}")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    for product_type, source in SOURCES.items():
        process_csv(source, product_type, OUTPUT_DIR / f"{product_type}_google_500.csv", rng)


if __name__ == "__main__":
    main()
