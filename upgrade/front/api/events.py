"""Events of one run, numbered so that a screen can follow them and recover.

Every event carries `seq` (grows by one per run), `type` and `time` (epoch
seconds). A screen asks for the events after the last `seq` it applied, so a
reload replays them in order and never counts a row twice.
"""
from __future__ import annotations

import dataclasses
import enum
import itertools
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

_ids = itertools.count(1)


def to_jsonable(value: Any) -> Any:
    """Turn the pipeline's dataclasses, enums and paths into JSON values."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {k: to_jsonable(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    return value


class Run:
    """One run of the monitor: one or several CSV files, processed in order."""

    def __init__(self, files: List[Path], options: Dict[str, Any], folder: Path) -> None:
        self.id = f'{time.strftime("%Y%m%d-%H%M%S")}-{next(_ids)}'
        self.files = files
        self.options = options
        self.folder = folder
        self.events: List[Dict[str, Any]] = []
        self.results_paths: Dict[int, Path] = {}
        self.finished = False
        self.stop = threading.Event()
        self._seq = 0
        self._lock = threading.Lock()

    def emit(self, type_: str, **data: Any) -> None:
        """Record an event. Never raises: a failing event must not stop the pipeline."""
        try:
            with self._lock:
                self._seq += 1
                event = {'seq': self._seq, 'type': type_, 'time': time.time()}
                event.update(to_jsonable(data))
                self.events.append(event)
        except Exception as error:  # noqa: BLE001 - observing must never break the run
            # Straight to the real stderr: during a run sys.stderr is captured into
            # events, and reporting through it would fail again.
            try:
                sys.__stderr__.write(f'monitor: could not record event {type_}: {error}\n')
            except Exception:  # noqa: BLE001
                pass

    def events_after(self, seq: int) -> List[Dict[str, Any]]:
        """The events with a sequence number above `seq`, in order."""
        with self._lock:
            return [e for e in self.events if e['seq'] > seq]

    def check_stop(self) -> None:
        """Raise KeyboardInterrupt if the user asked to interrupt, as Ctrl-C does."""
        if self.stop.is_set():
            raise KeyboardInterrupt
