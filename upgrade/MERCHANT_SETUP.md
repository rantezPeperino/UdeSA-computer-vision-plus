# Milestone 3 contra Google Merchant Center: qué hicimos y cómo verlo

El 2 de noviembre de 2026 implementamos las llamadas reales a la Merchant API en
`positioner/publishing/` y las probamos de punta a punta. Subimos un producto del
CSV sintético a una cuenta de prueba de Merchant Center y Google lo aprobó.

Primero lo probamos para US, con el feed viejo en dólares. Cuando el feed pasó a
Argentina (precios en ARS, títulos en castellano), sumamos una fuente de datos y un
servicio de envíos para AR. Ahora `MerchantClient` usa `es` / `AR` por defecto.

El 11 de noviembre corrimos la etapa 4 contra la misma cuenta: a partir de la URL de
una foto, el pipeline la atribuyó con los modelos reales y subió el producto, y Google
lo aprobó. Los pasos están en
[Cómo correr la etapa 4 con un producto real](#cómo-correr-la-etapa-4-con-un-producto-real).

## Cuentas e IDs

| Qué | Valor |
|---|---|
| Proyecto de Google Cloud | `udesa-toi` (número `334596132408`) |
| Service account | `merchant-uploader@udesa-toi.iam.gserviceaccount.com` |
| Cuenta real de Merchant Center | `5897867062` ("test-udesa-merchant"), sitio `https://matlock.github.io/` |
| **Cuenta de prueba** (acá van los productos) | `5897870917` ("UdeSA test") |
| **Fuente de datos para Argentina** (la que usa el código) | `10789583598` (idioma `es`, país `AR`) |
| Fuente de datos de la primera prueba | `10789365395` (idioma `en`, país `US`) |
| Producto para Argentina | `11885326`, "ElegantLine Pantalón unisex de poliéster verde talle L", 135444.24 ARS: **aprobado** |
| Producto de la primera prueba | `11888123`, "TrendWear Women's Navy Blue Denim Regular Fit Pant Trousers", en USD: **aprobado** |
| Producto de la etapa 4 (desde la URL de la foto) | `11876597`, "ElegantLine female Pants Loose-Fit-Pant navy blue XXL", 30029.69 ARS: **aprobado** |

La clave JSON de la service account **no está en el repo**. Cada uno la guarda en
`~/.config/google/` con permisos `600`, y nunca se commitea.

## Por qué hizo falta otro repo y una página en github.io

Google solo deja usar la Merchant API a proyectos registrados contra una cuenta
**real** de Merchant Center, y esa cuenta tiene que tener un **sitio web verificado**.
Las cuentas de prueba no se pueden registrar: se crean desde una cuenta real que ya
lo esté.

No teníamos sitio, así que creamos uno mínimo:

- El repo de este proyecto no sirve para eso. GitHub Pages solo publica la raíz o
  `/docs`. Además, la página quedaría en
  `rantezpeperino.github.io/UdeSA-computer-vision-plus/`, y Google busca la etiqueta
  de verificación en la página de inicio del dominio, que no es nuestra.
- Por eso creamos el repo `MatLock/matlock.github.io`, que GitHub publica en
  `https://matlock.github.io/`. Tiene una sola página: es la de `merchant-site/index.html`.
- En el `<head>` lleva la etiqueta `google-site-verification` que dio Merchant
  Center. **No hay que borrarla**: si se borra, Google pierde la verificación del sitio.

Merchant Center aceptó el subdominio de `github.io` sin problemas.

## Cómo ver la service account en Google Cloud

1. Entrá a [console.cloud.google.com](https://console.cloud.google.com) y elegí el
   proyecto **udesa-toi** en el selector de arriba a la izquierda.
2. Menú ☰ → **IAM y administración → Cuentas de servicio**. Ahí está
   `merchant-uploader`. Las claves se manejan en la pestaña **Claves**.
3. Menú ☰ → **APIs y servicios → APIs y servicios habilitados**. Ahí tiene que figurar
   **Merchant API**.

La service account no tiene roles en Google Cloud: sus permisos se los da Merchant
Center, donde es administradora de las dos cuentas.

## Cómo ver el producto en Merchant Center

1. Entrá a [merchants.google.com](https://merchants.google.com) con tu cuenta de Google.
2. Arriba a la derecha, cambiá a la cuenta **UdeSA test** (`5897870917`). La cuenta
   "test-udesa-merchant" no tiene productos.
3. Andá a **Productos → Todos los productos**.

El producto **no aparece en Google**: las cuentas de prueba nunca publican nada, ni
en Shopping, ni en Búsqueda, ni en ningún otro servicio. Solo se ve dentro de Merchant
Center.

## Cómo subir productos desde el código

```bash
export GOOGLE_SERVICE_ACCOUNT_PATH=~/.config/google/<clave>.json
export MERCHANT_ID=5897870917
export MERCHANT_DATA_SOURCE_ID=10789583598
```

```python
from positioner.publishing.credential_loader import load_credentials
from positioner.publishing.environment import get_environment
from positioner.publishing.merchant_client import MerchantClient

client = MerchantClient(load_credentials(), get_environment())
results = client.upload_feed(report, products)        # report y products salen de M2
statuses = client.get_product_statuses([p.id for p in products])
```

Google tarda entre 30 segundos y unos minutos en procesar cada producto. Mientras
tanto, `get_product_statuses` devuelve `pending`.

## Cómo correr la etapa 4 con un producto real

`scripts/publish_from_url.py` toma la URL de la foto y los datos de la marca, baja
la imagen, la atribuye con los modelos del prototipo, genera la descripción con un
modelo de lenguaje, valida la ficha, la sube a la cuenta de prueba y espera el
veredicto de Google. Todos los comandos se corren desde la raíz del repo, con el
`.venv` activado.

### 1. Instalar las dependencias de los modelos (una sola vez)

```bash
pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cpu
pip install transformers==5.12.0 scikit-learn==1.8.0 openai==2.41.1 anthropic==0.96.0
```

Son las versiones de `deep-tagger-api/requirements.txt`. La primera línea instala
`torch` para CPU: no hace falta GPU, y así se evitan los ~2 GB de CUDA. En la primera
corrida, `transformers` baja el modelo BLIP de Hugging Face, así que tarda más.

### 2. Configurar las credenciales

Las de Merchant Center, como en la sección anterior:

```bash
export GOOGLE_SERVICE_ACCOUNT_PATH=~/.config/google/<clave>.json
export MERCHANT_ID=5897870917
export MERCHANT_DATA_SOURCE_ID=10789583598
```

Y la del modelo que genera la descripción: OpenAI o Claude. Nosotros usamos OpenAI,
con la clave guardada en `openai_key.txt` en la raíz del repo. Ese archivo está en
`.gitignore` y **nunca se commitea**; conviene dejarlo con permisos `600`. Se carga
así, sin mostrarla en la terminal:

```bash
export OPENAI_API_KEY="$(tr -d '[:space:]' < openai_key.txt)"
export LLM_PROVIDER=openai      # o anthropic, con ANTHROPIC_API_KEY
```

Sin una clave el script no sube nada, porque la descripción saldría como texto de
relleno. Con `--dry-run` corre igual.

### 3. Elegir un producto

Los datos de la marca salen del feed sintético
([`data/pants_google_500.csv`](data/README.md), o el de calzado o tops). Para ver una
fila:

```bash
python -c "import csv; print(next(csv.DictReader(open('upgrade/data/pants_google_500.csv'))))"
```

| Columna del CSV | Argumento del script |
|---|---|
| `image_url` | primer argumento (la URL de la foto) |
| `id` | `--id` |
| `brand` | `--brand` |
| `price` | `--price` |
| `link` | `--link` |
| `size` | `--size` |
| `gender` | `--gender` |
| `color`, `material`, `pattern`, `gtin` | `--color`, `--material`, `--pattern`, `--gtin` (opcionales) |

`title` y `description` no se usan: el pipeline los genera a partir de la foto.
Subir un `id` que ya está en la cuenta (por ejemplo, `11876597` o `11885326`)
reemplaza ese producto.

### 4. Probar sin subir

```bash
python scripts/publish_from_url.py \
  "https://asset1.ruecdn.com/images/product/151188/1511885746_RLLDTH_1.jpg" \
  --id 11876597 --brand ElegantLine --price "30029.69 ARS" \
  --link "https://matlock.github.io/?category=pants&product=11876597" \
  --size XXL --gender female --color "navy blue" --material Polyester --pattern Striped \
  --dry-run
```

Muestra los atributos inferidos, el título y la descripción, y dice si la ficha pasa
la validación. No necesita las credenciales de Merchant Center.

### 5. Subir

El mismo comando, sin `--dry-run`. Después de subir, el script consulta el estado
cada 15 segundos durante 5 minutos como máximo (se cambia con `--wait SECONDS`;
`--wait 0` no espera). Sale con código 0 si el producto quedó subido o aprobado,
1 si una etapa falló o Google lo rechazó, y 2 si falta una credencial.

### 6. Si quedó en `pending`

Un producto nuevo suele quedar un rato con `image_link_pending_crawl`, mientras Google
baja la imagen. Con el `11876597` tardó más de los 5 minutos del script. Para
consultarlo más tarde:

```bash
python -c "
from positioner.publishing.credential_loader import load_credentials
from positioner.publishing.environment import get_environment
from positioner.publishing.merchant_client import MerchantClient
print(MerchantClient(load_credentials(), get_environment()).get_product_statuses(['11876597']))"
```

El producto también se ve en Merchant Center, como se explica en
[Cómo ver el producto en Merchant Center](#cómo-ver-el-producto-en-merchant-center).

## Cómo correr la etapa 4 con un CSV

`scripts/publish_from_csv.py` hace lo mismo que `publish_from_url.py` para cada fila
de un CSV. Necesita las mismas dependencias y credenciales (pasos 1 y 2 de la
sección anterior).

El CSV lleva una prenda por fila, con estas columnas:

| Columna | |
|---|---|
| `image_url` (o `url`) | URL pública de la foto |
| `brand`, `price`, `link` | el precio con moneda, por ejemplo `45999.00 ARS` |
| `size`, `gender` | Google los exige para ropa y ningún modelo los infiere |
| `id` | opcional; si está vacío, sale de la URL de la foto |
| `color`, `material`, `pattern`, `gtin`, `availability`, `condition`, `age_group` | opcionales |

Los feeds sintéticos de `upgrade/data/` ya tienen esa forma. El resto de las columnas
(`title`, `description`, etc.) se ignora: el pipeline las genera desde la foto.

```bash
# Probar sin subir, con las primeras 3 filas
python scripts/publish_from_csv.py upgrade/data/pants_google_500.csv --dry-run --limit 3

# Subir
python scripts/publish_from_csv.py upgrade/data/pants_google_500.csv --limit 3
```

- Si al CSV le falta una columna obligatoria o tiene dos filas con el mismo `id`,
  corta antes de cargar los modelos.
- Una fila que falla (foto que no baja, ficha inválida, error del modelo de lenguaje)
  no frena las demás.
- Al terminar de subir, espera el veredicto de Google de todos los productos
  subidos (`--wait SECONDS`, 300 por defecto; `--wait 0` no espera).
- Escribe una línea por fila en `<entrada>_results.csv`, junto al CSV de entrada
  (se cambia con `--out`): etapa en la que terminó, estado en Merchant Center,
  motivos, y el título, la categoría y la descripción generados. Si se corta con
  Ctrl-C, guarda las filas ya procesadas.
- Sale con código 0 si todas las filas se subieron y ninguna fue rechazada, 1 si
  alguna falló o fue rechazada, y 2 si el CSV es inválido o falta una credencial.
Ahí aparecen el título, la descripción, la categoría de Google y los datos de la
marca. El calce, los bolsillos y la temporada que infieren los modelos no tienen campo
propio en Merchant Center: solo aparecen dentro del título y la descripción.

## Pasos de configuración que hicimos por API

Se hacen una sola vez y ya están hechos. Los dejamos anotados por si hay que repetirlos
en otra cuenta. Todos usan la service account.

1. **Registro del proyecto**: `developerRegistration:registerGcp` sobre la cuenta real.
2. **Cuenta de prueba**: `createTestAccount` desde la cuenta real.
3. **Términos de Servicio**: `termsOfService/135:accept` para la cuenta de prueba
   (región US). Tardaron unos 4 minutos en propagarse. Para publicar en Argentina no
   hizo falta aceptar los de AR: la región del negocio de la cuenta es US.
4. **Fuentes de datos**: dos de tipo API. La de `es` / `AR` coincide con los valores
   por defecto de `MerchantClient`; la de `en` / `US` quedó de la primera prueba.
   Cada producto tiene que ir a la fuente de su idioma y país.
5. **Sitio de la cuenta de prueba**: `https://matlock.github.io/`. Los links de los
   productos tienen que ser de ese mismo dominio.
6. **Envíos**: dos servicios de envío gratis, uno a US en USD y otro a AR en ARS.
   La configuración se reemplaza entera, así que cada `insert` tiene que llevar todos
   los servicios. Hay que indicar `shipment_type: DELIVERY`: sin ese campo, Google
   responde OK pero no guarda nada. Lo mismo pasó con el servicio de AR cuando se
   llamaba "Estándar AR"; con el nombre sin tilde se guardó.

## Pendientes

- **Idioma de la ficha.** En la etapa 4, el título y la descripción salen en inglés
  ("female Pants", "Effortless sophistication…"), aunque el producto se publica en la
  fuente `es` / `AR`. Hay que pedirle la descripción en castellano al modelo de
  lenguaje y traducir las partes del título.
