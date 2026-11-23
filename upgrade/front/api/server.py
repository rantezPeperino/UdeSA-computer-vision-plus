"""HTTP API of the monitor and the web app.

    POST /api/runs                       upload one CSV or a folder's files, start
    GET  /api/runs/current               the run in progress or the last one
    GET  /api/runs/{id}/events?after=N   events after N (snapshot / polling)
    GET  /api/runs/{id}/stream?after=N   the same, as Server-Sent Events
    POST /api/runs/{id}/interrupt        stop as Ctrl-C does
    GET  /api/runs/{id}/results/{file}   the results CSV of one file
    GET  /                               the web app (upgrade/front/ui)

Credentials and the LLM key are read by the script from the server's
environment variables; the API never receives or returns them.
"""
from __future__ import annotations

import asyncio
import json
import re
import threading
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .events import Run
from .runner import execute, run_lock

FRONT = Path(__file__).resolve().parents[1]
RUNS = FRONT / 'runs'
UI = FRONT / 'ui'

app = FastAPI(title='Deep Tagger · Monitor de lotes')
runs: Dict[str, Run] = {}
last_run: Optional[str] = None

_SAFE_NAME = re.compile(r'^[\w.\- ]+$')


def _csv_files(uploads: List[UploadFile], mode: str) -> List[tuple]:
    """(name, upload) of the CSV to process, in alphabetical order.

    One file: that file. A folder: every .csv of its first level; other files and
    subfolders are ignored, as the user chose a folder of CSV files.
    """
    chosen = []
    for upload in uploads:
        parts = PurePosixPath((upload.filename or '').replace('\\', '/')).parts
        if not parts:
            continue
        name = parts[-1]
        if mode == 'folder':
            if len(parts) != 2 or not name.lower().endswith('.csv'):
                continue
        if not _SAFE_NAME.match(name) or name in ('.', '..'):
            raise HTTPException(400, f'Nombre de archivo no válido: {name}')
        chosen.append((name, upload))
    chosen.sort(key=lambda item: item[0])
    return chosen


@app.post('/api/runs')
async def create_run(
    files: List[UploadFile] = File(...),
    mode: str = Form('file'),
    folder_name: str = Form(''),
    dry_run: bool = Form(False),
    limit: Optional[int] = Form(None),
    wait: int = Form(300),
    out: str = Form(''),
):
    global last_run
    if mode not in ('file', 'folder'):
        raise HTTPException(400, 'mode tiene que ser file o folder')
    chosen = _csv_files(files, mode)
    if mode == 'folder' and not chosen:
        raise HTTPException(400, 'La carpeta no tiene ningún archivo .csv en su primer nivel.')
    if mode == 'file' and len(chosen) != 1:
        raise HTTPException(400, 'Elegí un solo archivo CSV.')
    out = out.strip()
    if out and (len(chosen) != 1 or not _SAFE_NAME.match(out)):
        raise HTTPException(400, '--out solo se puede usar con un único CSV y un nombre de archivo simple.')
    if not run_lock.acquire(blocking=False):
        raise HTTPException(409, 'Ya hay una ejecución en curso.')
    try:
        options = {'dry_run': dry_run, 'limit': limit, 'wait': wait, 'out': out or None}
        run = Run([], options, RUNS)
        folder = RUNS / run.id / (folder_name if _SAFE_NAME.match(folder_name or '') else 'entrada')
        folder.mkdir(parents=True, exist_ok=True)
        paths = []
        for name, upload in chosen:
            target = folder / name
            target.write_bytes(await upload.read())
            paths.append(target)
        run.files = paths
        run.folder = folder
        runs[run.id] = run
        last_run = run.id
    except BaseException:
        run_lock.release()
        raise

    def work():
        try:
            execute(run)
        finally:
            run_lock.release()

    threading.Thread(target=work, name=f'run-{run.id}', daemon=True).start()
    return {'run_id': run.id, 'files': [p.name for p in paths]}


def _get(run_id: str) -> Run:
    run = runs.get(run_id)
    if run is None:
        raise HTTPException(404, 'No existe esa ejecución.')
    return run


@app.get('/api/runs/current')
def current_run():
    return {'run_id': last_run, 'running': run_lock.locked()}


@app.get('/api/runs/{run_id}/events')
def run_events(run_id: str, after: int = 0):
    run = _get(run_id)
    return {'events': run.events_after(after), 'finished': run.finished}


@app.get('/api/runs/{run_id}/stream')
async def run_stream(run_id: str, after: int = 0):
    run = _get(run_id)

    async def generate():
        seq = after
        idle = 0.0
        while True:
            events = run.events_after(seq)
            for event in events:
                seq = event['seq']
                yield f'id: {seq}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n'
            if not events:
                if run.finished:
                    yield 'event: end\ndata: {}\n\n'
                    return
                idle += 0.25
                if idle >= 15:
                    idle = 0.0
                    yield ': heartbeat\n\n'
                await asyncio.sleep(0.25)
            else:
                idle = 0.0

    return StreamingResponse(generate(), media_type='text/event-stream', headers={
        'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no',
    })


@app.post('/api/runs/{run_id}/interrupt')
def interrupt(run_id: str):
    run = _get(run_id)
    run.stop.set()
    return {'interrupting': not run.finished}


@app.get('/api/runs/{run_id}/results/{file_index}')
def results(run_id: str, file_index: int):
    run = _get(run_id)
    path = run.results_paths.get(file_index)
    if path is None or not Path(path).exists():
        raise HTTPException(404, 'Ese archivo todavía no tiene resultados.')
    return FileResponse(path, media_type='text/csv', filename=Path(path).name)


if UI.exists():
    app.mount('/', StaticFiles(directory=UI, html=True), name='ui')
