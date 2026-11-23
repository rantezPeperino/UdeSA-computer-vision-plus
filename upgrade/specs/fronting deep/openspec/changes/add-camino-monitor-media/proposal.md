# Proposal: Monitor "Camino" (versión media) para lotes de Deep Tagger

## Why

Hoy el pipeline de Deep Tagger (CSV de la marca → análisis de foto con IA → ficha Google → Google Merchant) corre sin una vista que negocio pueda seguir. Se necesita una pantalla que permita **iniciar un lote manualmente** (archivo CSV o carpeta) y **ver su avance como un camino horizontal de íconos**, que refleje en todo momento lo que realmente está pasando en el pipeline, tanto para un lote de 1 prenda como para uno de miles.

El diseño de referencia está en el canvas de diseño (artboard `CaminoMedia.dc.html`, "Camino · versión media"): https://claude.ai/artifact/TvmQV7qwsE7Uce8RYfUE9C

## What Changes

- Nueva pantalla de **inicio de lote**: carga de CSV o carpeta (selector y arrastrar/soltar), pre-validación liviana en el cliente, opción **Modo prueba** y botón **Iniciar procesamiento**.
- Nueva pantalla de **monitor del lote** (`/lotes/{batch_id}`) con:
  - Camino horizontal de **7 nodos** que agrupan las **12 etapas** del pipeline, sobre 3 bandas de fase.
  - Chip de "prenda en tránsito" bajo el nodo activo (ícono del tipo de prenda + nombre + "+N").
  - Panel "Prendas del lote" que escala: un ícono por prenda hasta 60, mapa de cubetas por encima.
  - Indicadores de resultado, barra de veredicto de Google y lista "Requieren atención".
- Nuevo **contrato de progreso** en el backend: snapshot + stream SSE con **agregados absolutos** (no incrementos), numerados por secuencia y reanudables, emitidos desde la misma fuente que confirma el estado del pipeline.
- Endpoint paginado de prendas que requieren atención.
- Simulador de eventos (Python) para desarrollo y pruebas de carga (1, 12, 10.000 y 50.000 prendas).

**Fuera de alcance**
- Versiones full y básica del monitor (se especifican en changes separados).
- Pausar o cancelar un lote (el pipeline no lo soporta). El botón "Pausar" del diseño era parte de la simulación y **no se implementa**.
- Autenticación y multi-marca (se asume la sesión existente de la app).
- Cambios en la lógica de negocio del pipeline (solo se instrumenta).

## Capabilities

### New Capabilities

- `batch-intake`: carga de CSV o carpeta, pre-validación, subida de fotos con progreso, modo prueba e inicio del lote.
- `pipeline-progress-events`: modelo canónico de etapas, snapshot del lote, stream SSE de progreso con agregados absolutos, muestras activas, resumen por cubetas, prendas que requieren atención, veredicto con fecha límite y reporte.
- `camino-monitor`: la pantalla de monitor versión media (camino de 7 nodos, chips, prendas del lote, indicadores, veredicto, atención, banners, reconexión, rendimiento y accesibilidad).

### Modified Capabilities

Ninguna.

## Impact

- **Backend / pipeline**: instrumentación en cada transición de etapa (escritura transaccional de estado + outbox de eventos), un agregador de contadores por lote, endpoints `POST /batches`, `GET /batches/{id}/snapshot`, `GET /batches/{id}/events` (SSE), `GET /batches/{id}/items`, `GET /batches/{id}/report`.
- **Frontend**: dos rutas nuevas, un store de lote alimentado por snapshot + SSE, componentes del camino.
- **Infra**: el proxy o balanceador debe permitir conexiones SSE de larga duración (sin buffering, timeout ≥ 15 min, heartbeat).
- **Riesgo principal**: inconsistencia entre lo que muestra la pantalla y el estado real. Se mitiga con agregados absolutos calculados en el servidor, secuencia monotónica y snapshot de recuperación (ver `design.md`).
- **Rollback**: la pantalla es aditiva; se desactiva ocultando la ruta. La instrumentación del pipeline no altera su comportamiento (solo escribe estado y eventos).
