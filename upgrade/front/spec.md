# Milestone 5 — Web monitor for the CSV pipeline

A web front that starts the Milestone 4 pipeline from the browser and shows it
running, row by row. It replaces typing `scripts/publish_from_csv.py` in a terminal,
not the pipeline: every decision (what is read, validated, uploaded, waited for and
written) stays in the existing code, and the front only shows what that code does
and produces. The visual design is the "Deep Tagger · Monitor de lotes" canvas
(screens 1 to 5).

Three rules hold for every requirement below:

- **Only additions.** No existing file or folder of the repo is modified:
  not `positioner/`, not `scripts/`, not `deep-tagger-api/`, not `deep-tagger-ui/`,
  not the other files of `upgrade/`. The monitor is one more layer on top.
- **Everything new lives in `upgrade/front/`.** The monitor calls the pipeline's
  functions and observes them through the parameters they already accept
  (`enrich`, `client`, `on_result`, `sleep`).
- **Nothing invented.** Every value shown on screen comes from the pipeline's
  output (`read_rows`, `connect`, `PipelineResult`, `ProductStatus`,
  `write_results`) or from timing measured by the observation layer.

Layout of the new folder:

```
upgrade/front/
├── spec.md        this file
├── tasks.md       task list
├── api/           backend: observation layer, runner, events, FastAPI endpoints
├── ui/            web app: the five screens of the design
├── tests/         tests of the scenarios below
└── runs/          one folder per run: the uploaded CSV and their results (not committed)
```

Because the spec is outside `upgrade/specs/`, `scripts/spec_report.py` does not
list it. Its tests run on their own with
`python -m unittest discover -s upgrade/front/tests`.

## ADDED Requirements

### Requirement: CSV or folder input
The monitor SHALL take one CSV file or a folder, and SHALL process each CSV as a
separate run of the script.

#### Scenario: One CSV
- **WHEN** the user chooses one CSV
- **THEN** the monitor SHALL save it in a new run folder on the server and process
  it as `publish_from_csv.py <file>` would

#### Scenario: Folder with several CSV
- **WHEN** the user chooses a folder
- **THEN** the monitor SHALL take every `.csv` file of its first level, in
  alphabetical order, ignore any other file, and process them one at a time,
  each as its own run of the script

#### Scenario: Folder without CSV
- **IF** the chosen folder has no `.csv` file
- **THEN** the monitor SHALL not start and SHALL say that no CSV was found

### Requirement: Same options as the script
The monitor SHALL offer exactly the options of `publish_from_csv.py`: `--dry-run`,
`--limit N`, `--wait SECONDS` (default 300, 0 means not waiting) and `--out`, with
the same defaults, and SHALL apply them to every CSV of the run.

#### Scenario: Default options
- **WHEN** the user starts without changing any option
- **THEN** the run SHALL not be a dry run, SHALL process every row, SHALL wait up
  to 300 seconds for the verdict and SHALL write `<input>_results.csv` next to
  each input

### Requirement: Same flow as the script
For each CSV the monitor SHALL run the same steps, in the same order, as `main()` of
`publish_from_csv.py`, calling the existing functions: `read_rows`, `connect` (only
when not a dry run), `run_batch`, `write_results` (also when the run is
interrupted), `wait_for_statuses` (only when something was uploaded and the wait is
above 0) and `write_results` again with the statuses.

#### Scenario: Bad CSV
- **IF** `read_rows` raises
- **THEN** that CSV SHALL end with exit code 2 and the exact error message, no row
  SHALL be processed, and the monitor SHALL go on with the next CSV

#### Scenario: Missing key or credentials
- **IF** `connect` raises `SetupError`
- **THEN** that CSV SHALL end with exit code 2 and the exact message, before
  loading the models

#### Scenario: Dry run
- **WHEN** the run is a dry run
- **THEN** the monitor SHALL skip `connect` and the verdict, and every valid row
  SHALL end in `dry_run`

#### Scenario: Verdict not waited
- **WHEN** something was uploaded and the wait is 0
- **THEN** the monitor SHALL show "Not waiting for Google's verdict. It shows up in
  Merchant Center → Products."

#### Scenario: Statuses could not be read
- **IF** `wait_for_statuses` raises
- **THEN** the monitor SHALL show "Could not read the statuses: <error>. They show
  up in Merchant Center → Products." and keep the results already written

#### Scenario: Exit code
- **WHEN** a CSV finishes
- **THEN** its exit code SHALL be 0 if every row reached `uploaded` (or `dry_run`
  in a dry run) and Google disapproved none of them, and 1 otherwise, as in the
  script

#### Scenario: Same output as the terminal
- **WHEN** the same CSV runs through the script and through the monitor with the
  same options and the same simulated models and client
- **THEN** both SHALL produce the same results file and the same lines of output

### Requirement: Observation without changing behavior
The monitor SHALL observe a run only by wrapping what the pipeline already accepts
as a parameter: the `enrich` function, the Merchant `client` (`upload_feed`,
`get_product_statuses`), the `on_result` callback and the `sleep` of
`wait_for_statuses`. Each wrapper SHALL call the original with the same arguments
and return its result unchanged.

#### Scenario: Results do not depend on the observer
- **WHEN** the same rows run with and without the wrappers
- **THEN** every `PipelineResult` and every status SHALL be equal

#### Scenario: Observer failure does not stop the pipeline
- **IF** sending an event fails
- **THEN** the pipeline SHALL go on and the result SHALL be the same

### Requirement: Progress events
The monitor SHALL emit one event per observable step, numbered with a sequence
that grows by one per run, so that a screen can follow the run and recover it after
a reload.

| Event | When | Data |
|---|---|---|
| `run.started` | start | files, options |
| `file.started` | before `read_rows` | file name |
| `file.read` | after `read_rows` | number of rows, or the error and exit code 2 |
| `setup.connected` | after `connect` | LLM provider, Merchant account, environment |
| `setup.failed` | `SetupError` | message, exit code 2 |
| `models.loading` / `models.loaded` | around the first import of the models | elapsed time |
| `row.started` | when a row begins | index, total, product ID, photo URL, brand fields of the CSV |
| `row.enrich.started` / `row.enrich.finished` | around `enrich` | elapsed time, the `EnrichedProduct` |
| `row.upload.started` / `row.upload.finished` | around `upload_feed` | elapsed time, `UploadResult` |
| `row.finished` | `on_result` | the `PipelineResult` (stage, reasons, enriched, product, validation, upload) and the time of each step |
| `verdict.round` | each `get_product_statuses` call | round, statuses read, products still pending |
| `verdict.waiting` | each `sleep` | seconds until the next round |
| `results.written` | after `write_results` | path of the results file |
| `file.finished` | end of a CSV | the counts the script prints in its summary, Merchant statuses, exit code |
| `run.finished` | end | one line per file |
| `log` | each line the script would print | the exact line |

#### Scenario: Row started without a dedicated hook
- **WHEN** row *i* finishes
- **THEN** the monitor SHALL emit `row.started` for row *i+1*; the first row starts
  when `run_batch` is called

#### Scenario: Row cut at the brand check
- **WHEN** `row.finished` arrives for a row without `row.enrich.started`
- **THEN** the screen SHALL show that the row ended at "Revisar los datos de la
  marca"

#### Scenario: Reload in the middle of a run
- **WHEN** the screen is reloaded
- **THEN** it SHALL ask for the snapshot, show the same state, and follow the
  events after the snapshot's sequence number, without counting any row twice

### Requirement: Interruption
The monitor SHALL let the user interrupt a run, as Ctrl-C does in the terminal: the
rows already finished SHALL be kept and written to the results file.

#### Scenario: Interrupt during a row
- **WHEN** the user interrupts while a row is running
- **THEN** the monitor SHALL stop at the next observation point, write the results
  of the finished rows and not start the following CSV files

### Requirement: Server-side secrets
The monitor SHALL read the Merchant credentials and the LLM key only from the
server's environment variables, as the script does, and SHALL never receive them
from the browser or send them to it.

#### Scenario: Screen without secrets
- **WHEN** the screen shows the setup step
- **THEN** it SHALL show the provider name, the account and the environment that
  `connect` prints, and nothing else about the credentials

### Requirement: Downloads
The monitor SHALL let the user download each `<input>_results.csv` once written.

#### Scenario: Results file
- **WHEN** a CSV finishes
- **THEN** its results file SHALL be downloadable with the columns of
  `RESULT_COLUMNS`
