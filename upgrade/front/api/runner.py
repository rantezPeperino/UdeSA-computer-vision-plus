"""Runs scripts/publish_from_csv.py for each CSV of a run, under observation.

It does not reimplement the script: it loads the script as a module and calls
its own main(), after putting the observation wrappers in place of the names
main() calls (see observer.py). So the order of the steps, the messages and the
exit codes are the script's.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import sys
import threading
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Optional

from .events import Run
from .observer import FileObserver

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'scripts' / 'publish_from_csv.py'

_script = None
_script_lock = threading.Lock()

# Only one run at a time: the script prints to the process's stdout and the
# models are shared.
run_lock = threading.Lock()


def load_script():
    """The script as a module, loaded once. Loading it sets sys.path as it does."""
    global _script
    with _script_lock:
        if _script is None:
            spec = importlib.util.spec_from_file_location('_front_publish_from_csv', SCRIPT)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _script = module
        return _script


class _LineWriter(io.TextIOBase):
    """Stands in for stdout/stderr: each printed line becomes a `log` event."""

    encoding = 'utf-8'  # so main() does not try to reconfigure it

    def __init__(self, run: Run, file_index: int, stream: str, echo) -> None:
        self._run = run
        self._file = file_index
        self._stream = stream
        self._echo = echo
        self._buffer = ''

    def write(self, text: str) -> int:
        if self._echo is not None:
            try:
                self._echo.write(text)
            except Exception:  # noqa: BLE001 - the console is optional
                pass
        self._buffer += text
        while '\n' in self._buffer:
            line, self._buffer = self._buffer.split('\n', 1)
            self._run.emit('log', file=self._file, stream=self._stream, text=line)
        return len(text)

    def flush(self) -> None:
        if self._echo is not None:
            try:
                self._echo.flush()
            except Exception:  # noqa: BLE001
                pass

    def close_line(self) -> None:
        if self._buffer:
            self._run.emit('log', file=self._file, stream=self._stream, text=self._buffer)
            self._buffer = ''


def _namespace(csv: Path, options: Dict[str, Any]) -> argparse.Namespace:
    """The same arguments parse_args() would give for this CSV and these options."""
    out = options.get('out')
    return argparse.Namespace(
        csv=csv,
        out=Path(csv.parent / out) if out else None,
        limit=options.get('limit'),
        dry_run=bool(options.get('dry_run')),
        wait=int(options.get('wait', 300)),
    )


def run_file(run: Run, index: int, csv: Path, echo: bool = True) -> Dict[str, Any]:
    """Run main() of the script on one CSV. Returns what file.finished reports."""
    module = load_script()
    observer = FileObserver(run, index)
    namespace = _namespace(csv, run.options)
    observer.install(module, lambda: namespace)
    out = _LineWriter(run, index, 'stdout', sys.__stdout__ if echo else None)
    err = _LineWriter(run, index, 'stderr', sys.__stderr__ if echo else None)
    exit_code: Optional[int] = None
    interrupted = False
    crash: Optional[str] = None
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            exit_code = module.main()
    except KeyboardInterrupt:
        interrupted = True
    except Exception as error:  # noqa: BLE001 - shown as the script's traceback would be
        crash = f'{type(error).__name__}: {error}'
    finally:
        observer.uninstall()
        out.close_line()
        err.close_line()
    summary = {
        'file': index,
        'name': csv.name,
        'exit_code': exit_code,
        'interrupted': interrupted,
        'crash': crash,
        'counts': dict(Counter(r.stage for r in observer.results).most_common()),
        'merchant': dict(Counter(s.status for s in observer.statuses.values()).most_common()),
        'results': observer.results_path.name if observer.results_path else None,
    }
    run.emit('file.finished', **summary)
    return summary


def execute(run: Run, echo: bool = True) -> None:
    """Process every CSV of the run, one at a time, in the run's order."""
    run.emit('run.started', files=[f.name for f in run.files], options=run.options)
    finished = []
    try:
        for index, csv in enumerate(run.files):
            if run.stop.is_set():
                break
            run.emit('file.started', file=index, name=csv.name)
            summary = run_file(run, index, csv, echo=echo)
            finished.append({'name': csv.name, 'exit_code': summary['exit_code'],
                             'interrupted': summary['interrupted']})
            if summary['interrupted']:
                break
    finally:
        run.emit('run.finished', files=finished, interrupted=run.stop.is_set())
        run.finished = True
