"""Builds the sheet and the viewer for human re-labeling (reliability, cell R6).

Picks 60 images from the downloaded subset (20 per category, fixed seed) and
writes, into data/etiquetado/:
  - planilla_base.csv: id, categoria, ruta_imagen and one empty column per
    attribute, plus tipo_foto, color_principal and coincide_categoria.
  - visor.html: a local page that shows each image with options from the
    prototype's taxonomy and exports etiquetador_A.csv or etiquetador_B.csv. It
    does not show the original label, to avoid bias.

The output file names, the columns and the options shown to the labelers stay in
Spanish: they are the committed data and the labelers' interface, and the EDA
notebook reads them.

Usage (from the repo root, after scripts/download_images.py):
    python scripts/build_labeling_sheet.py
"""

import json
from pathlib import Path

import pandas as pd

SEED = 42
PER_CATEGORY = 20
ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "muestra"
OUTPUT = ROOT / "data" / "etiquetado"
ATTRIBUTES = {
    "tops": ["neck_style", "fit_silhouette", "season"],
    "shoes": ["wearing_occasion", "style_silhouette", "season"],
    "pants": ["pocket_details", "fit_silhouette", "season"],
}
ALL_ATTRIBUTES = list(dict.fromkeys(a for v in ATTRIBUTES.values() for a in v))
# Extra columns, with the options the labelers pick from (in Spanish, as they see them).
EXTRAS = {
    "tipo_foto": ["packshot", "con modelo", "otra"],
    "color_principal": ["negro", "blanco", "gris", "beige", "marrón", "azul", "celeste", "verde", "rojo",
                        "rosa", "violeta", "amarillo", "naranja", "dorado/plateado", "multicolor/estampado"],
    "coincide_categoria": ["sí", "no"],
}
# Option added to every attribute group: "other / not visible".
OTHER_OPTION = "otro / no se ve"


def main():
    subset = pd.read_csv(SAMPLE / "subconjunto_imagenes.csv", dtype=str)
    chosen = (pd.concat(subset[subset["categoria"] == cat].sample(n=PER_CATEGORY, random_state=SEED)
                        for cat in ATTRIBUTES)
                .sample(frac=1, random_state=SEED))           # shuffled, so labeling is not done in blocks
    base = chosen[["id", "categoria"]].copy()
    base["ruta_imagen"] = chosen["ruta"]
    for col in ALL_ATTRIBUTES + list(EXTRAS):
        base[col] = ""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    base.to_csv(OUTPUT / "planilla_base.csv", index=False)

    taxonomy = {}
    for cat in ATTRIBUTES:
        meta = json.loads((SAMPLE / "taxonomia" / f"{cat}.labels.json").read_text(encoding="utf-8"))
        taxonomy[cat] = {g["name"]: g["classes"] + [OTHER_OPTION] for g in meta["groups"]}

    items = [{"id": r.id, "categoria": r.categoria, "img": "../../" + r.ruta_imagen} for r in base.itertuples()]
    html = (Path(__file__).with_name("visor_plantilla.html").read_text(encoding="utf-8")
            .replace("__ITEMS__", json.dumps(items))
            .replace("__TAXONOMIA__", json.dumps(taxonomy, ensure_ascii=False))
            .replace("__ATRIBUTOS__", json.dumps(ATTRIBUTES))
            .replace("__EXTRAS__", json.dumps(EXTRAS, ensure_ascii=False))
            .replace("__COLUMNAS__", json.dumps(list(base.columns))))
    (OUTPUT / "visor.html").write_text(html, encoding="utf-8")
    print(f"{len(base)} images -> {OUTPUT.relative_to(ROOT)}/planilla_base.csv and visor.html")


if __name__ == "__main__":
    main()
