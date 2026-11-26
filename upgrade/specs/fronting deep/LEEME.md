# Change OpenSpec: add-camino-monitor-media

Monitor "Camino" versión media de Deep Tagger. Validado con `openspec validate --strict` (OpenSpec 2.1.1).

## Cómo usarlo con Claude Code

1. Si el repo todavía no tiene OpenSpec:
   ```
   npm install -g @fission-ai/openspec@latest
   openspec init --tools claude
   ```
2. Copiar la carpeta `openspec/changes/add-camino-monitor-media/` dentro del `openspec/changes/` del repo.
3. Revisar y ajustar `design.md` sección 3 (supuestos de stack) y responder las preguntas abiertas de la sección 14.
4. Validar: `openspec validate add-camino-monitor-media --strict`
5. En Claude Code: `/opsx:apply add-camino-monitor-media` (o pedirle que implemente las tareas de `tasks.md` en orden).
6. Al desplegar: `openspec archive add-camino-monitor-media`

## Contenido

```
openspec/changes/add-camino-monitor-media/
├── .openspec.yaml
├── proposal.md                          por qué, alcance, impacto
├── design.md                            arquitectura, contratos Pydantic, derivación de la vista, escala, tokens
├── tasks.md                             checklist en 8 bloques
└── specs/
    ├── batch-intake/spec.md             carga de CSV o carpeta e inicio
    ├── pipeline-progress-events/spec.md snapshot + SSE con agregados absolutos
    └── camino-monitor/spec.md           la pantalla
```

Diseño de referencia: artboard "Camino · versión media" en https://claude.ai/artifact/TvmQV7qwsE7Uce8RYfUE9C
