# Pipeline de posicionamiento en Google Shopping

Esta carpeta especifica la extensión del prototipo: pasar de un generador de atributos a partir de una foto a un pipeline que, a partir de la URL de una foto, lleva la prenda hasta Google Merchant Center. El código está en [`positioner/`](../positioner/). El porqué, a quién le sirve y qué no sabemos todavía está en el [canvas](../canvas.md), sección 3.

## Contenido

| Archivo | Qué tiene |
|---|---|
| [`proposal.md`](proposal.md) | Por qué, qué cambia y qué queda afuera |
| [`requirements.md`](requirements.md) | Qué hace falta para correrlo contra Google, en cuentas de prueba (gratis) y en producción (pago) |
| [`tasks.md`](tasks.md) | Tareas por etapa y su estado |
| [`specs/`](specs/) | Un spec por etapa, con los escenarios y el test que cubre cada uno |
| [`data/`](data/) | Feed sintético de 1.500 productos para probar las etapas 2 a 4 |
| [`generate_synthetic_data.py`](generate_synthetic_data.py) | Regenera el feed sintético |

## Las cuatro etapas

```
Foto + datos de la marca
   │
   ▼
1 · Enriquecimiento   → tipo de prenda, color, atributo, título, descripción, categoría de Google
2 · Feed              → esquema de Merchant Center + validación de cada fila
3 · Publicación       → credenciales, cuenta de prueba por defecto, solo filas válidas, estado de aprobación
4 · Automatización   → de la URL de la foto a Merchant Center: descarga, atributos, validación, subida y veredicto
```

Cada etapa usa la salida de la anterior y se prueba por separado.

| Etapa | Spec | Código | Escenarios |
|---|---|---|---|
| 1 · Enriquecimiento | [`specs/product-enrichment/spec.md`](specs/product-enrichment/spec.md) | `positioner/enrichment/` | 6 |
| 2 · Feed | [`specs/merchant-feed/spec.md`](specs/merchant-feed/spec.md) | `positioner/feed/` | 9 |
| 3 · Publicación | [`specs/merchant-publishing/spec.md`](specs/merchant-publishing/spec.md) | `positioner/publishing/` | 6 |
| 4 · Automatización | [`specs/url-to-merchant/spec.md`](specs/url-to-merchant/spec.md) | `positioner/automation/`, `scripts/publish_from_url.py` | 10 |

## Qué campos genera el pipeline y cuáles declara la marca

| Origen | Campos |
|---|---|
| Se infieren de la foto | `google_product_category` (a partir del tipo de prenda de TinyVGG), color (K-Means), atributo del título (clasificador multilabel), `title` y `description` (Claude) |
| Los declara la marca | `brand`, `price`, `gtin` (si la prenda lo tiene), `availability`, `link`, `condition`, `gender`, `material`, `pattern`, `size`, `age_group` |

Ningún modelo del prototipo predice género, material ni estampa, así que el pipeline los toma de la marca y nunca los inventa. Si la marca declara el color, ese color va al feed; el predicho se guarda aparte (`predicted_color`) para poder compararlos.

## Estado

- La lógica de las cuatro etapas está escrita y sus 31 escenarios pasan, con las APIs de Google simuladas.
- Las llamadas a Merchant API (`_upload_product`, `_get_status`) son reales y se probaron contra una cuenta de prueba de Merchant Center ([`MERCHANT_SETUP.md`](MERCHANT_SETUP.md)).
- La etapa 4 encadena las tres anteriores para una prenda: `scripts/publish_from_url.py` recibe la URL de la foto y los datos de la marca, y sube el producto a Merchant Center. Se corrió con los modelos reales contra la cuenta de prueba el 2026-11-11: el producto `11876597` quedó aprobado. Paso a paso en [`MERCHANT_SETUP.md`](MERCHANT_SETUP.md#cómo-correr-la-etapa-4-con-un-producto-real).
- Las campañas de Google Ads quedaron fuera del alcance: crear una campaña y medir sus resultados cuesta dinero ([bitácora del canvas](../canvas.md#bitácora-de-revisiones), 2026-11-11).

## Cómo se corren los tests

Desde la raíz del repo, sin GPU, sin red y sin credenciales:

```bash
python -m unittest discover -s positioner/tests -t .     # los 38 tests
python scripts/spec_report.py                            # los specs con cada escenario tildado
python scripts/spec_report.py --estricto               # además, falla si un escenario no tiene test
```

`spec_report.py` sale con código 1 si algún escenario falla, así que puede correr en CI.

## Convenciones de los specs

- Siguen el formato OpenSpec, en inglés: requisitos con `SHALL` (estilo EARS), todos como `## ADDED Requirements`.
- Cada escenario es un bloque `#### Scenario:` con sus pasos `WHEN`/`IF`/`THEN` y una línea `- **TEST** \`nombre_del_test\`` con el test que lo cubre. Un escenario sin esa línea aparece como `sin test` en el reporte.
