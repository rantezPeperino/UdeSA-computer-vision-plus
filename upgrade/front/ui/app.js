/* Deep Tagger · Monitor de lotes.
 *
 * Shows what scripts/publish_from_csv.py does, live. Every value on screen comes
 * from an event of the API (upgrade/front/api), and the events come from the
 * pipeline's own output. The screen state is rebuilt by applying the events in
 * order (reduce), so a reload replays them and never counts a row twice.
 */
'use strict';

const app = document.getElementById('app');
const modalRoot = document.getElementById('modal-root');

// ── helpers ──────────────────────────────────────────────────────────────────
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const secs = (s) => (s == null ? '' : `${s.toFixed(1).replace('.', ',')} s`);
const clock = (s) => {
  s = Math.max(0, Math.floor(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  const mm = String(m).padStart(2, '0'), ss = String(r).padStart(2, '0');
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
};
const now = () => Date.now() / 1000;

const ICON = {
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="m9 15 2 2 4-4"/>',
  plug: '<path d="M12 22v-5"/><path d="M9 8V2"/><path d="M15 8V2"/><path d="M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8Z"/>',
  cpu: '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M15 2v2M9 2v2M15 20v2M9 20v2M2 15h2M2 9h2M20 15h2M20 9h2"/>',
  clipboard: '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M9 12h6M9 16h6"/>',
  sparkles: '<path d="M9.9 15.5A2 2 0 0 0 8.5 14.1l-6.1-1.6a.5.5 0 0 1 0-1l6.1-1.6a2 2 0 0 0 1.4-1.4l1.6-6.1a.5.5 0 0 1 1 0l1.6 6.1a2 2 0 0 0 1.4 1.4l6.1 1.6a.5.5 0 0 1 0 1l-6.1 1.6a2 2 0 0 0-1.4 1.4l-1.6 6.1a.5.5 0 0 1-1 0z"/>',
  shield: '<path d="M20 13c0 5-3.5 7.5-7.7 9a1 1 0 0 1-.7 0C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.2-2.7a1.2 1.2 0 0 1 1.6 0C14.5 3.8 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
  upload: '<path d="M12 13v8"/><path d="m8 17 4-4 4 4"/><path d="M20 16.6A5 5 0 0 0 18 7h-1.3A8 8 0 1 0 4 15.3"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  report: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8M16 17H8M10 9H8"/>',
  folder: '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9l-.8-1.2A2 2 0 0 0 7.9 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
  doc: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
  cloud: '<path d="M12 13v8"/><path d="m8 17 4-4 4 4"/><path d="M20 16.6A5 5 0 0 0 18 7h-1.3A8 8 0 1 0 4 15.3"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/>',
};
const svg = (name, size = 26) => `<svg aria-hidden="true" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICON[name]}</svg>`;

const OK_STAGES = ['uploaded', 'dry_run'];
const stageClass = (stage) => (OK_STAGES.includes(stage) ? 'ok'
  : (stage === 'invalid' || stage === 'download_failed') ? 'warn' : 'err');
const stageChip = (stage) => ({ ok: 'chip-ok', warn: 'chip-warn', err: 'chip-err' }[stageClass(stage)]);

// ── state: rebuilt from the events ───────────────────────────────────────────
function emptyRun(id) {
  return { id, files: [], options: {}, startedAt: null, finishedAt: null, finished: false,
           interrupted: false, lastSeq: 0, selected: 0, follow: true, interrupting: false };
}

function emptyFile(name) {
  return { name, status: 'waiting', startedAt: null, finishedAt: null, read: null, setup: null,
           models: null, total: null, rows: [], current: null, log: [], verdict: null,
           results: null, summary: null };
}

function apply(run, e) {
  if (e.seq <= run.lastSeq) return;           // already applied: never twice
  run.lastSeq = e.seq;
  const f = e.file != null ? run.files[e.file] : null;
  switch (e.type) {
    case 'run.started':
      run.files = e.files.map(emptyFile); run.options = e.options; run.startedAt = e.time; break;
    case 'file.started':
      f.status = 'running'; f.startedAt = e.time; if (run.follow) run.selected = e.file; break;
    case 'file.read': f.read = e.error ? { error: e.error } : { rows: e.rows }; break;
    case 'log': f.log.push({ stream: e.stream, text: e.text }); break;
    case 'setup.connected': f.setup = { provider: e.provider, account: e.account, environment: e.environment }; break;
    case 'setup.failed': f.setup = { failed: e.message }; break;
    case 'models.loading': f.models = { loading: e.time }; break;
    case 'models.loaded': f.models = { ...(f.models || {}), seconds: e.seconds }; break;
    case 'row.started':
      f.total = e.total;
      f.rows[e.index] = { index: e.index, productId: e.product_id, imageUrl: e.image_url,
                          business: e.business, step: 'brand', startedAt: e.time, timings: {} };
      f.current = e.index; break;
    case 'row.enrich.started': f.rows[e.index].step = 'enrich'; f.rows[e.index].enrichAt = e.time; break;
    case 'row.enrich.finished': {
      const r = f.rows[e.index];
      r.enriched = e.enriched || null; r.enrichError = e.error || null; r.timings.enrich = e.seconds;
      r.step = 'build'; r.buildAt = e.time; break;
    }
    case 'row.upload.started': f.rows[e.index].step = 'upload'; f.rows[e.index].uploadAt = e.time; break;
    case 'row.upload.finished': f.rows[e.index].upload = e.upload; f.rows[e.index].timings.upload = e.seconds; break;
    case 'row.finished': {
      const r = f.rows[e.index];
      r.result = e.result; r.timings = e.timings; r.endStep = r.step; r.step = 'done'; r.finishedAt = e.time;
      if (f.current === e.index) f.current = null;
      f.lastDone = e.index; break;
    }
    case 'verdict.started':
      f.verdict = { started: e.time, products: e.products, timeout: e.timeout, interval: e.interval, rounds: [] }; break;
    case 'verdict.round':
      f.verdict.rounds.push({ round: e.round, pending: e.pending, at: e.time });
      for (const s of e.statuses) f.verdict.byId = { ...(f.verdict.byId || {}), [s.product_id]: s };
      f.verdict.nextAt = null; break;
    case 'verdict.waiting': f.verdict.nextAt = e.time + e.seconds; break;
    case 'verdict.finished':
      f.verdict.finished = e.counts; f.verdict.nextAt = null;
      for (const st of e.statuses || []) f.verdict.byId = { ...(f.verdict.byId || {}), [st.product_id]: st };
      break;
    case 'verdict.failed': f.verdict.failed = e.error; f.verdict.nextAt = null; break;
    case 'results.written': f.results = e.path; break;
    case 'file.finished': f.summary = e; f.status = 'finished'; f.finishedAt = e.time; f.current = null; break;
    case 'run.finished': run.finished = true; run.finishedAt = e.time; run.interrupted = e.interrupted; break;
    default: break;
  }
}

// ── node states of one file ──────────────────────────────────────────────────
function done(file) { return file.rows.filter((r) => r && r.result); }
function countBy(rows, fn) { const c = {}; for (const r of rows) { const k = fn(r); if (k) c[k] = (c[k] || 0) + 1; } return c; }
const fmtCounts = (c) => Object.entries(c).map(([k, v]) => `${v} ${k}`).join(' · ');

function nodes(run, file) {
  const finished = file.status === 'finished';
  const notRun = (label = 'No se ejecutó') => ({ state: 'idle', detail: label });
  const dry = !!run.options.dry_run;
  const rows = done(file);
  const current = file.current != null ? file.rows[file.current] : null;
  const n = {};

  // 1 · Preparación
  if (file.read?.error) n.read = { state: 'failed', badge: 'err', detail: 'salida 2' };
  else if (file.read) n.read = { state: 'done', detail: `${file.read.rows} prendas` };
  else n.read = file.status === 'running' ? { state: 'running', detail: 'read_rows' } : notRun('');

  if (dry) n.connect = { state: 'skipped', detail: '--dry-run' };
  else if (file.setup?.failed) n.connect = { state: 'failed', badge: 'err', detail: 'SetupError' };
  else if (file.setup) n.connect = { state: 'done', detail: [file.setup.provider, file.setup.account && `cuenta ${file.setup.account}`, file.setup.environment].filter(Boolean).join(' · ') };
  else if (file.read?.rows != null && !finished) n.connect = { state: 'running', detail: 'connect()' };
  else n.connect = finished || file.read?.error ? notRun() : notRun('');

  if (file.models?.seconds != null) n.models = { state: 'done', detail: clock(file.models.seconds) };
  else if (file.models) n.models = { state: 'running', detail: clock(now() - file.models.loading) };
  else n.models = finished ? notRun() : notRun('');

  // 2 · Por cada fila
  const ended = (step) => rows.filter((r) => r.endStep === step);
  const passed = (steps) => file.rows.filter((r) => r && (steps.includes(r.step) || (r.endStep && steps.includes(r.endStep)) || r.step === 'done' && steps.includes(r.endStep))).length;
  const rowNode = (step, failedHere, okLabel) => {
    const running = current && current.step === step;
    const fails = countBy(failedHere, (r) => r.result.stage);
    const failText = fmtCounts(fails);
    let state = 'idle';
    if (running) state = 'running';
    else if (okLabel || failText) state = finished ? 'done' : 'passed';
    const detail = running ? `${current.productId || '(id de la URL)'} · ${secs(now() - (current[`${step}At`] || current.startedAt))}`
      : [okLabel, failText].filter(Boolean).join(' · ');
    return { state, badge: failText ? 'warn' : null, detail };
  };
  const afterBrand = file.rows.filter((r) => r && (r.enrichAt != null)).length;
  const afterEnrich = file.rows.filter((r) => r && r.buildAt != null && !(r.endStep === 'build' && r.result?.stage === 'download_failed')).length;
  const enrichFails = rows.filter((r) => r.endStep === 'enrich' || (r.endStep === 'build' && ['download_failed', 'error'].includes(r.result.stage) && r.enrichError !== undefined && (r.result.stage === 'download_failed' || r.enrichError)));
  const buildFails = rows.filter((r) => r.endStep === 'build' && !enrichFails.includes(r) && !OK_STAGES.includes(r.result.stage));
  const uploads = rows.filter((r) => r.endStep === 'upload');
  const noRows = file.total == null;
  n.brand = noRows && finished ? notRun() : rowNode('brand', ended('brand'), afterBrand ? `${afterBrand} ok` : '');
  n.enrich = noRows && finished ? notRun() : rowNode('enrich', enrichFails, afterEnrich ? `${afterEnrich} ok` : '');
  const dryOk = rows.filter((r) => r.result.stage === 'dry_run').length;
  n.build = noRows && finished ? notRun() : rowNode('build', buildFails, dry ? (dryOk ? `${dryOk} dry_run` : '') : (file.rows.filter((r) => r && r.uploadAt != null).length ? `${file.rows.filter((r) => r && r.uploadAt != null).length} ok` : ''));
  if (dry) n.upload = { state: 'skipped', detail: '--dry-run' };
  else if (noRows && finished) n.upload = notRun();
  else {
    const up = uploads.filter((r) => r.result.stage === 'uploaded').length;
    n.upload = rowNode('upload', uploads.filter((r) => r.result.stage !== 'uploaded'), up ? `${up} uploaded` : '');
  }

  // 3 · Cierre del archivo
  const v = file.verdict;
  if (dry) n.verdict = { state: 'skipped', detail: '--dry-run' };
  else if (v?.failed) n.verdict = { state: 'failed', badge: 'err', detail: 'no se pudieron leer' };
  else if (v?.finished) n.verdict = { state: 'done', badge: v.finished.disapproved ? 'warn' : null, detail: fmtCounts(v.finished) };
  else if (v) {
    const next = v.nextAt ? ` · próxima en ${Math.max(0, Math.ceil(v.nextAt - now()))} s` : '';
    n.verdict = { state: 'running', detail: `ronda ${v.rounds.length || 1}${next}` };
  } else if (run.options.wait === 0) n.verdict = { state: 'skipped', detail: '--wait 0' };
  else n.verdict = finished ? notRun() : { state: 'idle', detail: `hasta ${run.options.wait} s, cada 15 s` };

  if (file.results && finished) n.results = { state: 'done', detail: file.results };
  else if (file.results) n.results = { state: 'passed', detail: file.results };
  else n.results = finished ? notRun() : { state: 'idle', detail: '' };
  return n;
}

// ── views ────────────────────────────────────────────────────────────────────
function nodeHtml(name, icon, node) {
  const badge = node.badge ? `<span aria-hidden="true" class="badge ${node.badge}">${node.badge === 'err' ? '✕' : '!'}</span>` : '';
  const label = `${name}: ${({ idle: 'sin empezar', running: 'en curso', passed: 'en curso, con filas terminadas', done: 'terminado', failed: 'falló', skipped: 'salteado' })[node.state]}. ${node.detail || ''}`;
  return `<div class="node ${node.state}" role="listitem" aria-label="${esc(label)}">
    <div class="disc ${node.state}">${svg(icon)}${badge}</div>
    <div class="node-name">${esc(name)}</div>
    <div class="node-detail">${esc(node.detail || '')}</div></div>`;
}

function trackHtml(color, left, right, fill, fillColor) {
  return `<div class="track" style="left:${left}%;right:${right}%;background:${color}"></div>` +
    (fill > 0 ? `<div class="track" style="left:${left}%;width:${(100 - left - right) * Math.min(1, fill)}%;background:${fillColor}"></div>` : '');
}

function pathHtml(run, file) {
  const n = nodes(run, file);
  const finishedRows = done(file).length;
  const total = file.total ?? file.read?.rows;
  const stoppedEarly = file.status === 'finished' && file.total == null;
  const p1Failed = n.read.state === 'failed' || n.connect.state === 'failed';
  return `<div class="path-scroll"><div class="path">
    <div class="band band-1"><div class="band-title"><span>1 · Preparación</span></div>
      <div class="nodes" role="list">${trackHtml(p1Failed ? 'var(--err-soft)' : 'var(--p1-line)', 16, 16, 0)}
        ${nodeHtml('Leer el CSV', 'file', n.read)}${nodeHtml('Clave del LLM y Merchant Center', 'plug', n.connect)}${nodeHtml('Cargar los modelos', 'cpu', n.models)}</div></div>
    <div class="band band-2 ${stoppedEarly ? 'off' : ''}"><div class="band-title"><span>2 · Por cada fila</span><span>${total != null ? `${finishedRows} de ${file.total ?? total}` : ''}</span></div>
      <div class="nodes" role="list">${trackHtml('var(--p2-track)', 12, 12, total ? finishedRows / total : 0, 'var(--p2-line)')}
        ${nodeHtml('Revisar los datos de la marca', 'clipboard', n.brand)}${nodeHtml('Bajar la foto y atribuirla', 'sparkles', n.enrich)}${nodeHtml('Armar y validar el producto', 'shield', n.build)}${nodeHtml('Subir a Merchant Center', 'upload', n.upload)}</div></div>
    <div class="band band-3 ${stoppedEarly ? 'off' : ''}"><div class="band-title"><span>3 · Cierre del archivo</span></div>
      <div class="nodes" role="list">${trackHtml('var(--p3-track)', 25, 25, file.status === 'finished' && !stoppedEarly ? 1 : 0, 'var(--p3-line)')}
        ${nodeHtml('Esperar el veredicto de Google', 'clock', n.verdict)}${nodeHtml('Escribir los resultados', 'report', n.results)}</div></div>
  </div></div>`;
}

function fileNote(run, file) {
  const s = file.summary;
  if (file.read?.error) return { text: file.read.error, mono: true };
  if (file.setup?.failed) return { text: file.setup.failed, mono: true };
  if (s?.crash) return { text: s.crash, mono: true };
  const counts = fmtCountsColon(countBy(done(file), (r) => r.result.stage));
  const merchant = file.verdict?.finished ? fmtCountsColon(file.verdict.finished) : '';
  if (file.status === 'waiting') return { text: 'En espera', mono: false };
  return { text: [counts, merchant].filter(Boolean).join(' · '), mono: true };
}
const fmtCountsColon = (c) => Object.entries(c).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k}: ${v}`).join(' · ');

function fileStatus(file) {
  const s = file.summary;
  if (file.status === 'waiting') return ['En espera', 'chip-idle'];
  if (file.status === 'running') return ['Procesando', 'chip-run'];
  if (s?.interrupted) return ['Interrumpido', 'chip-warn'];
  if (s?.crash) return ['Error', 'chip-err'];
  if (s?.exit_code === 2) return ['Salida 2', 'chip-err'];
  if (s?.exit_code === 1) return ['Salida 1', 'chip-warn'];
  if (s?.exit_code === 0) return ['Salida 0', 'chip-ok'];
  return ['Terminado', 'chip-idle'];
}

function filesHtml(run) {
  return `<section class="card" aria-labelledby="files-h"><div class="card-head"><h2 id="files-h">Archivos</h2>
    <span class="muted">Se procesan de a uno, en orden alfabético</span></div>
    ${run.files.map((file, i) => {
      const [label, chip] = fileStatus(file);
      const total = file.total ?? file.read?.rows;
      const finished = done(file).length;
      const pct = total ? Math.round((finished / total) * 100) : (file.status === 'finished' ? 100 : 0);
      const barColor = file.read?.error || file.setup?.failed ? 'var(--err-soft)' : file.status === 'running' ? 'var(--run)' : file.status === 'finished' ? 'var(--ok-line)' : 'var(--idle-line)';
      const note = fileNote(run, file);
      return `<button type="button" class="file-row ${i === run.selected ? 'selected' : ''}" data-action="select" data-file="${i}">
        <span class="name">${esc(file.name)}</span><span class="chip ${chip}">${label}</span>
        <span class="bar"><span class="bar-track"><span class="bar-fill" style="width:${pct}%;background:${barColor}"></span></span>
        <span class="bar-count">${total != null ? `${finished} / ${total}` : '—'}</span></span>
        <span class="note ${note.mono ? 'mono' : ''}">${esc(note.text)}</span></button>`;
    }).join('')}</section>`;
}

function stepRow(label, state, time) {
  return `<li><span class="st ${state}"></span><span>${esc(label)}</span><span class="t">${esc(time)}</span></li>`;
}

function rowSteps(row) {
  const order = ['brand', 'enrich', 'build', 'upload'];
  const names = { brand: 'Revisar los datos de la marca', enrich: 'Bajar la foto y atribuirla', build: 'Armar y validar el producto', upload: 'Subir a Merchant Center' };
  const at = row.step === 'done' ? row.endStep : row.step;
  const pos = order.indexOf(at);
  const ok = row.result ? OK_STAGES.includes(row.result.stage) : true;
  return order.map((step, i) => {
    let state = '';
    if (i < pos) state = 'done';
    else if (i === pos) state = row.result ? (ok ? 'done' : 'failed') : 'running';
    let time = '';
    if (step === 'enrich' && row.timings?.enrich != null) time = secs(row.timings.enrich);
    else if (step === 'upload' && row.timings?.upload != null) time = secs(row.timings.upload);
    else if (state === 'running') time = `${secs(now() - (row[`${step}At`] || row.startedAt))}…`;
    else if (state === 'done' || state === 'failed') time = step === 'brand' || step === 'build' ? '' : time;
    return stepRow(names[step], state, time);
  }).join('');
}

function businessKv(business) {
  return Object.entries(business || {}).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
}

function photoHtml(url, big) {
  return url ? `<img class="photo ${big ? 'photo-big' : ''}" src="${esc(url)}" alt="Foto de la prenda (image_url)" loading="lazy" referrerpolicy="no-referrer">`
    : `<div class="photo ${big ? 'photo-big' : ''}" role="img" aria-label="Sin foto"></div>`;
}

function currentHtml(run, file) {
  const row = file.current != null ? file.rows[file.current] : null;
  if (!row) return '';
  return `<section class="card card-pad current grow-3" aria-labelledby="cur-h" style="display:flex;flex-direction:column;gap:16px">
    <div style="display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px;align-items:baseline">
      <h2 id="cur-h">Fila en curso <span class="mono">[${row.index + 1}/${file.total}] ${esc(row.productId || '')}</span></h2>
      <span class="muted">empezó hace ${secs(now() - row.startedAt)}</span></div>
    <div style="display:flex;flex-wrap:wrap;gap:20px">
      <figure style="margin:0;flex:0 0 auto;display:flex;flex-direction:column;gap:6px;max-width:180px">${photoHtml(row.imageUrl)}
        <figcaption class="mono muted" style="font-size:11px;word-break:break-all">${esc(row.imageUrl)}</figcaption></figure>
      <div style="flex:1 1 260px;display:flex;flex-direction:column;gap:14px">
        <div><div class="label">Datos del CSV</div><dl class="kv">${businessKv(row.business)}</dl></div>
        <div><div class="label">Pasos de esta fila</div><ol class="steps">${rowSteps(row)}</ol></div>
      </div></div></section>`;
}

function lastHtml(run, file) {
  const row = file.lastDone != null ? file.rows[file.lastDone] : null;
  if (!row) return '';
  const r = row.result, en = r.enriched;
  const fields = en ? `
      <div class="field"><dt>title</dt><dd style="font-weight:600">${esc(en.title)}</dd></div>
      <div class="field"><dt>google_product_category</dt><dd>${esc(en.google_product_category ?? '—')}</dd></div>
      <div style="display:flex;flex-wrap:wrap;gap:24px">
        <div class="field"><dt>color (CSV)</dt><dd>${esc(row.business?.color ?? '—')}</dd></div>
        <div class="field"><dt>predicted_color</dt><dd>${esc(en.predicted_color ?? '—')}</dd></div></div>
      <div class="field"><dt>description</dt><dd style="color:var(--ink-2)">${esc(en.description)}</dd></div>` : '';
  return `<section class="card card-pad grow-2" aria-labelledby="last-h" style="display:flex;flex-direction:column;gap:12px">
    <div style="display:flex;justify-content:space-between;gap:8px;align-items:baseline"><h2 id="last-h">Última fila terminada</h2>
      <a href="${rowHref(run, run.selected, row.index)}">Ver detalle</a></div>
    <div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px"><span class="mono">[${row.index + 1}/${file.total}] ${esc(r.product_id)}</span>
      <span class="tag ${stageChip(r.stage)}">${esc(r.stage)}</span><span class="muted">${secs(row.timings?.total)} en total</span></div>
    ${r.reasons?.length ? `<div class="mono" style="font-size:13px">${esc(r.reasons.join('; '))}</div>` : ''}
    <dl style="margin:0">${fields}</dl></section>`;
}

function summaryHtml(run) {
  return `<section class="card" aria-labelledby="sum-h"><div class="card-head"><h2 id="sum-h">Resumen por archivo</h2></div>
    <div class="table-scroll"><table style="min-width:1000px"><thead><tr><th scope="col">Archivo</th><th scope="col">Salida</th>
      <th scope="col">Summary</th><th scope="col">Merchant Center</th><th scope="col">Results in</th></tr></thead><tbody>
      ${run.files.map((file, i) => {
        const [label, chip] = fileStatus(file);
        const note = fileNote(run, file);
        const merchant = file.verdict?.finished ? fmtCountsColon(file.verdict.finished) : '';
        const counts = fmtCountsColon(countBy(done(file), (r) => r.result.stage));
        const summary = file.read?.error || file.setup?.failed || file.summary?.crash ? note.text : counts;
        return `<tr><th scope="row" class="mono" style="font-weight:500">${esc(file.name)}</th><td><span class="chip ${chip}">${label}</span></td>
          <td class="mono" style="font-size:13px">${esc(summary)}</td><td class="mono" style="font-size:13px">${esc(merchant)}</td>
          <td>${file.results ? `<a class="mono" href="/api/runs/${encodeURIComponent(run.id)}/results/${i}">${esc(file.results)}</a>` : ''}</td></tr>`;
      }).join('')}</tbody></table></div>
    <div class="muted" style="padding:12px 24px;border-top:1px solid var(--line);background:#F8F9FB;font-size:13px">Salida 0: todo subido y nada rechazado · 1: alguna fila no se subió o Google la rechazó · 2: el archivo o la configuración frenó antes de procesar</div></section>`;
}

function runHeadHtml(run) {
  const env = run.files.map((f) => f.setup?.environment).find(Boolean);
  const runningIndex = run.files.findIndex((f) => f.status === 'running');
  let chip = '<span class="chip chip-run"><span class="dot"></span>Procesando</span>';
  if (run.finished) chip = run.interrupted ? '<span class="chip chip-warn">Interrumpido</span>' : '<span class="chip chip-idle">Terminado</span>';
  else if (run.interrupting) chip = '<span class="chip chip-warn">Interrumpiendo…</span>';
  const elapsed = run.startedAt ? clock((run.finishedAt ?? now()) - run.startedAt) : '00:00';
  const progress = run.finished ? `${run.files.filter((f) => f.status === 'finished').length} de ${run.files.length} procesados`
    : runningIndex >= 0 ? `procesando el ${runningIndex + 1} de ${run.files.length}` : '';
  return `<section class="card card-pad run-head">
    <div><div class="run-title"><h1>${esc(run.files.length === 1 ? run.files[0].name : `${run.files.length} archivos`)}</h1>${chip}</div>
      <div class="muted">${esc([`${run.files.length} archivo${run.files.length === 1 ? '' : 's'}`, progress, run.options.dry_run ? '--dry-run' : '', env ? `environment ${env}` : ''].filter(Boolean).join(' · '))}</div></div>
    <div style="display:flex;flex-wrap:wrap;align-items:center;gap:12px">
      <div class="elapsed"><div class="muted" style="font-size:12px">${run.finished ? 'Duró' : 'Transcurrido'}</div><div class="mono">${elapsed}</div></div>
      ${run.finished ? '<a class="btn btn-primary" href="#/">Cargar otro lote</a>'
        : `<div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px"><button type="button" class="btn" data-action="interrupt" ${run.interrupting ? 'disabled' : ''}>Interrumpir</button>
           <span class="muted" style="font-size:12px">Como Ctrl-C: guarda las filas ya procesadas</span></div>`}
    </div></section>`;
}

function runHtml(run) {
  if (!run.files.length) return '<p class="muted">Cargando…</p>';
  const file = run.files[run.selected] || run.files[0];
  return `${runHeadHtml(run)}
    ${run.finished ? summaryHtml(run) : ''}
    ${filesHtml(run)}
    <section class="card card-pad" aria-labelledby="path-h">
      <div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:8px;margin-bottom:16px">
        <h2 id="path-h">Camino de <span class="mono">${esc(file.name)}</span></h2>
        <span class="muted">${file.current != null ? `Fila ${file.current + 1} de ${file.total}` : ''}</span></div>
      ${pathHtml(run, file)}</section>
    <div class="row">${currentHtml(run, file)}${lastHtml(run, file)}</div>`;
}

// ── row detail ───────────────────────────────────────────────────────────────
function rowHref(run, fileIndex, rowIndex) { return `#/run/${encodeURIComponent(run.id)}/file/${fileIndex}/row/${rowIndex}`; }

function detailHtml(run, fileIndex, rowIndex) {
  const file = run.files[fileIndex];
  const row = file?.rows[rowIndex];
  if (!row) return '';
  const r = row.result, en = r?.enriched || row.enriched, product = r?.product;
  const status = file.verdict?.byId?.[r?.product_id];
  const generated = ['title', 'description', 'google_product_category'];
  const productRows = product ? Object.entries(product).map(([k, v]) => {
    const fromIa = generated.includes(k) || (k === 'color' && !row.business?.color && v);
    const src = k === 'id' ? '' : fromIa ? '<span class="src src-ia">Atribución</span>' : '<span class="src src-csv">CSV</span>';
    return `<tr><th scope="row" class="mono" style="font-weight:400;color:var(--ink-2)">${esc(k)}</th><td class="mono" style="word-break:break-word">${esc(v ?? '(vacío)')}</td><td>${src}</td></tr>`;
  }).join('') : '';
  const times = [['Bajar la foto y atribuirla', row.timings?.enrich], ['Subir a Merchant Center', row.timings?.upload], ['Total', row.timings?.total]]
    .filter(([, t]) => t != null).map(([l, t]) => stepRow(l, 'done', secs(t))).join('');
  return `<div class="modal-back" data-action="close"><div class="modal" role="dialog" aria-modal="true" aria-labelledby="row-h" data-stop="1">
    <div style="display:flex;justify-content:space-between;gap:12px;align-items:center">
      <a href="#/run/${encodeURIComponent(run.id)}" class="btn">Volver a ${esc(file.name)}</a></div>
    <section class="card card-pad" style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between">
      <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center"><h1 id="row-h" class="mono">[${row.index + 1}/${file.total}] ${esc(row.productId || r?.product_id || '')}</h1>
        ${r ? `<span class="tag ${stageChip(r.stage)}">stage: ${esc(r.stage)}</span>` : '<span class="chip chip-run">en curso</span>'}
        ${status ? `<span class="tag ${status.status === 'approved' ? 'chip-ok' : status.status === 'disapproved' ? 'chip-err' : 'chip-warn'}">merchant_status: ${esc(status.status)}</span>` : ''}</div>
      <span class="muted">${esc(file.name)} · fila ${row.index + 1}${row.timings?.total != null ? ` · ${secs(row.timings.total)} en total` : ''}</span></section>
    <div class="row">
      <section class="card card-pad grow-1" style="display:flex;flex-direction:column;gap:14px"><h2>Foto</h2>${photoHtml(row.imageUrl, true)}
        <div class="mono muted" style="font-size:12px;word-break:break-all">${esc(row.imageUrl)}</div>
        ${times ? `<div style="border-top:1px solid var(--line-soft);padding-top:14px"><div class="label">Tiempos</div><ol class="steps">${times}</ol></div>` : ''}
        <div style="border-top:1px solid var(--line-soft);padding-top:14px"><div class="label">Datos del CSV</div><dl class="kv">${businessKv(row.business)}</dl></div></section>
      <div class="grow-3" style="display:flex;flex-direction:column;gap:20px">
        ${r?.reasons?.length ? `<section class="card card-pad"><h2 style="margin-bottom:8px">reasons</h2><div class="box">${esc(r.reasons.join('\n'))}</div></section>` : ''}
        ${en ? `<section class="card card-pad"><h2>Lo que generó la atribución</h2>
          <p class="muted" style="margin:4px 0 14px">Salida de <span class="mono">enrich_product</span> · status <span class="mono">${esc(en.status)}</span></p>
          <dl class="kv" style="font-size:14px;gap:10px 16px">${Object.entries(en).filter(([k]) => k !== 'status').map(([k, v]) => `<dt>${esc(k)}</dt><dd style="font-family:Inter,sans-serif">${esc(v ?? '—')}</dd>`).join('')}</dl></section>` : ''}
        ${row.enrichError ? `<section class="card card-pad"><h2 style="margin-bottom:8px">Error en la atribución</h2><div class="box">${esc(row.enrichError)}</div></section>` : ''}
        ${product ? `<section class="card" style="overflow:hidden"><div class="card-head"><h2>Producto armado para Merchant Center</h2>
          <span class="muted"><span class="mono">validation</span>: ${r.validation?.valid ? 'valid' : esc((r.validation?.reasons || []).join('; '))}${r.upload ? ` · <span class="mono">upload</span>: ${r.upload.success ? 'success' : esc(r.upload.error)}` : ''}</span></div>
          <div class="table-scroll"><table style="min-width:520px"><thead><tr><th scope="col">Campo</th><th scope="col">Valor</th><th scope="col">De dónde sale</th></tr></thead><tbody>${productRows}</tbody></table></div></section>` : ''}
        ${status ? `<section class="card card-pad"><h2 style="margin-bottom:10px">Veredicto de Google</h2>
          <span class="tag ${status.status === 'approved' ? 'chip-ok' : status.status === 'disapproved' ? 'chip-err' : 'chip-warn'}">${esc(status.status)}</span>
          ${status.issues?.length ? `<div class="label" style="margin-top:12px">issues</div><div class="box">${esc(status.issues.join('\n'))}</div>` : ''}</section>` : ''}
      </div></div></div></div>`;
}

// ── run page: snapshot + stream ──────────────────────────────────────────────
let active = null;   // { run, source, timer }

function stopActive() {
  if (!active) return;
  active.source?.close();
  clearInterval(active.timer);
  active = null;
}

// The row detail is redrawn only when its content changes, keeping its scroll:
// the 1-second tick that updates the timers must not send it back to the top.
let modalHtml = '';
function showModal(html) {
  if (html === modalHtml) return;
  const back = modalRoot.querySelector('.modal-back');
  const top = back ? back.scrollTop : 0;
  modalHtml = html;
  modalRoot.innerHTML = html;
  const next = modalRoot.querySelector('.modal-back');
  if (next && back) next.scrollTop = top;
}

let renderQueued = false;
function render() {
  if (renderQueued) return;
  renderQueued = true;
  requestAnimationFrame(() => {
    renderQueued = false;
    if (!active) return;
    app.innerHTML = runHtml(active.run);
    const route = parseRoute();
    showModal(route.row != null ? detailHtml(active.run, route.file, route.row) : '');
  });
}

async function openRun(id) {
  if (active?.run.id === id) { render(); return; }
  stopActive();
  const run = emptyRun(id);
  active = { run, source: null, timer: setInterval(render, 1000) };
  app.innerHTML = '<p class="muted">Cargando…</p>';
  const response = await fetch(`/api/runs/${encodeURIComponent(id)}/events?after=0`);
  if (!response.ok) { stopActive(); app.innerHTML = notFoundHtml(); return; }
  const body = await response.json();
  for (const e of body.events) apply(run, e);
  render();
  if (body.finished) return;
  const source = new EventSource(`/api/runs/${encodeURIComponent(id)}/stream?after=${run.lastSeq}`);
  active.source = source;
  source.onmessage = (msg) => { apply(run, JSON.parse(msg.data)); render(); };
  source.addEventListener('end', () => { source.close(); render(); });
  source.onerror = async () => {
    // The stream dropped: catch up with the snapshot; EventSource reconnects by itself.
    try {
      const r = await fetch(`/api/runs/${encodeURIComponent(id)}/events?after=${run.lastSeq}`);
      const b = await r.json();
      for (const e of b.events) apply(run, e);
      if (b.finished) source.close();
      render();
    } catch (_) { /* offline: try again on the next error */ }
  };
}

function notFoundHtml() {
  return `<section class="card card-pad"><h1>No encontramos esa ejecución</h1>
    <p class="muted">El servidor no la tiene en memoria (se reinició o el enlace es de otra máquina).</p>
    <a class="btn btn-primary" href="#/">Cargar otro lote</a></section>`;
}

// ── new run ──────────────────────────────────────────────────────────────────
const pick = { mode: null, files: [], folderName: '' };

function csvOfPick() {
  if (pick.mode === 'file') return pick.files.map((f) => ({ name: f.name, size: f.size, file: f }));
  return pick.files.filter((f) => {
    const parts = (f.webkitRelativePath || f.name).split('/');
    return parts.length === 2 && parts[1].toLowerCase().endsWith('.csv');
  }).map((f) => ({ name: f.name, size: f.size, file: f })).sort((a, b) => (a.name < b.name ? -1 : 1));
}

const kb = (n) => (n < 1024 ? `${n} B` : `${Math.round(n / 1024)} KB`);

async function newRunView() {
  stopActive();
  showModal('');
  let current = null;
  try { current = await (await fetch('/api/runs/current')).json(); } catch (_) { /* server down */ }
  const csv = csvOfPick();
  const busy = current?.running;
  app.innerHTML = `
    <div><h1 style="font-size:28px">Nuevo lote</h1>
      <p class="intro">Elegí un CSV o una carpeta. Cada CSV se procesa igual que en la terminal con <span class="mono" style="color:var(--ink)">python scripts/publish_from_csv.py &lt;archivo&gt;</span>. Si es una carpeta, el script corre una vez por cada CSV.</p></div>
    ${busy ? `<div class="info-box">Hay una ejecución en curso. <a href="#/run/${encodeURIComponent(current.run_id)}">Ver la ejecución</a></div>`
      : current?.run_id ? `<div class="muted">Última ejecución: <a href="#/run/${encodeURIComponent(current.run_id)}">${esc(current.run_id)}</a></div>` : ''}
    <div class="row">
      <section class="grow-3" style="display:flex;flex-direction:column;gap:20px">
        <div class="card card-pad">
          <div class="drop" id="drop">
            <span style="color:var(--accent)">${svg('cloud', 40)}</span>
            <div class="drop-title">Arrastrá un CSV o una carpeta</div>
            <div class="muted">CSV local con una prenda por fila</div>
            <div style="display:flex;flex-wrap:wrap;justify-content:center;gap:10px">
              <label class="btn">${svg('doc', 18)}Elegir archivo CSV<input id="pick-file" type="file" accept=".csv,text/csv" class="sr-only"></label>
              <label class="btn">${svg('folder', 18)}Elegir carpeta<input id="pick-folder" type="file" webkitdirectory multiple class="sr-only"></label>
            </div></div>
          <p class="cols-note">El CSV necesita una columna de foto (<span class="mono">image_url</span> o <span class="mono">url</span>) y las columnas <span class="mono">brand, price, link, size, gender</span>. Puede traer además <span class="mono">id, color, material, pattern, gtin, availability, condition, age_group</span>.</p>
        </div>
        ${pick.mode ? `<div class="card" style="overflow:hidden">
          <div class="card-head"><h2>${esc(pick.mode === 'folder' ? pick.folderName : 'Archivo')}</h2>
            <span class="muted">${csv.length} archivo${csv.length === 1 ? '' : 's'} CSV${pick.mode === 'folder' ? ' · se procesan de a uno, en orden alfabético' : ''}</span></div>
          ${csv.length ? `<ol class="file-list">${csv.map((f) => `<li><span class="mono">${esc(f.name)}</span><span class="muted">${kb(f.size)}</span></li>`).join('')}</ol>`
            : '<div class="card-pad"><div class="error-box">La carpeta no tiene ningún archivo .csv en su primer nivel.</div></div>'}
        </div>` : ''}
      </section>
      <aside class="grow-1" style="display:flex;flex-direction:column;gap:20px">
        <form class="card card-pad options" id="opts">
          <h2>Opciones</h2>
          <div class="check opt"><input type="checkbox" id="dry"><label for="dry" style="margin:0">No subir a Merchant Center <span class="flag">--dry-run</span>
            <span class="muted" style="display:block;font-weight:400">Arma y valida cada producto sin subir nada. No hacen falta credenciales.</span></label></div>
          <div class="opt"><label for="limit">Procesar solo las primeras N filas <span class="flag">--limit</span></label><input id="limit" type="number" min="1" placeholder="Todas" style="max-width:160px"></div>
          <div class="opt"><label for="wait">Esperar el veredicto de Google <span class="flag">--wait</span></label>
            <div style="display:flex;align-items:center;gap:8px"><input id="wait" type="number" min="0" value="300" style="width:110px"><span class="muted">segundos · 0 = no esperar</span></div></div>
          <div class="opt"><label for="out">Archivo de resultados <span class="flag">--out</span></label>
            <input id="out" type="text" placeholder="&lt;nombre&gt;_results.csv" class="mono" style="width:100%" ${csv.length > 1 ? 'disabled' : ''}>
            <span class="muted" style="font-size:13px">${csv.length > 1 ? 'Con varios CSV cada uno escribe el suyo, al lado del archivo de entrada' : 'Por defecto, al lado del archivo de entrada'}</span></div>
          <div id="form-error"></div>
          <button type="submit" class="btn btn-primary btn-big" ${!csv.length || busy ? 'disabled' : ''}>Iniciar${csv.length ? ` · ${csv.length} archivo${csv.length === 1 ? '' : 's'}` : ''}</button>
        </form>
      </aside></div>`;

  document.getElementById('pick-file').addEventListener('change', (ev) => {
    pick.mode = 'file'; pick.files = [...ev.target.files].slice(0, 1); pick.folderName = ''; newRunView();
  });
  document.getElementById('pick-folder').addEventListener('change', (ev) => {
    const files = [...ev.target.files];
    pick.mode = 'folder'; pick.files = files;
    pick.folderName = files[0]?.webkitRelativePath?.split('/')[0] || 'carpeta';
    newRunView();
  });
  const drop = document.getElementById('drop');
  drop.addEventListener('dragover', (ev) => { ev.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', async (ev) => {
    ev.preventDefault(); drop.classList.remove('over');
    const item = ev.dataTransfer.items?.[0]?.webkitGetAsEntry?.();
    if (item?.isDirectory) {
      const entries = await new Promise((ok) => item.createReader().readEntries(ok));
      const files = await Promise.all(entries.filter((e) => e.isFile).map((e) => new Promise((ok) => e.file((f) => {
        Object.defineProperty(f, 'webkitRelativePath', { value: `${item.name}/${f.name}` }); ok(f);
      }))));
      pick.mode = 'folder'; pick.files = files; pick.folderName = item.name;
    } else if (ev.dataTransfer.files.length) {
      pick.mode = 'file'; pick.files = [ev.dataTransfer.files[0]]; pick.folderName = '';
    }
    newRunView();
  });
  document.getElementById('opts').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const form = new FormData();
    for (const f of csv) form.append('files', f.file, pick.mode === 'folder' ? `${pick.folderName}/${f.name}` : f.name);
    form.append('mode', pick.mode);
    form.append('folder_name', pick.folderName);
    form.append('dry_run', document.getElementById('dry').checked ? 'true' : 'false');
    const limit = document.getElementById('limit').value.trim();
    if (limit) form.append('limit', limit);
    form.append('wait', document.getElementById('wait').value.trim() || '300');
    const out = document.getElementById('out').value.trim();
    if (out) form.append('out', out);
    const response = await fetch('/api/runs', { method: 'POST', body: form });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      document.getElementById('form-error').innerHTML = `<div class="error-box">${esc(body.detail || 'No se pudo iniciar.')}</div>`;
      return;
    }
    pick.mode = null; pick.files = [];
    location.hash = `#/run/${encodeURIComponent(body.run_id)}`;
  });
}

// ── routing and clicks ───────────────────────────────────────────────────────
function parseRoute() {
  const m = /^#\/run\/([^/]+)(?:\/file\/(\d+)\/row\/(\d+))?/.exec(location.hash);
  if (!m) return { view: 'new' };
  return { view: 'run', id: decodeURIComponent(m[1]), file: m[2] != null ? +m[2] : null, row: m[3] != null ? +m[3] : null };
}

function route() {
  const r = parseRoute();
  if (r.view === 'run') openRun(r.id); else newRunView();
}

app.addEventListener('click', async (ev) => {
  const target = ev.target.closest('[data-action]');
  if (!target || !active) return;
  if (target.dataset.action === 'select') {
    active.run.selected = +target.dataset.file; active.run.follow = false; render();
  } else if (target.dataset.action === 'interrupt') {
    active.run.interrupting = true; render();
    await fetch(`/api/runs/${encodeURIComponent(active.run.id)}/interrupt`, { method: 'POST' });
  }
});

modalRoot.addEventListener('click', (ev) => {
  if (ev.target.dataset.action === 'close' && active) location.hash = `#/run/${encodeURIComponent(active.run.id)}`;
});
document.addEventListener('keydown', (ev) => {
  if (ev.key === 'Escape' && modalRoot.innerHTML && active) location.hash = `#/run/${encodeURIComponent(active.run.id)}`;
});

window.addEventListener('hashchange', route);
route();
