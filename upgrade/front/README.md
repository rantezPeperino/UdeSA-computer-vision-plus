# Monitor de lotes: cómo funciona y qué significa cada valor

El monitor es una pantalla web que ejecuta `scripts/publish_from_csv.py` y muestra en
vivo lo que el script va haciendo. No reemplaza ni cambia el script: corre el mismo
código, con las mismas opciones, y lo que ves en pantalla sale de lo que el script
hace e imprime. El resultado es el mismo que en la terminal.

## Arrancar y parar

```bash
bash upgrade/front/start.sh      # levanta el front y abre http://127.0.0.1:8000
bash upgrade/front/stop.sh       # lo para
```

- La primera vez, `start.sh` crea `upgrade/front/.venv` e instala las dependencias.
  Tarda varios minutos, por torch y paddle.
- Las keys y las credenciales se leen de `upgrade/front/.env`, que git ignora, o de
  las variables exportadas en la terminal:
  - `OPENAI_API_KEY` o `ANTHROPIC_API_KEY`, y `LLM_PROVIDER`;
  - `GOOGLE_SERVICE_ACCOUNT_PATH`, `MERCHANT_ID` y `MERCHANT_DATA_SOURCE_ID`.
- Sin keys ni credenciales solo funciona la opción "No subir a Merchant Center".

## 1. Pantalla "Nuevo lote"

**Archivo o carpeta**
- Con un CSV, el script corre una vez.
- Con una carpeta, toma solo los `.csv` del primer nivel (no entra en subcarpetas).
  Los procesa de a uno y en orden alfabético, y el script corre una vez por cada CSV.

**Columnas del CSV**
- Obligatorias: `image_url` (o `url`), `brand`, `price`, `link`, `size` y `gender`.
- Opcionales: `id`, `color`, `material`, `pattern`, `gtin`, `availability`,
  `condition` y `age_group`.
- Si `id` está vacío, el script lo arma a partir de la URL de la foto.
- El formato de `price` es `número MONEDA`, por ejemplo `45999.00 ARS`.
- Ejemplos: `upgrade/data/sdd_spec_sample/`.

**Opciones** (son las del script)

| En pantalla | Opción del script | Qué hace |
|---|---|---|
| No subir a Merchant Center | `--dry-run` | Arma y valida cada producto, pero no sube nada. No pide credenciales. |
| Procesar solo las primeras N filas | `--limit N` | Vacío = todas las filas. |
| Esperar el veredicto de Google | `--wait S` | Cuántos segundos esperar a que Google apruebe o rechace (por defecto 300). `0` = no esperar. |
| Archivo de resultados | `--out` | Solo con un CSV. Por defecto es `<nombre>_results.csv`. |

## 2. Pantalla de la ejecución

### Encabezado
- **Estado:**
  - Procesando: el script está corriendo.
  - Interrumpiendo…: se pidió cortar y está terminando la fila en curso.
  - Interrumpido: se cortó antes de terminar.
  - Terminado: procesó todos los archivos.
- **Transcurrido / Duró:** el tiempo desde que empezó.
- **Interrumpir:** equivale a Ctrl-C en el script. Corta en el próximo punto seguro y
  guarda en el CSV de resultados las filas que ya terminaron. Si es una carpeta, los
  archivos que faltaban no se procesan.

### Archivos
Una fila por CSV, con su estado, una barra de filas terminadas sobre el total y una
nota con los conteos. Al hacer clic en un archivo, el resto de la pantalla muestra ese
archivo.

| Estado | Significado |
|---|---|
| En espera | Todavía no le tocó. |
| Procesando | El script está corriendo sobre este archivo. |
| Salida 0 | Todo se subió (o pasó la validación, con "No subir") y Google no rechazó nada. |
| Salida 1 | Alguna fila no llegó al final, o Google rechazó algún producto. |
| Salida 2 | El script frenó antes de procesar filas: CSV mal formado, falta la key del LLM o faltan las credenciales. |
| Interrumpido | Se cortó con "Interrumpir". |

Son los mismos códigos de salida que devuelve el script en la terminal.

### El camino
Son los pasos del script, en tres fases. Cada círculo es un paso y tiene un estado:

| Aspecto del círculo | Estado |
|---|---|
| Blanco con borde gris | Sin empezar. |
| Azul que va hasta blanco y vuelve, con ondas | **En curso**: es el paso que se está ejecutando ahora. |
| Verde claro | Ya pasaron filas por acá, pero el archivo sigue en curso. |
| Verde | Terminado. |
| Rojo | Falló y frenó el archivo. |
| Borde punteado | Salteado: el paso no corre con las opciones elegidas. |
| Marca amarilla `!` | Algunas filas se quedaron en este paso. El texto de abajo dice cuántas y por qué. |
| Marca roja `✕` | Este paso falló. |

**1 · Preparación** (una vez por archivo)

| Paso | Qué hace el script | Texto debajo |
|---|---|---|
| Leer el CSV | Lee y revisa el archivo: columnas, fotos vacías, IDs repetidos. | `N prendas`, o `salida 2` si el archivo está mal. |
| Clave del LLM y Merchant Center | Revisa la key del LLM y se conecta a Merchant Center. Con "No subir" se saltea. | Proveedor del LLM · cuenta · ambiente (`test` o `production`). |
| Cargar los modelos | Carga los modelos que miran la foto. Pasa con la primera fila que llega a la atribución. | Cuánto tardó. |

**2 · Por cada fila** (se repite fila por fila). Arriba a la derecha dice `N de M`.

| Paso | Qué hace el script | Texto debajo |
|---|---|---|
| Revisar los datos de la marca | Controla que la fila traiga los campos obligatorios. | `N ok`, y las que no pasaron (`invalid`). |
| Bajar la foto y atribuirla | Baja la foto; los modelos detectan prenda, color y atributos, y el LLM escribe la descripción. | `N ok`, y las que fallaron (`download_failed`, `error`). |
| Armar y validar el producto | Arma el producto para Google y lo valida: precio, GTIN, campos obligatorios. | `N ok`, y las inválidas (`invalid`). |
| Subir a Merchant Center | Sube el producto. Con "No subir" se saltea. | `N uploaded`, y las que fallaron (`upload_failed`). |

Mientras una fila está en un paso, ese paso muestra el ID de la fila y los segundos que
lleva.

**3 · Cierre del archivo**

| Paso | Qué hace el script | Texto debajo |
|---|---|---|
| Esperar el veredicto de Google | Pregunta a Merchant Center cada 15 s si aprobó o rechazó los productos subidos, hasta que ninguno quede pendiente o se cumpla `--wait`. Se saltea con "No subir" o con `--wait 0`. | `ronda N · próxima en S s` mientras espera; al final, los conteos (`approved`, `disapproved`, `pending`). |
| Escribir los resultados | Escribe el CSV de resultados. | Nombre del archivo. |

> Google suele tardar bastante más que 5 minutos en revisar un producto, y en una
> cuenta de prueba puede no revisarlo nunca. Que un producto termine en `pending` no
> es un error: quedó subido, y el veredicto aparece después en Merchant Center →
> Productos.

### Fila en curso
La fila que se está procesando:
- la foto (`image_url`);
- los datos que vienen del CSV;
- los cuatro pasos de la fila, con el tiempo de cada uno.

### Última fila terminada
- **stage:** dónde terminó la fila (ver la tabla de abajo).
- **title**, **google_product_category** y **description**: lo que generó el script.
- **color (CSV)** frente a **predicted_color**: el color que trae el CSV y el que
  detectó el modelo en la foto. Si el CSV trae color, el título usa ese.
- **Ver detalle:** abre la ficha completa de la fila.

### Filas del archivo
Una celda por fila. Al hacer clic se abre el detalle.

| Color | Significado |
|---|---|
| Verde | `uploaded` (subida) o `dry_run` (pasó todo, con "No subir"). |
| Amarillo | `invalid` (datos que no pasan la validación) o `download_failed` (no se pudo bajar o leer la foto). |
| Rojo | `upload_failed` (Merchant Center la rechazó al subir) o `error` (falla inesperada). |
| Azul | En curso. |
| Blanco | Sin procesar. |

Debajo están los conteos por `stage` y, si hubo espera, los de Merchant Center.

### Salida del script
Las líneas que imprime el script, exactamente como en la terminal:
- en verde, las filas que salieron bien;
- en amarillo, las que no pasaron;
- en rojo, los errores.

### Resumen por archivo (al terminar)

| Columna | Significado |
|---|---|
| Salida | El código de salida del script (0, 1 o 2). |
| Summary | Cuántas filas terminaron en cada `stage`, igual que el "Summary" del script. |
| Merchant Center | Cuántos productos quedaron `approved`, `disapproved` o `pending`. |
| Results in | Link para descargar el CSV de resultados. |

## 3. Detalle de una fila
- **Foto**, **tiempos** de cada paso y **datos del CSV**.
- **reasons:** por qué la fila no llegó al final, si es el caso (ver la tabla de abajo).
- **Lo que generó la atribución:** la salida del paso de atribución (prenda, color,
  atributos, título, categoría y descripción).
- **Producto armado para Merchant Center:** cada campo que se sube y de dónde sale:
  - `CSV`: lo trajo el archivo;
  - `Atribución`: lo generó el script.
  También muestra si pasó la validación y cómo fue la subida.
- **Veredicto de Google:** `approved`, `disapproved` o `pending`, con los problemas que
  informó Google (*issues*).

## 4. Qué significa cada `stage` y cada `reason`

| stage | Significado |
|---|---|
| `uploaded` | Subida a Merchant Center. |
| `dry_run` | Pasó todos los controles; no se subió porque estaba tildado "No subir". |
| `invalid` | Le falta un dato obligatorio o un dato tiene mal formato. Ver `reasons`. |
| `download_failed` | No se pudo bajar o procesar la foto. |
| `upload_failed` | Merchant Center la rechazó al subirla. |
| `error` | Falla inesperada en esa fila (por ejemplo, el LLM respondió con un error). |

Algunos `reasons` frecuentes:
- `missing_<campo>`: falta ese campo (por ejemplo `missing_size`).
- `price_format`: el precio no tiene el formato `número MONEDA`.
- `gtin_format`: el GTIN no es un GTIN-13 válido.

## 5. CSV de resultados
Se escribe al lado del CSV de entrada, dentro de `upgrade/front/runs/<ejecución>/`, y se
descarga desde el resumen. Tiene una fila por producto:

| Columna | Significado |
|---|---|
| `id` | El ID del producto en Merchant Center. |
| `image_url` | La foto. |
| `stage` | Dónde terminó la fila. |
| `merchant_status` | El veredicto de Google (`approved`, `disapproved`, `pending`), o vacío si no se esperó. |
| `reasons` | Por qué no llegó al final, si es el caso. |
| `title` | Lo que generó el script. |
| `google_product_category` | Lo que generó el script. |
| `predicted_color` | Lo que generó el script. |
| `description` | Lo que generó el script. |

## 6. Preguntas frecuentes

**¿Si subo el mismo CSV dos veces se duplican los productos?**
No. El mismo ID (o la misma foto, si no hay ID) actualiza el producto que ya existe.

**¿Y si un ID se repite dentro del mismo CSV?**
El script no procesa ese archivo: frena en "Leer el CSV" con salida 2 y dice en qué
líneas está repetido.

**¿Por qué tarda tanto "Esperar el veredicto"?**
Porque espera a que Google revise los productos, hasta lo que diga `--wait`. Para
pruebas, conviene poner `0`.

**¿Por qué un zapato salió como cartera?**
Es lo que vio el modelo en la foto. Los modelos están entrenados sobre todo con ropa.
