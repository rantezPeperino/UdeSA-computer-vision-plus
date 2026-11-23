# Tareas · Monitor web del pipeline

Un front que arranca la etapa 4 desde el navegador y la muestra en vivo. Es una capa más: no modifica ningún archivo existente del repo, y todo lo nuevo vive en `upgrade/front/`. Spec: [`spec.md`](spec.md). Diseño: lienzo "Deep Tagger · Monitor de lotes" (pantallas 1 a 5).

- [x] 1 Capa de observación (`api/`): envolturas de `enrich`, del cliente de Merchant (`upload_feed`, `get_product_statuses`), de `on_result` y de `sleep`, que emiten eventos y devuelven lo mismo que el original
- [x] 2 Runner (`api/`) que repite el orden de `main()` del script por cada CSV, con las mismas funciones, mensajes y códigos de salida; en una carpeta, un CSV por vez
- [x] 3 Test de paridad (`tests/`): mismo CSV por el script y por el runner, con modelos y cliente simulados, da el mismo archivo de resultados y las mismas líneas
- [x] 4 Eventos con número de secuencia, snapshot de la ejecución y stream SSE
- [x] 5 Endpoints en FastAPI (`api/`): subir uno o varios CSV a `runs/`, iniciar con las opciones del script, snapshot, eventos, interrumpir y descargar resultados
- [x] 6 Web (`ui/`): nuevo lote, ejecución en curso, terminada, frenada y detalle de una fila
- [x] 7 Interrupción: frena en el próximo punto de observación y guarda las filas terminadas
- [x] 8 Tests de cada escenario del spec (`tests/`)
- [x] 9 `upgrade/front/.gitignore` con `runs/`
