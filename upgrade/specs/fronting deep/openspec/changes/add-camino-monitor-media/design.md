# Design: Monitor "Camino" (versión media)

## 1. Contexto

El pipeline procesa un lote en 3 fases y 12 etapas. La Fase 1 es bloqueante (si falla, se frena todo). La Fase 2 se ejecuta por prenda y un error en una prenda no frena a las demás. La Fase 3 espera el veredicto de Google (hasta 5 minutos) y genera el reporte.

La pantalla tiene que **coincidir con el pipeline** con 1 prenda o con decenas de miles. Eso descarta las dos soluciones ingenuas:
- **Que el front cuente eventos por prenda y sume.** Si se pierde, duplica o desordena un evento, los totales quedan mal para siempre. Además con 50.000 prendas el front recibiría cientos de miles de mensajes.
- **Que el front dibuje un elemento por prenda.** Con miles de prendas la pantalla se vuelve lenta e ilegible.

**Decisión central:** el servidor es la única fuente de verdad. Calcula **agregados absolutos** de tamaño fijo (no crecen con la cantidad de prendas) y la pantalla solo los muestra.

## 2. Objetivos y no objetivos

**Objetivos**
- La pantalla coincide con el estado confirmado del pipeline, con como máximo ~1 s de atraso.
- El tamaño de los mensajes y el costo de render no dependen de N, con N entre 1 y 50.000.
- Al recargar la página o al reconectar se recupera el estado exacto, sin doble conteo.
- Fidelidad visual con el artboard `CaminoMedia.dc.html`.

**No objetivos**
- Pausar o cancelar lotes.
- Versiones full y básica.
- Edición de prendas desde la pantalla.

## 3. Supuestos de stack (ajustar al repo si difiere)

| Capa | Supuesto | Motivo |
|---|---|---|
| Front | React 18 + TypeScript + Vite | Componentes, ecosistema |
| Estado del front | Zustand (store por lote) | Simple, selectores finos, sin re-render global |
| Tiempo real | SSE (`EventSource`) | Unidireccional, reconexión nativa con `Last-Event-ID`, pasa por proxies HTTP |
| Backend / BFF | Python + FastAPI | Coincide con el stack del pipeline |
| Estado del lote | Tabla `batch`, `batch_item`, `batch_counters` + `batch_event` (outbox) | Transaccional |
| Fan-out de eventos | Redis Pub/Sub o Streams (o equivalente gestionado) | Varios viewers por lote |
| Íconos | Lucide (o Tabler) | Reemplaza los SVG dibujados a mano del diseño |

Si el repo ya usa otra cosa (por ejemplo, Next.js, WebSocket, DynamoDB Streams), los requisitos de `specs/` siguen valiendo. Solo cambia esta sección.

## 4. Modelo canónico de etapas

| # | `stage_id` | Fase | Nodo del camino (`group_id`) | Falla posible (outcome) |
|---|---|---|---|---|
| 1.1 | `csv_received` | 1 | `file_validated` | — |
| 1.2 | `csv_structure` | 1 | `file_validated` | corte: `csv_missing_column`, `csv_row_without_photo`, `csv_duplicate_sku` |
| 1.3 | `credentials` | 1 | `connection` | corte: `missing_credentials` (salteada en modo prueba) |
| 2.1 | `required_fields` | 2 | `data_photo` | `incomplete` |
| 2.2 | `photo_download` | 2 | `data_photo` | `photo_unavailable` |
| 2.3 | `ai_analysis` | 2 | `ai_listing` | — (error técnico → `ai_error`) |
| 2.4 | `build_listing` | 2 | `ai_listing` | — |
| 2.5 | `quality_check` | 2 | `ai_listing` | `invalid` |
| 2.6 | `merchant_upload` | 2 | `publish` | `upload_error` (salteada en modo prueba) |
| 2.7 | `merchant_ack` | 2 | `publish` | `upload_error` (salteada en modo prueba) |
| 3.1 | `google_verdict` | 3 | `verdict` | `approved` / `rejected` / `pending` (salteada en modo prueba) |
| 3.2 | `report` | 3 | `report` | — |

Outcomes terminales de prenda (Fase 2): `uploaded`, `validated_dry_run`, `incomplete`, `photo_unavailable`, `invalid`, `upload_error`, `ai_error`.
Veredicto (solo `uploaded`): `approved`, `rejected`, `pending`.

> `ai_error` no está en el diagrama original, pero un error técnico de la IA tiene que caer en algún lado. Se muestra junto a "No pasaron calidad" con su motivo. **Pregunta abierta 1.**

## 5. Arquitectura

```
                 POST /batches (CSV o carpeta)                  GET /batches/{id}/snapshot
  [ Front ] ───────────────────────────────▶ [ API ] ◀────────────────────── [ Front ]
      ▲                                        │                                 │
      │  SSE /batches/{id}/events              │ encola                          │ SSE (desde seq del snapshot)
      │  (batch.progress, item.attention...)   ▼                                 ▼
  [ Event fan-out ] ◀── outbox relay ── [ Pipeline workers ] ── transacción ──▶ [ DB: batch, batch_item,
   (Redis Streams)                         │  por cada transición:                 batch_counters, batch_event ]
                                           │   1) UPDATE batch_item.stage/outcome
                                           │   2) UPDATE batch_counters (absolutos)
                                           │   3) INSERT batch_event (outbox, seq++)
                                           └── todo en la MISMA transacción
                                        [ Aggregator ] lee counters y emite batch.progress
                                          coalesciendo (≤ 2/s por lote + inmediato en cambio de fase)
```

**Por qué outbox transaccional:** si el worker confirma el estado de la prenda pero se cae antes de publicar el evento, el evento ya quedó en `batch_event` y el relay lo publica después. Nunca hay estado sin evento ni evento sin estado.

## 6. Secuencia: carga, monitor y reconexión

```
Usuario        Front                         API                     Pipeline / Aggregator
  │ suelta CSV   │                            │                              │
  │─────────────▶│ pre-valida (ext, tamaño)   │                              │
  │ Iniciar      │ POST /batches              │                              │
  │─────────────▶│ (Idempotency-Key) ────────▶│ crea batch, encola           │
  │              │◀──────── 201 {batch_id} ───│─────────────────────────────▶│ fase 1
  │              │ navega a /lotes/{id}       │                              │
  │              │ GET snapshot ─────────────▶│ (seq=S)                      │
  │              │ SSE ?after=S ─────────────▶│◀──── batch.progress (seq>S) ─│
  │              │ aplica si seq > lastSeq    │                              │
  │   (corte de red)                          │                              │
  │              │ EventSource reconecta      │                              │
  │              │ Last-Event-ID: lastSeq ───▶│ ¿lastSeq en ventana?         │
  │              │                            │  sí → replay seq>lastSeq     │
  │              │◀──── no → batch.snapshot ──│  (estado completo)           │
```

## 7. Contratos de datos (Python, Pydantic v2)

Copiar y pegar en `deep_tagger/api/progress_models.py`. El front genera los tipos TypeScript desde el OpenAPI o JSON Schema de estos modelos (por ejemplo con `datamodel-code-generator` a la inversa, o `pydantic2ts`).

```python
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class BatchStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    STOPPED = "stopped"          # corte de Fase 1
    COMPLETED = "completed"


class PhaseStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"
    NOT_RUN = "not_run"


class GroupId(str, Enum):
    FILE_VALIDATED = "file_validated"
    CONNECTION = "connection"
    DATA_PHOTO = "data_photo"
    AI_LISTING = "ai_listing"
    PUBLISH = "publish"
    VERDICT = "verdict"
    REPORT = "report"


class GarmentKind(str, Enum):
    SHIRT = "shirt"
    PANTS = "pants"
    DRESS = "dress"
    JACKET = "jacket"
    SKIRT = "skirt"
    SOCKS = "socks"
    SHORTS = "shorts"
    OTHER = "other"


class ItemRef(BaseModel):
    sku: str
    name: str
    kind: GarmentKind = GarmentKind.OTHER


class GroupProgress(BaseModel):
    group_id: GroupId
    in_flight: int = Field(ge=0, description="Prendas dentro de alguna etapa del grupo ahora")
    passed: int = Field(ge=0, description="Prendas que completaron el grupo sin fallar")
    failed: int = Field(ge=0, description="Prendas cuyo outcome terminal ocurrió en este grupo")
    skipped: bool = False
    active_sample: list[ItemRef] = Field(default_factory=list, max_length=3)


class CheckStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Phase1Checks(BaseModel):
    csv_received: CheckStatus
    csv_structure: CheckStatus
    credentials: CheckStatus


class Outcomes(BaseModel):
    uploaded: int = 0
    validated_dry_run: int = 0
    incomplete: int = 0
    photo_unavailable: int = 0
    invalid: int = 0
    upload_error: int = 0
    ai_error: int = 0


class Verdicts(BaseModel):
    approved: int = 0
    rejected: int = 0
    pending: int = 0
    awaiting: int = Field(0, description="Subidas sin respuesta todavía")


BucketState = Literal["idle", "running", "ok", "warn", "err"]


class BatchProgress(BaseModel):
    """Estado agregado completo. Tamaño O(1) respecto de la cantidad de prendas."""
    batch_id: str
    seq: int = Field(ge=0, description="Secuencia monotónica por lote")
    server_time: datetime
    status: BatchStatus
    dry_run: bool
    file_label: str
    total: int = Field(ge=0)
    queued: int = Field(ge=0, description="Prendas aún no ingresadas a la Fase 2")
    started_at: datetime | None
    finished_at: datetime | None
    phases: dict[Literal["1", "2", "3"], PhaseStatus]
    checks: Phase1Checks
    groups: list[GroupProgress]
    outcomes: Outcomes
    verdicts: Verdicts
    verdict_deadline: datetime | None
    report_ready: bool
    attention_count: int = Field(ge=0)
    item_states: list[BucketState] | None = Field(
        None, description="Un estado por prenda, en orden del CSV. Solo si total <= 60"
    )
    bucket_states: list[BucketState] | None = Field(
        None, max_length=100, description="Estado dominante por cubeta. Solo si total > 60"
    )
    stop_reason: StopReason | None = None


class StopReason(BaseModel):
    code: Literal["csv_missing_column", "csv_row_without_photo", "csv_duplicate_sku", "missing_credentials"]
    message: str = Field(description="Texto para negocio, en español")
    stage_id: Literal["csv_structure", "credentials"]


class AttentionItem(BaseModel):
    sku: str
    name: str
    kind: GarmentKind
    label: Literal[
        "Datos incompletos", "Foto no disponible", "No pasó calidad",
        "Error de IA", "Error al publicar", "Rechazada", "Pendiente",
    ]
    reason: str
    stage_id: str
    at: datetime


class SseEnvelope(BaseModel):
    """Cada mensaje SSE: `id: {seq}`, `event: {type}`, `data: {json de este modelo}`."""
    type: Literal["batch.snapshot", "batch.progress", "item.attention", "batch.stopped", "report.ready", "heartbeat"]
    seq: int
    server_time: datetime
    progress: BatchProgress | None = None
    attention: AttentionItem | None = None
    report_url: str | None = None


BatchProgress.model_rebuild()
```

**Invariantes que el servidor garantiza en cada `BatchProgress`:**
```
queued + sum(g.in_flight for g in fase 2) + sum(outcomes) == total
verdicts.approved + rejected + pending + awaiting == outcomes.uploaded   (si no es modo prueba)
seq estrictamente creciente por lote
```
El simulador y los tests de contrato verifican estas invariantes en cada mensaje.

## 8. Derivación de la pantalla a partir del estado (función pura en el front)

`deriveView(progress, now) -> CaminoViewModel`, sin efectos y testeable.

**Estado de nodo**

| Nodo | `running` | `done` (verde) | `failed` (rojo) | `skipped` (punteado) | `passed` (verde claro) |
|---|---|---|---|---|---|
| `file_validated` | `csv_received` o `csv_structure` = running | ambos passed | `csv_structure` = failed | — | — |
| `connection` | `credentials` = running | passed | failed | skipped (modo prueba) | — |
| grupos de Fase 2 | `in_flight > 0` | fase 2 completed | — (los fallos son por prenda) | `skipped` | `passed > 0` y `in_flight == 0` mientras la fase 2 sigue |
| `verdict` | fase 3 running y `awaiting > 0` | `awaiting == 0` | — | modo prueba | — |
| `report` | fase 3 running y `awaiting == 0` y no `report_ready` | `report_ready` | — | — | — |

Si el lote se cortó (`status = stopped`), los nodos posteriores al corte quedan `idle` con el texto "No se ejecutó".

**Insignia de nodo:** `ok` si terminó sin fallas. `warn` (!) si terminó con `failed > 0`, o si en el veredicto hay `rejected` o `pending`. `err` (✕) si el nodo produjo el corte.

**Concurrencia:** a diferencia del diseño (que simula una prenda por vez), el pipeline real procesa en paralelo. **Varios nodos de Fase 2 pueden estar `running` a la vez.** Cada uno muestra su chip con `active_sample[0]` y "+{in_flight - 1}".

**Avance de la línea por fase:**
```
p1 = checks pasados (o salteados) / 3
p2 = sum(outcomes) / total
p3 = modo prueba ? (report_ready ? 1 : 0.5)
                 : ((approved + rejected + pending) / max(1, uploaded)) * 0.8 + (report_ready ? 0.2 : 0)
```

**Cuenta regresiva del veredicto:** `max(0, verdict_deadline - (now + skew))`, donde `skew = server_time - client_time_at_receipt`, actualizada en cada mensaje.

**Tiempo transcurrido:** `(finished_at ?? now + skew) - started_at`.

## 9. Escala: decisiones concretas

| Problema con N grande | Decisión |
|---|---|
| Volumen de mensajes | Un solo tipo de mensaje de progreso con agregados absolutos, coalescido a ≤ 2 por segundo por lote, más emisión inmediata en cambios de fase o estado. `item.attention` solo para prendas con problema. |
| Mensajes perdidos o duplicados | Absolutos + `seq`: aplicar solo si `seq > lastSeq`. Un mensaje perdido se corrige con el siguiente. |
| Desconexión larga | Replay desde `Last-Event-ID` si la secuencia sigue en la ventana retenida (≥ 10 min). Si no, el servidor manda `batch.snapshot`. |
| DOM con miles de prendas | Hasta 60 prendas, un ícono por prenda (`item_states`). Por encima, una grilla fija de 100 cubetas (`bucket_states`), cada una representa `ceil(N/100)` prendas en orden del CSV, y se pinta con su estado dominante (prioridad `err > warn > running > ok > idle`). |
| Lista de atención enorme | En vivo se guardan las últimas 50 (`item.attention`). "Ver todas (N)" abre una lista virtualizada que pagina contra `GET /batches/{id}/items?filter=attention&cursor=`. |
| Render | El store aplica mensajes sin re-render. La vista se recalcula con `requestAnimationFrame`, a lo sumo cada 250 ms. |
| Muchos viewers | Fan-out vía Redis. El agregador calcula una vez por lote, no por conexión. |
| Contadores calientes con alta concurrencia | `batch_counters` con UPDATE atómico por columna (o contadores fragmentados si el motor lo requiere). El agregador lee y emite. |

**Objetivo medible:** con 50.000 prendas a 500 prendas/s en el simulador, la pantalla no supera 2.500 nodos DOM, no tiene tareas largas de más de 50 ms (CPU ×4 throttling en DevTools) y la memoria se mantiene estable durante 10 minutos.

## 10. Carga de archivo o carpeta

- **CSV solo:** `POST /batches` multipart (`file`, `dry_run`) con header `Idempotency-Key` (UUID generado al elegir el archivo).
- **Carpeta:** se busca exactamente un `.csv`. Las imágenes (`jpg`, `jpeg`, `png`, `webp`) se suben antes de iniciar:
  1. `POST /batches/uploads` → `upload_id` + URLs prefirmadas por nombre de archivo.
  2. Subida paralela con 6 en simultáneo y hasta 3 reintentos con backoff, mostrando "Subiendo fotos 340 de 1.200".
  3. `POST /batches` con `upload_id`. El CSV puede referenciar la foto por nombre relativo además de por URL.
- La validación de estructura (1.2) es **solo del servidor**. El cliente valida extensión, tamaño máximo (configurable, 50 MB por defecto para el CSV) y presencia del CSV en la carpeta.

## 11. Tokens visuales (del artboard)

| Token | Valor |
|---|---|
| Fondo | `#F7F6FA` |
| Texto | `#2B2A33`, secundario `#5F5D6B` |
| Acento | `#4B4A8F` |
| Banda Fase 1 | fondo `#FDEFE7`, título `#A2471C`, línea `#E9946A` |
| Banda Fase 2 | fondo `#F1EDFB`, título `#5A46A8`, línea `#7C6BCB` |
| Banda Fase 3 | fondo `#E8F5EE`, título `#23714A`, línea `#5DAE80` |
| Nodo activo | `#4B6EC8` con pulso (desactivado si `prefers-reduced-motion`) |
| OK / Error / Aviso | `#5DAE80` / `#D9606E` / `#E3C14F` |
| Chips | ok `#DDF2E5/#1E5B3A`, err `#FBDDE0/#8A2433`, warn `#FCF1C7/#6B5208`, info `#DCE8FA/#1F4A85` |
| Tipografía | Inter 400/500/600/700, JetBrains Mono para tiempos |
| Nodo | círculo de 64 px, ícono de 28 px, insignia de 22 px |

## 12. Alternativas consideradas

- **WebSocket:** bidireccional y no hace falta. SSE trae reconexión con `Last-Event-ID` incluida.
- **Polling cada 2 s al snapshot:** más simple, pero más carga y más latencia. Se mantiene como **fallback** si SSE falla 3 veces seguidas.
- **Agregar en el front:** se descarta por consistencia (sección 1).

## 13. Riesgos

- **Proxies que bufferean SSE.** Mitigación: `Cache-Control: no-cache`, `X-Accel-Buffering: no` y heartbeat cada 15 s.
- **Contadores desalineados por bug de instrumentación.** Mitigación: job de reconciliación que recalcula `batch_counters` desde `batch_item` al cerrar cada fase y emite un progreso corregido. Los tests de contrato verifican las invariantes.
- **Prenda sin tipo reconocible.** Se usa `kind = other` (ícono genérico de etiqueta).

## 14. Preguntas abiertas

1. ¿Un error técnico de la IA (2.3) es outcome propio (`ai_error`) o se reintenta y termina en `invalid`?
2. ¿El tipo de prenda (`kind`) sale de una columna del CSV o de la clasificación de la IA? Antes de 2.3 se mostraría `other`.
3. ¿Hay reintento automático de `upload_error`? Si lo hay, la prenda vuelve a `in_flight` del grupo `publish`.
4. Ventana de retención del replay SSE (propuesta: 10 min o 10.000 eventos).
