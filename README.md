# Deep Tagger: de la foto a Google Shopping

Proyecto de la materia Teoría de la Información (Universidad de San Andrés). Toma la foto de una prenda y los datos que declara la marca, genera la ficha del producto y la lleva hasta Google: feed de Merchant Center validado, publicación y campañas de Shopping con una regla de optimización.

Está pensado para quien carga el catálogo en una marca argentina de indumentaria chica o mediana. El problema, los stakeholders, las hipótesis y lo que todavía no sabemos están en el [canvas](canvas.md).

Este repo es un fork de [MatLock/UdeSA-computer-vision](https://github.com/MatLock/UdeSA-computer-vision), el prototipo original (`deep-tagger-api`, `deep-tagger-ui`, `img-puller`).

## Demo

<video src="https://github.com/user-attachments/assets/6f47bd3f-877b-4ed3-bb6f-0f218e168935" controls width="720"></video>

---

## Qué hace

```
Foto + datos de la marca
   │
   ▼
┌──────────────────────────────────┐
│  Deep Tagger API (prototipo)     │
│  TinyVGG · ResNet · K-Means ·    │
│  BLIP · Claude                   │
│  tipo, atributos, color,         │
│  título, descripción             │
└────────────────┬─────────────────┘
                 ▼
┌──────────────────────────────────┐
│  1 · Enriquecimiento             │  positioner/enrichment/
│  categoría de Google, título     │
│  con orden fijo, color declarado │
│  y predicho                      │
└────────────────┬─────────────────┘
                 ▼
┌──────────────────────────────────┐
│  2 · Feed                        │  positioner/feed/
│  esquema de Merchant Center,     │
│  campos obligatorios, precio,    │
│  GTIN                            │
└────────────────┬─────────────────┘
                 ▼
┌──────────────────────────────────┐
│  3 · Publicación                 │  positioner/publishing/
│  credenciales, cuenta de prueba  │
│  por defecto, estado de          │
│  aprobación                      │
└────────────────┬─────────────────┘
                 ▼
┌──────────────────────────────────┐
│  4 · Automatización              │  positioner/automation/
│  de la URL de la foto a Merchant │  scripts/publish_from_url.py
│  Center, de punta a punta        │
└──────────────────────────────────┘
```

**Estado:** la lógica de las cuatro etapas está escrita y sus 31 escenarios pasan con las APIs de Google simuladas. Las llamadas a Merchant API (etapa 3) ya son reales y se probaron contra una cuenta de prueba ([`upgrade/MERCHANT_SETUP.md`](upgrade/MERCHANT_SETUP.md)). La etapa 4 encadena las tres para una foto, y ya se corrió con los modelos reales contra la cuenta de prueba: el producto `11876597` quedó aprobado. Las campañas de Google Ads quedaron fuera de alcance porque cuestan dinero ([`upgrade/README.md`](upgrade/README.md), sección Estado).

---

## Estructura

```
canvas.md               # AI Opportunity Canvas del proyecto
hito-2/                 # Entregables del Hito 2: mapa de fuentes, EDA, datasheet y veredicto
data/                   # Muestra del Hito 2, planilla de re-etiquetado y caché del chequeo de URLs
notebooks/              # Notebook del EDA de viabilidad
scripts/                # Regeneración de la muestra, reporte de specs, pipeline de la etapa 4 y entrenamiento nocturno
deep-tagger-api/        # Backend FastAPI del prototipo
deep-tagger-ui/         # Frontend React del prototipo
img-puller/             # Descarga de imágenes y CSV etiquetados del prototipo
positioner/             # Pipeline de posicionamiento en Google
  enrichment/           #   1: enriquecimiento
  feed/                 #   2: esquema de Merchant Center y validación
  publishing/           #   3: publicación en Merchant Center
  automation/           #   4: de la URL de la foto a Merchant Center
  tests/                #   38 tests (sin GPU, sin red, sin credenciales)
upgrade/                # Propuesta, requisitos, tareas, specs y feed sintético del pipeline
```

---

## Prototipo

### Deep Tagger API

Backend FastAPI que encadena cinco modelos sobre una URL de imagen:

- **TinyVGG**: tipo de prenda, entrenado con Fashion-MNIST (10 clases).
- **ResNet-18 multilabel**: atributos para tops (cuello, calce, temporada), calzado (ocasión, silueta, temporada) y pantalones (bolsillos, calce, temporada). No predice material, género ni estampa.
- **K-Means**: color dominante, con un solo grupo de color.
- **BLIP**: título.
- **Claude**: descripción.

Endpoint: `POST /predict-image` → `{ product_type, title, description, tags }`. Instalación en [`deep-tagger-api/README.md`](deep-tagger-api/README.md).

### Deep Tagger UI

Aplicación React para mandar URLs de imágenes y ver los tags generados. Instalación en [`deep-tagger-ui/README.md`](deep-tagger-ui/README.md).

### Image Puller

CLI en Python que baja las imágenes de los CSV etiquetados y anota la ruta local de cada una. Ver [`img-puller/README.md`](img-puller/README.md).

---

## Pipeline de posicionamiento (`positioner/`)

La especificación completa está en [`upgrade/`](upgrade/README.md).

### Qué se infiere y qué declara la marca

| Origen | Campos |
|---|---|
| Se infieren de la foto | `google_product_category`, color, atributo del título, `title`, `description` |
| Los declara la marca | `brand`, `price`, `gtin` (si la prenda lo tiene), `availability`, `link`, `condition`, `gender`, `material`, `pattern`, `size`, `age_group` |

Lo que declara la marca no se inventa: pasa tal cual al feed. Si la marca declara el color, ese es el que se publica; el predicho queda en `predicted_color` para compararlos.

### 1 · Enriquecimiento

```python
from positioner.enrichment.field_generator import enrich_product

row = {
    "image_url": "https://example.com/producto.jpg",
    "brand": "StyleCo",
    "size": "M",
    "gender": "female",
    "material": "Cotton",
}
result = enrich_product(row)
# result.google_product_category, result.title, result.color, result.predicted_color ...
# result.status → "ok" | "partial" | "needs_category_review"
```

El título sigue el orden `marca + género + prenda + atributo + color + talle` y omite las partes que faltan.

### 2 · Feed

Une lo enriquecido con los datos de la marca, lo lleva al esquema de Merchant Center y valida cada fila.

- **Campos obligatorios de la marca:** `brand`, `price`, `availability`, `link`, `condition`. El `gtin` es opcional, porque Google lo pide solo para los productos que lo tienen.
- **Validaciones:** campos obligatorios de indumentaria (`missing_<campo>`), formato de precio `"45999.00 ARS"` (`price_format`) y dígito verificador del GTIN-13 cuando hay uno (`gtin_format`).

```python
from positioner.feed.schema_mapper import map_to_merchant, validate_business_fields
from positioner.feed.validator import validate_row
from positioner.feed.report import build_report

validate_business_fields(business_row)           # ValueError si falta un campo obligatorio
product = map_to_merchant(enriched, business_row, row_id="123")
result  = validate_row(product)                  # ValidationResult(valid, reasons)
report  = build_report([result, ...])            # valid_count + invalid_count == N
```

### 3 · Publicación

Sube el feed validado a Google Merchant Center con la Merchant API. Las credenciales salen solo de variables de entorno, nunca del repo:

```bash
GOOGLE_SERVICE_ACCOUNT_PATH=/ruta/a/la/clave.json
MERCHANT_ID=123456789
MERCHANT_DATA_SOURCE_ID=987654   # fuente de datos de tipo API en Merchant Center (para subir)
MERCHANT_ENV=test          # o "production"
```

```python
from positioner.publishing.credential_loader import load_credentials
from positioner.publishing.environment import get_environment
from positioner.publishing.merchant_client import MerchantClient

creds    = load_credentials()                    # falla antes de cualquier llamada si falta algo
env      = get_environment()                     # por defecto, TEST
client   = MerchantClient(creds, env)
results  = client.upload_feed(report, products)  # saltea las filas inválidas
statuses = client.get_product_statuses(ids)      # approved / disapproved / pending
```

Probado de punta a punta contra una cuenta de prueba de Merchant Center: las cuentas, la configuración y dónde ver los productos están en [`upgrade/MERCHANT_SETUP.md`](upgrade/MERCHANT_SETUP.md).

### 4 · Automatización: de la URL a Merchant Center

Encadena las tres etapas para una prenda. Dada la URL de la foto y los datos de la marca: revisa los datos obligatorios, descarga la imagen, la atribuye con los modelos del prototipo, valida la ficha, la sube a Merchant Center y espera a que Google la apruebe o la rechace. Se corta en la primera etapa que falla. La misma URL da siempre el mismo id de producto, así que correrlo dos veces actualiza el producto en vez de duplicarlo.

Necesita las dependencias de `deep-tagger-api`, las variables de entorno de la etapa 3 y una clave para generar la descripción: `OPENAI_API_KEY` o `ANTHROPIC_API_KEY` (con `LLM_PROVIDER=openai` o `anthropic` se elige uno si están las dos):

```bash
python scripts/publish_from_url.py "https://.../foto.jpg" \
    --brand StyleCo --price "45999.00 ARS" \
    --link "https://matlock.github.io/?product=123" \
    --size M --gender female

# Arma y valida la ficha sin subirla (no hacen falta credenciales):
python scripts/publish_from_url.py "https://.../foto.jpg" ... --dry-run
```

```python
from positioner.automation.pipeline import run_pipeline, wait_for_status

result = run_pipeline(image_url, business_row, client=client)   # result.stage: uploaded, invalid, ...
status = wait_for_status(client, result.product_id)             # approved / disapproved / pending
```

Paso a paso para correrlo con un producto real (dependencias, credenciales, cómo sacar los datos de una fila del feed sintético y cómo consultar el estado después): [`upgrade/MERCHANT_SETUP.md`](upgrade/MERCHANT_SETUP.md#cómo-correr-la-etapa-4-con-un-producto-real).

Las campañas de Google Ads quedaron fuera de alcance: crear una campaña y medir sus resultados cuesta dinero.

---

## Tests

Sin GPU, sin red y sin credenciales: todas las llamadas externas están simuladas.

```bash
# Desde la raíz del repo
python -m unittest discover -s positioner/tests -t . -v   # los 38 tests

python -m unittest positioner.tests.test_enrichment -v     # 1 · 6 tests
python -m unittest positioner.tests.test_feed -v           # 2 · 9 tests
python -m unittest positioner.tests.test_publishing -v     # 3 · 13 tests
python -m unittest positioner.tests.test_automation -v     # 4 · 10 tests
```

Para ver los resultados contra los specs, con cada escenario tildado:

```bash
python scripts/spec_report.py                                       # todas las etapas
python scripts/spec_report.py upgrade/specs/merchant-feed/spec.md   # una etapa
python scripts/spec_report.py --no-steps                           # sin los pasos WHEN/THEN
python scripts/spec_report.py --strict                            # falla también si un escenario no tiene test
```

Sale con código 1 si algún escenario falla, así que puede correr en CI.

---

## Contra Google, en cuentas de prueba

Google ofrece cuentas de prueba gratuitas de Merchant Center. Los pasos para armarlas están en [`upgrade/requirements.md`](upgrade/requirements.md). Para probar sin datos de una marca real hay un feed sintético de 1.500 productos en [`upgrade/data/`](upgrade/data/README.md), que se regenera con:

```bash
python upgrade/generate_synthetic_data.py
```

| | Gratis (cuentas de prueba) | Pago (producción) |
|---|---|---|
| Merchant Center | Cuenta de prueba | Cuenta real verificada |
| Datos | Sirve el feed sintético | Precios, links y stock reales; GTIN si la prenda lo tiene |

La publicación en Merchant Center ya se puede probar de punta a punta ([`upgrade/MERCHANT_SETUP.md`](upgrade/MERCHANT_SETUP.md)).

---

## Autores

Jorge Federico Flores — jfflores90@gmail.com

Nilayvi Barrientos — nilayvi@gmail.com

Nicolás Velázquez — nicoj.velazquez@gmail.com

Rubén Ortigoza — ortigozaruben@hotmail.com
