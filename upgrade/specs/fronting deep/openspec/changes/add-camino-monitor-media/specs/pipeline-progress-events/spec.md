# pipeline-progress-events

## ADDED Requirements

### Requirement: Modelo canónico de etapas
El pipeline SHALL identificar cada transición con uno de los 12 `stage_id` canónicos (`csv_received`, `csv_structure`, `credentials`, `required_fields`, `photo_download`, `ai_analysis`, `build_listing`, `quality_check`, `merchant_upload`, `merchant_ack`, `google_verdict`, `report`) y SHALL asignar cada uno a su `group_id` según la tabla de `design.md`.

#### Scenario: Transición registrada
- **WHEN** un worker termina la descarga de la foto de una prenda
- **THEN** la transición se registra con `stage_id = photo_download` y cuenta para el grupo `data_photo`

### Requirement: Estado y evento en la misma transacción
Cada transición de etapa de una prenda SHALL actualizar en una misma transacción el estado de la prenda, los contadores absolutos del lote y el registro de evento de salida (outbox). Un evento MUST NOT publicarse sin su estado confirmado, ni un estado quedar sin evento.

#### Scenario: El worker se cae después de confirmar
- **WHEN** el worker confirma la transición y se cae antes de publicar
- **THEN** el relay del outbox publica el evento pendiente al recuperarse
- **AND** la pantalla termina mostrando el mismo estado que la base de datos

### Requirement: Snapshot del lote
El servidor SHALL exponer `GET /batches/{id}/snapshot` con un `BatchProgress` completo, que incluya el `seq` del último evento aplicado y el `server_time`. El tamaño de la respuesta MUST NOT crecer con la cantidad de prendas.

#### Scenario: Lote de 50.000 prendas
- **WHEN** se pide el snapshot de un lote de 50.000 prendas
- **THEN** la respuesta pesa lo mismo que la de un lote de 12, salvo por los textos de nombres en las muestras activas
- **AND** incluye `bucket_states` de 100 elementos y `item_states = null`

#### Scenario: Lote de 12 prendas
- **WHEN** se pide el snapshot de un lote de 12 prendas
- **THEN** incluye `item_states` con 12 elementos en orden del CSV y `bucket_states = null`

### Requirement: Stream SSE de progreso
El servidor SHALL exponer `GET /batches/{id}/events` como Server-Sent Events, donde cada mensaje lleva `id` igual a un `seq` estrictamente creciente por lote, `event` igual al tipo (`batch.snapshot`, `batch.progress`, `item.attention`, `batch.stopped`, `report.ready`, `heartbeat`) y `data` igual a un `SseEnvelope` en JSON. SHALL enviar `heartbeat` cada 15 segundos y los headers `Cache-Control: no-cache` y `X-Accel-Buffering: no`.

#### Scenario: Suscripción tras el snapshot
- **WHEN** el cliente se suscribe con `?after=S`, donde S es el `seq` del snapshot
- **THEN** recibe solo mensajes con `seq > S`

#### Scenario: Reconexión dentro de la ventana
- **WHEN** el cliente reconecta con `Last-Event-ID: 840` y la ventana retenida incluye 841 en adelante
- **THEN** el servidor reenvía en orden los mensajes desde 841

#### Scenario: Reconexión fuera de la ventana
- **WHEN** el cliente reconecta con un `Last-Event-ID` que ya no está retenido
- **THEN** el servidor envía primero un `batch.snapshot` con el estado completo y sigue desde ahí

### Requirement: Progreso con agregados absolutos y coalescido
`batch.progress` SHALL contener el `BatchProgress` completo con contadores absolutos (no incrementos), SHALL emitirse como máximo 2 veces por segundo por lote mientras haya cambios, y SHALL emitirse de inmediato ante un cambio de `status` o de estado de fase.

#### Scenario: Ráfaga de 500 prendas por segundo
- **WHEN** el pipeline completa 500 prendas en un segundo
- **THEN** el stream envía como máximo 2 `batch.progress` en ese segundo, cada uno con los totales vigentes

#### Scenario: Mensaje perdido
- **WHEN** el cliente no recibe el `batch.progress` con `seq` 900 pero sí el 901
- **THEN** el estado mostrado después de aplicar el 901 es correcto, porque 901 trae los totales absolutos

### Requirement: Invariantes del progreso
Todo `BatchProgress` SHALL cumplir `queued + suma de in_flight de los grupos de Fase 2 + suma de outcomes == total`. Fuera de modo prueba SHALL cumplir además `approved + rejected + pending + awaiting == uploaded`.

#### Scenario: Verificación en tests de contrato
- **WHEN** el test de contrato consume el stream completo de un lote simulado de 10.000 prendas
- **THEN** cada mensaje cumple ambas invariantes

### Requirement: Muestras de prendas activas
Cada `GroupProgress` SHALL incluir en `active_sample` hasta 3 prendas que están dentro del grupo en ese momento (`sku`, `name`, `kind`), con prioridad para la que entró más recientemente.

#### Scenario: 23 prendas generando ficha
- **WHEN** hay 23 prendas en etapas 2.3 a 2.5
- **THEN** el grupo `ai_listing` informa `in_flight = 23` y `active_sample` con 3 prendas

### Requirement: Resumen por cubetas
Cuando `total > 60`, `BatchProgress` SHALL incluir `bucket_states` con 100 cubetas (o `total` si es menor). Cada cubeta representa `ceil(total/100)` prendas consecutivas del CSV y lleva su estado dominante con prioridad `err > warn > running > ok > idle`. Cuando `total <= 60` SHALL incluir `item_states` con un estado por prenda.

#### Scenario: Cubeta con una prenda rechazada
- **WHEN** una cubeta tiene 499 prendas aprobadas y 1 rechazada
- **THEN** su estado es `err`

### Requirement: Prendas que requieren atención
El servidor SHALL emitir `item.attention` cuando una prenda termina con outcome distinto de `uploaded` o `validated_dry_run`, o cuando su veredicto es `rejected` o `pending`. SHALL exponer además `GET /batches/{id}/items?filter=attention&cursor=&limit=` paginado por cursor, ordenado de más reciente a más antiguo, con filtro opcional por `label`.

#### Scenario: Prenda sin precio
- **WHEN** una prenda falla en `required_fields` por falta de precio
- **THEN** se emite `item.attention` con `label = "Datos incompletos"` y `reason = "Falta el precio"`

#### Scenario: Listado completo con 3.000 prendas con problemas
- **WHEN** el cliente pide `limit=100` sin cursor
- **THEN** recibe 100 elementos y un `next_cursor`, y `attention_count` del progreso vale 3.000

### Requirement: Veredicto con fecha límite
Al terminar la Fase 2 fuera de modo prueba, el servidor SHALL fijar `verdict_deadline = now + 5 minutos`, SHALL actualizar `verdicts` a medida que Google responde, y al vencer el plazo SHALL pasar las `awaiting` restantes a `pending`.

#### Scenario: Plazo vencido
- **WHEN** vencen los 5 minutos con 2 prendas sin respuesta
- **THEN** `verdicts.pending` aumenta en 2, `awaiting = 0` y se emite `item.attention` "Pendiente" para cada una

### Requirement: Corte de Fase 1
Si falla `csv_structure` o `credentials`, el servidor SHALL poner el lote en `status = stopped`, SHALL emitir `batch.stopped` con `stop_reason` (`code`, `message` en español y `stage_id`), SHALL marcar las fases 2 y 3 como `not_run`, y MUST NOT procesar ninguna prenda.

#### Scenario: SKU repetido
- **WHEN** la etapa 1.2 encuentra el código RV-1006 repetido
- **THEN** se emite `batch.stopped` con `code = csv_duplicate_sku`, `stage_id = csv_structure` y un mensaje que nombra RV-1006

### Requirement: Modo prueba en el progreso
Con `dry_run = true`, el servidor SHALL reportar `credentials` como `skipped`, los grupos `publish` y `verdict` con `skipped = true`, y SHALL usar el outcome `validated_dry_run` para las prendas que pasan el control de calidad.

#### Scenario: Lote en modo prueba
- **WHEN** termina un lote de 12 prendas en modo prueba con 3 problemas
- **THEN** `outcomes.validated_dry_run = 9` y `verdicts` queda en cero

### Requirement: Reporte final
Al completar el lote, el servidor SHALL generar el reporte (un renglón por prenda con resultado y motivo, más totales), SHALL emitir `report.ready` con `report_url` y SHALL poner `status = completed` y `report_ready = true`.

#### Scenario: Descarga del reporte
- **WHEN** se emite `report.ready`
- **THEN** `GET {report_url}` devuelve un CSV con `total` renglones más un renglón de totales
