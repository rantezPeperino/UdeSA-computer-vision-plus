# Tasks: add-camino-monitor-media

Orden recomendado: contrato → simulador → front contra simulador → instrumentación real → pruebas de escala. Así el front se construye y prueba sin depender del pipeline real.

## 1. Contrato
- [ ] 1.1 Crear `deep_tagger/api/progress_models.py` con los modelos de `design.md` sección 7.
- [ ] 1.2 Agregar validadores de invariantes (`queued + in_flight + outcomes == total`, veredictos == uploaded) como función `check_invariants(progress) -> list[str]`.
- [ ] 1.3 Exportar JSON Schema y generar los tipos TypeScript del front en `web/src/lotes/types.gen.ts`.
- [ ] 1.4 Tests unitarios de serialización y de invariantes.

## 2. Simulador de eventos (Python)
- [ ] 2.1 `tools/sim_batch.py`: servidor FastAPI que implementa `POST /batches`, `GET /snapshot`, `GET /events` (SSE) y `GET /items` con datos simulados.
- [ ] 2.2 Parámetros: `--total` (1, 12, 10000, 50000), `--rate` (prendas/s), `--concurrency`, `--scenario` (`normal`, `dry_run`, `stop_csv`, `stop_credentials`), `--fail-ratio`, `--drop-ratio` (descarta mensajes para probar recuperación).
- [ ] 2.3 Escenario de 12 prendas idéntico al del diseño (mismos SKU, nombres, tipos y motivos).
- [ ] 2.4 Coalescer `batch.progress` a ≤ 2/s, mantener ventana de replay y responder `batch.snapshot` fuera de ventana.
- [ ] 2.5 Verificar invariantes en cada mensaje emitido (falla el proceso si se rompen).

## 3. Inicio de lote (front, `batch-intake`)
- [ ] 3.1 Ruta `/lotes/nuevo` con la zona de carga (arrastrar y soltar) y los botones "Elegir archivo CSV", "Elegir carpeta" (`webkitdirectory`) y "Usar archivo de ejemplo" (solo en entornos no productivos).
- [ ] 3.2 Pre-validación: extensión, tamaño máximo configurable, exactamente un CSV en la carpeta y conteo de fotos.
- [ ] 3.3 Tarjeta "Lote a procesar", casilla "Modo prueba" y botón "Iniciar procesamiento" deshabilitado sin archivo.
- [ ] 3.4 Subida de fotos con URLs prefirmadas, 6 en simultáneo, 3 reintentos y progreso; diálogo "Reintentar / Iniciar igual".
- [ ] 3.5 `POST /batches` con `Idempotency-Key`; navegar a `/lotes/{id}`; manejo de errores 4xx y 5xx.
- [ ] 3.6 Tests de componentes para cada escenario de `specs/batch-intake/spec.md`.

## 4. Store y derivación (front)
- [ ] 4.1 Store Zustand por lote: `progress`, `lastSeq`, `skew`, `attention` (buffer circular de 50), `connection` (`live | reconnecting | polling`).
- [ ] 4.2 Cliente SSE: snapshot → `EventSource(...?after=seq)`; descartar `seq <= lastSeq`; reemplazar el estado completo en `batch.progress` y `batch.snapshot`; fallback a polling tras 3 fallos.
- [ ] 4.3 `deriveView(progress, now)` pura según `design.md` sección 8 (estados de nodo, insignias, chips, avance por fase, cuenta regresiva, transcurrido).
- [ ] 4.4 Tests de tabla de `deriveView` para cada escenario de `specs/camino-monitor/spec.md` (paralelo, corte, modo prueba, 1 prenda, miles).
- [ ] 4.5 Recalcular la vista con `requestAnimationFrame`, como máximo cada 250 ms.

## 5. Componentes del camino (front, `camino-monitor`)
- [ ] 5.1 `CaminoHeader`: archivo, total, chip de modo prueba, estado, transcurrido, "Reconectando…", "Cargar otro lote" (sin pausa).
- [ ] 5.2 `CaminoBanner`: corte, modo prueba, finalizado con "Descargar reporte".
- [ ] 5.3 `CaminoTrack` + `PhaseBand` + `PathNode` + `TransitChip`: 7 nodos con íconos Lucide, insignias y desplazamiento horizontal.
- [ ] 5.4 `GarmentPanel`: íconos por prenda (≤ 60) o grilla de 100 cubetas con leyenda "Cada cuadro = N prendas".
- [ ] 5.5 `ResultKpis` + `VerdictBar` con formato es-AR.
- [ ] 5.6 `AttentionList` (últimas 50) + `AttentionDrawer` virtualizado y paginado con filtro por etiqueta.
- [ ] 5.7 Aplicar los tokens de `design.md` sección 11 y comparar contra el artboard con el escenario de 12 prendas.

## 6. Instrumentación del pipeline real (`pipeline-progress-events`)
- [ ] 6.1 Tablas `batch`, `batch_item`, `batch_counters`, `batch_event` (outbox con `seq` por lote).
- [ ] 6.2 Helper `record_transition(item, stage_id, status, outcome=None, reason=None)` que actualiza ítem, contadores y outbox en una sola transacción. Usarlo en cada una de las 12 etapas.
- [ ] 6.3 Relay del outbox hacia Redis Streams; agregador que coalesce `batch.progress` y calcula `active_sample`, `item_states` y `bucket_states`.
- [ ] 6.4 Endpoints reales: `POST /batches`, `POST /batches/uploads`, `GET /snapshot`, `GET /events`, `GET /items`, `GET /report`.
- [ ] 6.5 Corte de Fase 1 con `stop_reason` y mensajes en español; modo prueba con `skipped`.
- [ ] 6.6 Veredicto: fijar `verdict_deadline`, pasar `awaiting` a `pending` al vencer.
- [ ] 6.7 Job de reconciliación de contadores al cerrar cada fase.
- [ ] 6.8 Configurar el proxy para SSE (sin buffering, timeout ≥ 15 min).

## 7. Pruebas de consistencia y escala
- [ ] 7.1 Test de contrato: el mismo cliente contra el simulador y contra el pipeline real (lote de 12) produce la misma secuencia de estados de nodo.
- [ ] 7.2 Test end-to-end (Playwright) de los 4 escenarios con 12 prendas.
- [ ] 7.3 Prueba de carga: 50.000 prendas a 500/s con `--drop-ratio 0.05`; verificar nodos DOM ≤ 2.500, sin tareas largas > 50 ms (CPU ×4), memoria estable 10 min y totales finales iguales al snapshot.
- [ ] 7.4 Prueba de reconexión: corte de red de 30 s y de 15 min (fuera de ventana) sin doble conteo.
- [ ] 7.5 Auditoría de accesibilidad (axe) sin violaciones serias; `prefers-reduced-motion` respetado.

## 8. Cierre
- [ ] 8.1 Resolver las preguntas abiertas de `design.md` sección 14 y actualizar los specs si cambian.
- [ ] 8.2 `openspec validate add-camino-monitor-media --strict` sin errores.
- [ ] 8.3 Archivar el change al desplegar.
