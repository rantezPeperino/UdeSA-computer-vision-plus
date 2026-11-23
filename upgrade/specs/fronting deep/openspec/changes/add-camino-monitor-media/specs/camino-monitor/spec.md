# camino-monitor

## ADDED Requirements

### Requirement: Ruta del monitor y carga inicial
La pantalla SHALL vivir en `/lotes/{batch_id}`, SHALL cargar primero `GET /batches/{id}/snapshot` y después suscribirse al stream SSE con `after` igual al `seq` del snapshot. Al recargar la página SHALL mostrar el mismo estado que antes de recargar.

#### Scenario: Recarga en mitad del lote
- **WHEN** el usuario recarga con 4.312 de 10.000 prendas procesadas
- **THEN** la pantalla vuelve a mostrar 4.312 procesadas sin pasar por cero

#### Scenario: Lote inexistente
- **WHEN** el snapshot responde 404
- **THEN** se muestra "No encontramos ese lote" con el botón "Cargar otro lote"

### Requirement: Aplicación ordenada de mensajes
El cliente SHALL aplicar un mensaje solo si su `seq` es mayor que el último aplicado, SHALL reemplazar el estado agregado completo con cada `batch.progress` o `batch.snapshot`, y MUST NOT calcular totales sumando mensajes.

#### Scenario: Mensaje duplicado
- **WHEN** llega dos veces el mensaje con `seq` 1200
- **THEN** la segunda copia se descarta y los totales no cambian

#### Scenario: Mensaje viejo fuera de orden
- **WHEN** después de aplicar 1205 llega 1203
- **THEN** 1203 se descarta

### Requirement: Camino horizontal de 7 nodos
La pantalla SHALL mostrar un único camino horizontal de 7 nodos sobre 3 bandas de fase (Preparación, Por cada prenda, Cierre), que agrupan las 12 etapas según la tabla de `design.md` sección 4. Cada nodo SHALL mostrar su ícono, su nombre, las etapas que agrupa y una línea de detalle.

#### Scenario: Nodos y agrupación
- **WHEN** se abre el monitor de cualquier lote
- **THEN** la banda de Fase 1 muestra "Archivo recibido y validado" (1.1 · 1.2, ícono archivo) y "Conexión con Google e IA" (1.3, ícono enchufe)
- **AND** la banda de Fase 2 muestra "Validar datos y foto" (2.1 · 2.2, ícono imagen), "Generar ficha con IA" (2.3 · 2.4 · 2.5, ícono destellos) y "Publicar en Google" (2.6 · 2.7, ícono nube con flecha)
- **AND** la banda de Fase 3 muestra "Veredicto de Google" (3.1, ícono reloj) y "Reporte final" (3.2, ícono reporte)

#### Scenario: Pantalla angosta
- **WHEN** el ancho de la ventana es menor que el del camino
- **THEN** el camino se desplaza horizontalmente dentro de su tarjeta, sin apilar los nodos

### Requirement: Estados visuales de nodo
Cada nodo SHALL tomar uno de los estados `idle` (gris), `running` (azul con pulso), `passed` (verde claro), `done` (verde), `failed` (rojo) o `skipped` (borde punteado), y una insignia opcional `ok` (✓), `warn` (!) o `err` (✕), derivados del `BatchProgress` según la tabla de `design.md` sección 8.

#### Scenario: Procesamiento en paralelo
- **WHEN** hay 40 prendas en `data_photo`, 23 en `ai_listing` y 12 en `publish`
- **THEN** los tres nodos de Fase 2 se muestran `running` a la vez

#### Scenario: Fase 2 termina con problemas en calidad
- **WHEN** la Fase 2 se completa y `ai_listing.failed = 7`
- **THEN** "Generar ficha con IA" queda `done` con insignia `warn` y el detalle "9.993 ok · 7 con problemas"

#### Scenario: Corte por credenciales
- **WHEN** llega `batch.stopped` con `stage_id = credentials`
- **THEN** "Conexión con Google e IA" queda `failed` con insignia `err`, y los nodos de Fase 2 y 3 quedan `idle` con el detalle "No se ejecutó"

#### Scenario: Modo prueba
- **WHEN** el lote es `dry_run`
- **THEN** "Conexión con Google e IA", "Publicar en Google" y "Veredicto de Google" se muestran `skipped`

### Requirement: Chip de tránsito bajo el nodo activo
Bajo cada nodo `running` la pantalla SHALL mostrar un chip: en "Archivo recibido y validado", el ícono de archivo con el nombre del archivo del lote; en los nodos de Fase 2, el ícono del tipo de prenda de `active_sample[0]` con su nombre y, si `in_flight > 1`, el sufijo "+{in_flight - 1}"; en "Veredicto de Google", el reloj con "quedan mm:ss".

#### Scenario: Una sola prenda
- **WHEN** el lote tiene 1 prenda y está en `ai_listing`
- **THEN** el chip muestra el ícono y el nombre de esa prenda, sin sufijo

#### Scenario: Miles de prendas
- **WHEN** `publish.in_flight = 230` y `active_sample[0]` es "Jean mom fit azul" de tipo `pants`
- **THEN** el chip muestra el ícono de pantalón, "Jean mom fit azul" y "+229"

### Requirement: Línea de avance por fase
Cada banda de fase SHALL mostrar una línea que se llena de izquierda a derecha según `p1`, `p2` y `p3` definidos en `design.md`, en el color de su fase, o en rojo si la fase se cortó.

#### Scenario: Mitad de la Fase 2
- **WHEN** `sum(outcomes) = 5.000` y `total = 10.000`
- **THEN** la línea de la banda de Fase 2 está al 50 %

### Requirement: Prendas del lote escalable
El panel "Prendas del lote" SHALL mostrar un ícono por prenda (tipo de prenda, coloreado por estado) cuando `total <= 60`, y una grilla de hasta 100 cubetas coloreadas por `bucket_states` cuando `total > 60`. En este último caso SHALL indicar "Cada cuadro = N prendas". En ningún caso la cantidad de elementos dibujados MUST superar 100. Siempre SHALL mostrar "X de N procesadas" y la leyenda de colores.

#### Scenario: Lote de 12 prendas
- **WHEN** el lote tiene 12 prendas
- **THEN** se ven 12 íconos con el tipo de cada prenda y al pasar el mouse un título con nombre y estado

#### Scenario: Lote de 25.000 prendas
- **WHEN** el lote tiene 25.000 prendas
- **THEN** se ven 100 cuadros con la leyenda "Cada cuadro = 250 prendas"

### Requirement: Indicadores de resultado
La pantalla SHALL mostrar cuatro indicadores: "Publicadas" (`uploaded`, o "Fichas validadas" con `validated_dry_run` en modo prueba), "Problemas de datos o foto" (`incomplete + photo_unavailable`, etapas 2.1 y 2.2), "No pasaron calidad" (`invalid + ai_error`, etapas 2.3 a 2.5) y "Error al publicar" (`upload_error`, etapas 2.6 y 2.7). Los números SHALL formatearse con separador de miles es-AR.

#### Scenario: Formato de miles
- **WHEN** `uploaded = 12345`
- **THEN** el indicador muestra "12.345"

### Requirement: Barra de veredicto de Google
La pantalla SHALL mostrar una barra apilada aprobadas / rechazadas / pendientes sobre el total de publicadas (`awaiting` cuenta como pendiente mientras corre la Fase 3), con sus cantidades y una nota de estado: "Empieza al terminar las prendas", "Esperando respuesta de Google", "Cerrado", "No aplica en modo prueba" o "No se ejecutó".

#### Scenario: Esperando a Google
- **WHEN** la Fase 3 corre con `approved = 6`, `rejected = 1`, `awaiting = 2`
- **THEN** la barra muestra 6 / 1 / 2 y la nota "Esperando respuesta de Google"

### Requirement: Lista "Requieren atención"
La pantalla SHALL mostrar las últimas 50 prendas recibidas por `item.attention` (nombre, etiqueta de color y motivo), de la más reciente a la más antigua. Si `attention_count > 50`, SHALL ofrecer "Ver todas ({attention_count})", que abre una lista virtualizada y paginada contra `GET /batches/{id}/items?filter=attention`, con filtro por etiqueta. Sin problemas SHALL mostrar "Por ahora ninguna prenda tiene problemas."

#### Scenario: 3.000 prendas con problemas
- **WHEN** `attention_count = 3000`
- **THEN** la lista muestra 50 elementos y el enlace "Ver todas (3.000)"
- **AND** la lista completa carga de a 100 al hacer scroll, sin dibujar más de lo visible

### Requirement: Encabezado
El encabezado SHALL mostrar el nombre del archivo, el total de prendas, el chip "Modo prueba" si corresponde, el estado del lote ("Procesando", "Lote frenado" o "Finalizado"), el tiempo transcurrido desde `started_at` corregido con el reloj del servidor, y el botón "Cargar otro lote". MUST NOT mostrar controles de pausa ni cancelación.

#### Scenario: Lote en curso
- **WHEN** el lote corre hace 3 minutos y 20 segundos según el servidor
- **THEN** el encabezado muestra "Procesando", "03:20" y "Cargar otro lote", sin botón de pausa

### Requirement: Banners de estado
Bajo el encabezado la pantalla SHALL mostrar un banner rojo ante un corte (con `stop_reason.message` y "No se procesó ninguna prenda."), un banner amarillo de modo prueba mientras el lote corre, o un banner verde al finalizar con el resumen y "Descargar reporte" apuntando a `report_url`.

#### Scenario: Lote finalizado
- **WHEN** llega `report.ready`
- **THEN** aparece el banner verde "Lote finalizado" con "N aprobadas, N rechazadas, N pendientes · N descartadas" y el botón "Descargar reporte"

#### Scenario: Lote frenado
- **WHEN** llega `batch.stopped` con el mensaje "El código RV-1006 está repetido"
- **THEN** aparece el banner rojo "Se frenó todo el lote" con ese mensaje y "No se procesó ninguna prenda."

### Requirement: Reconexión visible y sin doble conteo
Cuando se pierde la conexión SSE, la pantalla SHALL mostrar "Reconectando…" junto al estado, SHALL reconectar con `Last-Event-ID`, y tras 3 fallos consecutivos SHALL pasar a consultar el snapshot cada 2 segundos hasta que el stream vuelva.

#### Scenario: Corte de red de 30 segundos
- **WHEN** se corta la red 30 segundos y vuelve
- **THEN** la pantalla muestra "Reconectando…" durante el corte y luego los totales correctos, sin saltos hacia atrás

### Requirement: Rendimiento independiente de la cantidad de prendas
La pantalla SHALL recalcular la vista como máximo cada 250 ms, MUST NOT superar 2.500 nodos DOM con cualquier `total` entre 1 y 50.000, MUST NOT producir tareas largas de más de 50 ms con CPU ×4 throttling, y su memoria MUST mantenerse estable durante 10 minutos de stream continuo.

#### Scenario: Prueba de carga
- **WHEN** el simulador emite un lote de 50.000 prendas a 500 prendas por segundo
- **THEN** la prueba automatizada verifica los cuatro límites anteriores

### Requirement: Accesibilidad
La pantalla SHALL anunciar en una región `aria-live="polite"` solo los cambios de fase y de estado del lote. Cada nodo SHALL tener un nombre accesible con nombre, estado y detalle. Los íconos decorativos SHALL tener `aria-hidden`. Los textos SHALL cumplir contraste 4,5:1. Con `prefers-reduced-motion` el pulso SHALL desactivarse.

#### Scenario: Cambio de fase con lector de pantalla
- **WHEN** termina la Fase 2
- **THEN** se anuncia "Fase 2 completada. Esperando el veredicto de Google." una sola vez

### Requirement: Fidelidad visual con el diseño
La pantalla SHALL respetar los tokens de color, tipografía y tamaños de `design.md` sección 11 y la composición del artboard `CaminoMedia.dc.html`: encabezado, banner, camino con bandas de fase, panel "Prendas del lote", indicadores con veredicto a la izquierda y "Requieren atención" a la derecha (apilados en pantallas angostas).

#### Scenario: Revisión visual
- **WHEN** se compara una captura del lote de ejemplo de 12 prendas con el artboard
- **THEN** coinciden la estructura, los colores por fase y los estados de nodo
