"""Observation layer: wrappers that report what the pipeline does, and change nothing.

Each wrapper calls the original with the same arguments and returns its result
unchanged. The only points used are the ones the pipeline already exposes:

    read_rows, connect, write_results        functions main() calls by name
    run_batch(enrich=, client=, on_result=)  parameters of the batch
    MerchantClient.upload_feed / get_product_statuses
    wait_for_statuses(client=, sleep=)       parameters of the verdict wait

When the user interrupts, the wrappers raise KeyboardInterrupt at the next of
these points, so main() behaves as with Ctrl-C: the rows already finished are
written to the results file.
"""
from __future__ import annotations

import time
from collections import Counter
from typing import Any, Callable, Dict, List, Optional

from .events import Run


class ObservedClient:
    """A Merchant client that reports each upload and each verdict round."""

    def __init__(self, inner: Any, observer: 'FileObserver') -> None:
        self._inner = inner
        self._observer = observer

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def upload_feed(self, report, products):
        obs = self._observer
        obs.run.check_stop()
        index = obs.current
        obs.run.emit('row.upload.started', file=obs.index, index=index)
        start = time.monotonic()
        results = self._inner.upload_feed(report, products)
        seconds = time.monotonic() - start
        obs.timing(index)['upload'] = seconds
        obs.run.emit('row.upload.finished', file=obs.index, index=index, seconds=seconds,
                     upload=results[0] if results else None)
        return results

    def get_product_statuses(self, product_ids):
        obs = self._observer
        statuses = self._inner.get_product_statuses(product_ids)
        obs.rounds += 1
        obs.run.emit('verdict.round', file=obs.index, round=obs.rounds, statuses=statuses,
                     pending=sum(1 for s in statuses if s.status == 'pending'))
        return statuses


class FileObserver:
    """Wrappers for one CSV of the run; `install` puts them in the script module."""

    def __init__(self, run: Run, index: int) -> None:
        self.run = run
        self.index = index
        self.current = 0
        self.rounds = 0
        self.timings: Dict[int, Dict[str, float]] = {}
        self.results: List[Any] = []
        self.statuses: Dict[str, Any] = {}
        self.results_path: Optional[Any] = None
        self._originals: Dict[str, Callable] = {}

    def timing(self, index: int) -> Dict[str, float]:
        return self.timings.setdefault(index, {})

    # ── install / uninstall ──────────────────────────────────────────────────
    def install(self, module, parse_args: Callable) -> None:
        """Replace, in the loaded script module only, the names main() calls."""
        names = ('parse_args', 'read_rows', 'connect', 'run_batch',
                 'wait_for_statuses', 'write_results')
        self._originals = {name: getattr(module, name) for name in names}
        self._module = module
        module.parse_args = parse_args
        module.read_rows = self._read_rows
        module.connect = self._connect
        module.run_batch = self._run_batch
        module.wait_for_statuses = self._wait_for_statuses
        module.write_results = self._write_results

    def uninstall(self) -> None:
        for name, original in self._originals.items():
            setattr(self._module, name, original)

    # ── wrappers ─────────────────────────────────────────────────────────────
    def _read_rows(self, path):
        try:
            rows = self._originals['read_rows'](path)
        except (OSError, ValueError) as error:
            self.run.emit('file.read', file=self.index, error=str(error))
            raise
        self.run.emit('file.read', file=self.index, rows=len(rows))
        return rows

    def _connect(self):
        setup_error = self._module.SetupError
        try:
            client = self._originals['connect']()
        except setup_error as error:
            self.run.emit('setup.failed', file=self.index, message=str(error))
            raise
        provider = None
        try:
            from llm import description_client  # same lookup connect() just did
            provider = description_client.provider()
        except Exception:  # noqa: BLE001 - only for display
            pass
        credentials = getattr(client, 'credentials', None)
        environment = getattr(client, 'environment', None)
        self.run.emit('setup.connected', file=self.index, provider=provider,
                      account=getattr(credentials, 'merchant_id', None),
                      environment=environment)
        return client

    def _run_batch(self, rows, client=None, dry_run=False, enrich=None, on_result=None):
        total = len(rows)
        real_enrich = enrich

        def started(i: int) -> None:
            if i < total:
                self.current = i
                self.timing(i)['start'] = time.monotonic()
                row = rows[i]
                self.run.emit('row.started', file=self.index, index=i, total=total,
                              product_id=row.product_id, image_url=row.image_url,
                              business=row.business)

        def observed_enrich(row):
            nonlocal real_enrich
            self.run.check_stop()
            if real_enrich is None:
                self.run.emit('models.loading', file=self.index)
                start = time.monotonic()
                from positioner.enrichment.field_generator import enrich_product
                real_enrich = enrich_product
                self.run.emit('models.loaded', file=self.index, seconds=time.monotonic() - start)
            index = self.current
            self.run.emit('row.enrich.started', file=self.index, index=index)
            start = time.monotonic()
            try:
                enriched = real_enrich(row)
            except Exception as error:
                seconds = time.monotonic() - start
                self.timing(index)['enrich'] = seconds
                self.run.emit('row.enrich.finished', file=self.index, index=index,
                              seconds=seconds, error=str(error))
                raise
            seconds = time.monotonic() - start
            self.timing(index)['enrich'] = seconds
            self.run.emit('row.enrich.finished', file=self.index, index=index,
                          seconds=seconds, enriched=enriched)
            return enriched

        def observed_on_result(index, result):
            if on_result is not None:
                on_result(index, result)
            self.results.append(result)
            timing = self.timing(index)
            timing['total'] = time.monotonic() - timing.get('start', time.monotonic())
            self.run.emit('row.finished', file=self.index, index=index, total=total,
                          result=result,
                          timings={k: v for k, v in timing.items() if k != 'start'})
            self.run.check_stop()
            started(index + 1)

        started(0)
        observed_client = ObservedClient(client, self) if client is not None else None
        return self._originals['run_batch'](
            rows, client=observed_client, dry_run=dry_run,
            enrich=observed_enrich, on_result=observed_on_result,
        )

    def _wait_for_statuses(self, client, product_ids, timeout_s=300, interval_s=15,
                           sleep=time.sleep, clock=time.monotonic):
        self.run.emit('verdict.started', file=self.index, products=len(product_ids),
                      timeout=timeout_s, interval=interval_s)

        def observed_sleep(seconds):
            self.run.emit('verdict.waiting', file=self.index, seconds=seconds)
            end = clock() + seconds
            while True:
                self.run.check_stop()
                remaining = end - clock()
                if remaining <= 0:
                    break
                sleep(min(0.5, remaining))

        try:
            statuses = self._originals['wait_for_statuses'](
                ObservedClient(client, self), product_ids, timeout_s=timeout_s,
                interval_s=interval_s, sleep=observed_sleep, clock=clock,
            )
        except Exception as error:
            self.run.emit('verdict.failed', file=self.index, error=str(error))
            raise
        self.statuses = statuses
        self.run.emit('verdict.finished', file=self.index,
                      statuses=list(statuses.values()),
                      counts=dict(Counter(s.status for s in statuses.values())))
        return statuses

    def _write_results(self, path, results, statuses):
        self._originals['write_results'](path, results, statuses)
        self.results_path = path
        self.run.results_paths[self.index] = path
        self.run.emit('results.written', file=self.index, path=path.name,
                      rows=len(results), statuses=len(statuses))
