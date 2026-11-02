# Milestone 3 contra Google Merchant Center: qué hicimos y cómo verlo

El 2 de noviembre de 2026 implementamos las llamadas reales a la Merchant API en
`positioner/publishing/` y las probamos de punta a punta. Subimos un producto del
CSV sintético a una cuenta de prueba de Merchant Center y Google lo aprobó.

## Cuentas e IDs

| Qué | Valor |
|---|---|
| Proyecto de Google Cloud | `udesa-toi` (número `334596132408`) |
| Service account | `merchant-uploader@udesa-toi.iam.gserviceaccount.com` |
| Cuenta real de Merchant Center | `5897867062` ("test-udesa-merchant"), sitio `https://matlock.github.io/` |
| **Cuenta de prueba** (acá van los productos) | `5897870917` ("UdeSA test") |
| Fuente de datos de tipo API | `10789365395` (idioma `en`, país `US`) |
| Producto subido | `11888123`, "TrendWear Women's Navy Blue Denim Regular Fit Pant Trousers": **aprobado** |

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
export MERCHANT_DATA_SOURCE_ID=10789365395
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
   (región US). Tardaron unos 4 minutos en propagarse.
4. **Fuente de datos**: una fuente de tipo API, con idioma `en` y país `US`, que
   coinciden con los valores por defecto de `MerchantClient`.
5. **Sitio de la cuenta de prueba**: `https://matlock.github.io/`. Los links de los
   productos tienen que ser de ese mismo dominio.
6. **Envíos**: un servicio de envío gratis a US. Hay que indicar
   `shipment_type: DELIVERY`. Sin ese campo, Google responde OK pero no guarda nada.

## Pendientes

- **M4.** Las cuentas de prueba de Merchant Center no se pueden vincular a Google Ads.
  Para probar campañas va a hacer falta usar la cuenta real.
- **Ruben.** No está invitado porque su Hotmail no tiene una cuenta de Google asociada.
