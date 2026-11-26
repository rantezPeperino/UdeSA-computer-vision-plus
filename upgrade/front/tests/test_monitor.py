"""Tests of upgrade/front/spec.md: the monitor runs the script as it is and only observes it.

Run from the repo root:
    python -m unittest discover -s upgrade/front/tests -v
"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import time
import unittest
from pathlib import Path

import helpers  # noqa: F401 - sets sys.path

helpers.install_fake_models()

from api import events as events_module  # noqa: E402
from api.events import Run, to_jsonable  # noqa: E402
from api.observer import FileObserver  # noqa: E402
from api.runner import execute, load_script  # noqa: E402
from positioner.automation.batch import read_rows, run_batch  # noqa: E402

DRY = {'dry_run': True, 'limit': None, 'wait': 300, 'out': None}
UPLOAD = {'dry_run': False, 'limit': None, 'wait': 300, 'out': None}


def _run_script(csv: Path, *args: str):
    """The script, as from the terminal: returns exit code, stdout lines, stderr lines."""
    module = load_script()
    out, err = io.StringIO(), io.StringIO()
    argv = sys.argv
    sys.argv = ['publish_from_csv.py', str(csv), *args]
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = module.main()
    finally:
        sys.argv = argv
    return code, out.getvalue().splitlines(), err.getvalue().splitlines()


def _monitor(files, options, folder: Path) -> Run:
    run = Run(list(files), dict(options), folder)
    execute(run, echo=False)
    return run


def _of(run: Run, type_: str, file: int = 0):
    return [e for e in run.events if e['type'] == type_ and e.get('file', file) == file]


def _log(run: Run, stream: str, file: int = 0):
    return [e['text'] for e in _of(run, 'log', file) if e['stream'] == stream]


class _Temp(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.script = load_script()
        self._connect = self.script.connect
        helpers.on_enrich.clear()

    def tearDown(self) -> None:
        self.script.connect = self._connect
        helpers.on_enrich.clear()
        self._tmp.cleanup()

    def folder(self, name: str) -> Path:
        path = self.tmp / name
        path.mkdir()
        return path


class SameFlowAsScript(_Temp):
    """Requirement: Same flow as the script."""

    def _parity(self, options, *args):
        a = helpers.write_csv(self.folder('terminal'), 'ropa.csv')
        b = helpers.write_csv(self.folder('monitor'), 'ropa.csv')
        code, out, err = _run_script(a, *args)
        run = _monitor([b], options, b.parent)
        finished = _of(run, 'file.finished')[0]
        normalize = lambda lines, p: [line.replace(str(p.parent), '<dir>') for line in lines]
        self.assertEqual(finished['exit_code'], code)
        self.assertEqual(normalize(_log(run, 'stdout'), b), normalize(out, a))
        self.assertEqual(_log(run, 'stderr'), err)
        self.assertEqual((b.parent / 'ropa_results.csv').read_text(encoding='utf-8'),
                         (a.parent / 'ropa_results.csv').read_text(encoding='utf-8'))
        return run

    def test_same_output_as_the_terminal_dry_run(self):
        run = self._parity(DRY, '--dry-run')
        self.assertEqual(_of(run, 'file.finished')[0]['exit_code'], 1)
        self.assertEqual(_of(run, 'setup.connected'), [])

    def test_same_output_as_the_terminal_upload(self):
        self.script.connect = helpers.fake_connect
        run = self._parity(UPLOAD)
        finished = _of(run, 'file.finished')[0]
        self.assertEqual(finished['merchant'], {'approved': 1, 'disapproved': 1})
        self.assertEqual(_of(run, 'setup.connected')[0]['environment'], 'test')

    def test_bad_csv_ends_that_file_and_goes_on(self):
        folder = self.folder('lote')
        bad = helpers.write_csv(folder, 'a.csv', header='id,image_url,brand')
        good = helpers.write_csv(folder, 'b.csv')
        run = _monitor([bad, good], DRY, folder)
        self.assertEqual(_of(run, 'file.finished', 0)[0]['exit_code'], 2)
        self.assertIn('missing columns', _of(run, 'file.read', 0)[0]['error'])
        self.assertEqual(_of(run, 'row.started', 0), [])
        self.assertEqual(_of(run, 'file.finished', 1)[0]['exit_code'], 1)

    def test_missing_key_stops_before_the_models(self):
        def failing():
            raise self.script.SetupError('Missing the language model key')
        self.script.connect = failing
        csv = helpers.write_csv(self.folder('lote'), 'a.csv')
        run = _monitor([csv], UPLOAD, csv.parent)
        self.assertEqual(_of(run, 'file.finished')[0]['exit_code'], 2)
        self.assertEqual(_of(run, 'setup.failed')[0]['message'], 'Missing the language model key')
        self.assertEqual(_of(run, 'models.loading'), [])
        self.assertIn('Missing the language model key', _log(run, 'stderr'))

    def test_verdict_not_waited(self):
        self.script.connect = helpers.fake_connect
        csv = helpers.write_csv(self.folder('lote'), 'a.csv')
        run = _monitor([csv], dict(UPLOAD, wait=0), csv.parent)
        self.assertIn("Not waiting for Google's verdict. It shows up in Merchant Center → Products.",
                      _log(run, 'stdout'))
        self.assertEqual(_of(run, 'verdict.started'), [])


class ObservationWithoutChange(_Temp):
    """Requirement: Observation without changing behavior."""

    def test_results_do_not_depend_on_the_observer(self):
        csv = helpers.write_csv(self.folder('lote'), 'a.csv')
        rows = read_rows(csv)
        plain = run_batch(rows, client=helpers.FakeClient(), enrich=helpers.fake_enrich)
        observer = FileObserver(Run([csv], UPLOAD, csv.parent), 0)
        observer._originals = {'run_batch': run_batch}
        observed = observer._run_batch(rows, client=helpers.FakeClient(), enrich=helpers.fake_enrich)
        self.assertEqual(to_jsonable(observed), to_jsonable(plain))

    def test_observer_failure_does_not_stop_the_pipeline(self):
        ok = helpers.write_csv(self.folder('normal'), 'a.csv')
        _monitor([ok], DRY, ok.parent)
        broken = helpers.write_csv(self.folder('roto'), 'a.csv')
        original = events_module.to_jsonable
        events_module.to_jsonable = lambda value: 1 / 0
        try:
            _monitor([broken], DRY, broken.parent)
        finally:
            events_module.to_jsonable = original
        self.assertEqual((broken.parent / 'a_results.csv').read_text(encoding='utf-8'),
                         (ok.parent / 'a_results.csv').read_text(encoding='utf-8'))


class ProgressEvents(_Temp):
    """Requirement: Progress events."""

    def setUp(self):
        super().setUp()
        self.script.connect = helpers.fake_connect
        csv = helpers.write_csv(self.folder('lote'), 'a.csv')
        self.run_ = _monitor([csv], UPLOAD, csv.parent)

    def test_sequence_grows_by_one(self):
        seqs = [e['seq'] for e in self.run_.events]
        self.assertEqual(seqs, list(range(1, len(seqs) + 1)))

    def test_every_row_starts_and_finishes(self):
        self.assertEqual([e['index'] for e in _of(self.run_, 'row.started')], [0, 1, 2, 3, 4])
        self.assertEqual([e['index'] for e in _of(self.run_, 'row.finished')], [0, 1, 2, 3, 4])

    def test_row_cut_at_the_brand_check_has_no_enrich(self):
        enriched = {e['index'] for e in _of(self.run_, 'row.enrich.started')}
        finished = {e['index']: e['result'] for e in _of(self.run_, 'row.finished')}
        self.assertNotIn(1, enriched)
        self.assertEqual(finished[1]['stage'], 'invalid')
        self.assertEqual(finished[1]['reasons'], ['missing_size'])

    def test_row_finished_carries_the_pipeline_result(self):
        first = _of(self.run_, 'row.finished')[0]
        self.assertEqual(first['result']['stage'], 'uploaded')
        self.assertEqual(first['result']['enriched']['predicted_color'], 'gray')
        self.assertEqual(first['result']['product']['price'], '45999.00 ARS')
        self.assertIn('enrich', first['timings'])
        self.assertIn('upload', first['timings'])

    def test_uploads_and_verdict_rounds_are_reported(self):
        self.assertEqual(len(_of(self.run_, 'row.upload.finished')), 2)
        self.assertEqual(_of(self.run_, 'verdict.round')[0]['pending'], 0)

    def test_events_after_a_reload(self):
        middle = self.run_.events[len(self.run_.events) // 2]['seq']
        replay = self.run_.events_after(0)
        tail = self.run_.events_after(middle)
        self.assertEqual(replay[middle:], tail)


class Interruption(_Temp):
    """Requirement: Interruption."""

    def test_interrupt_keeps_finished_rows_and_skips_next_files(self):
        folder = self.folder('lote')
        first = helpers.write_csv(folder, 'a.csv')
        second = helpers.write_csv(folder, 'b.csv')
        run = Run([first, second], DRY, folder)
        helpers.on_enrich.append(lambda n: run.stop.set() if n == 2 else None)
        execute(run, echo=False)
        finished = _of(run, 'file.finished', 0)[0]
        self.assertTrue(finished['interrupted'])
        written = (folder / 'a_results.csv').read_text(encoding='utf-8').splitlines()
        self.assertEqual(len(written) - 1, sum(finished['counts'].values()))
        self.assertEqual(_of(run, 'file.started', 1), [])
        self.assertTrue(_of(run, 'run.finished')[0]['interrupted'])


class Server(_Temp):
    """Requirements: CSV or folder input, Downloads, Server-side secrets."""

    def setUp(self):
        super().setUp()
        from fastapi.testclient import TestClient
        from api import server
        server.RUNS = self.tmp / 'runs'
        self.server = server
        self.http = TestClient(server.app)
        self.csv = '\n'.join([helpers.HEADER, *helpers.ROWS]) + '\n'

    def _wait(self, run_id):
        for _ in range(200):
            body = self.http.get(f'/api/runs/{run_id}/events').json()
            if body['finished']:
                return body['events']
            time.sleep(0.05)
        self.fail('the run did not finish')

    def test_folder_takes_first_level_csv_in_order(self):
        files = [
            ('files', ('lote/b.csv', self.csv, 'text/csv')),
            ('files', ('lote/a.csv', self.csv, 'text/csv')),
            ('files', ('lote/notas.txt', 'x', 'text/plain')),
            ('files', ('lote/sub/c.csv', self.csv, 'text/csv')),
        ]
        response = self.http.post('/api/runs', files=files,
                                  data={'mode': 'folder', 'folder_name': 'lote', 'dry_run': 'true'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['files'], ['a.csv', 'b.csv'])
        events = self._wait(response.json()['run_id'])
        self.assertEqual([e['name'] for e in events if e['type'] == 'file.finished'], ['a.csv', 'b.csv'])

    def test_folder_without_csv(self):
        files = [('files', ('lote/notas.txt', 'x', 'text/plain'))]
        response = self.http.post('/api/runs', files=files, data={'mode': 'folder'})
        self.assertEqual(response.status_code, 400)

    def test_results_file_can_be_downloaded(self):
        files = [('files', ('ropa.csv', self.csv, 'text/csv'))]
        run_id = self.http.post('/api/runs', files=files, data={'dry_run': 'true'}).json()['run_id']
        self._wait(run_id)
        response = self.http.get(f'/api/runs/{run_id}/results/0')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.text.startswith(
            'id,image_url,stage,merchant_status,reasons,title,google_product_category,predicted_color,description'))

    def test_screen_gets_no_secrets(self):
        self.script.connect = helpers.fake_connect
        files = [('files', ('ropa.csv', self.csv, 'text/csv'))]
        run_id = self.http.post('/api/runs', files=files, data={'wait': '0'}).json()['run_id']
        events = self._wait(run_id)
        self.assertNotIn('/fake/key.json', str(events))
        connected = [e for e in events if e['type'] == 'setup.connected'][0]
        self.assertEqual(set(connected) - {'seq', 'type', 'time', 'file'},
                         {'provider', 'account', 'environment'})


if __name__ == '__main__':
    unittest.main()
