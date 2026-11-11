# Milestone 3 contra Google Merchant Center: qué hicimos y cómo verlo

El 2 de noviembre de 2026 implementamos las llamadas reales a la Merchant API en
`positioner/publishing/` y las probamos de punta a punta. Subimos un producto del
CSV sintético a una cuenta de prueba de Merchant Center y Google lo aprobó.

Primero lo probamos para US, con el feed viejo en dólares. Cuando el feed pasó a
Argentina (precios en ARS, títulos en castellano), sumamos una fuente de datos y un
servicio de envíos para AR. Ahora `MerchantClient` usa `es` / `AR` por defecto.

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

- **M4.** Correr `scripts/publish_from_url.py` con los modelos reales contra esta
  cuenta de prueba. Usa las mismas variables de entorno de arriba, más
  `ANTHROPIC_API_KEY` para la descripción.
