# DQ Atlas - Engine

A **config-driven data quality engine** built around **ports-and-adapters (hexagonal) architecture**.

The engine separates **what should be checked** from **how checks are executed**, making the framework easy to extend with new check types, backends, and configuration sources without coupling the orchestration layer to any particular implementation.

The current production adapter targets **Snowflake**, while a deterministic mock backend is included for running the complete pipeline without a Snowflake connection. It can be extended to move entirely from table-based config storage to a file based one, given that the contract is retained in the file parser.

---

## Architecture

```text
main.py
  CLI entry point - wires adapters into the driver

core/
  models.py
    CheckInstance, CheckResult, RunSummary
    Uniform contracts used throughout the engine

  ports.py
    Protocols:
      SessionPort
      ResultLoggerPort
      RecordFetcherPort
      ConfigLoaderPort

  registry.py
    CHECK_TYPE → check function registry
    Config row → CheckInstance resolver

  driver.py
    Orchestrator:
      resolve → dispatch → execute → detail → log → summarize

  sql_render.py
    Safe SQL identifier and literal rendering

  evaluation.py
    Shared pass/fail threshold evaluation

  predicates.py
    Shared WHERE-clause builders
    Kept consistent between aggregate and detail queries

  exec_helpers.py
    Shared execution boilerplate for the common
    "one aggregate query" check pattern

  errors.py
    CheckExecutionError
    Carries rendered SQL through to the driver's error handler

checks/
  One implementation per check type:

    NULL
    DUPLICATE
    RANGE
    TYPE
    DATA_TYPE
    CHECKLIST
    OUTLIER_ZSCORE
    OUTLIER_IQR
    REF
    RECON
    CUSTOM

  Each check registers itself via:
    @register("TYPE")

templates/
  default_templates.py
    SQL templates for each check type:
      aggregate query
      optional row-level detail query

adapters/
  mock_session.py
    Demo backend - no Snowflake required

  snowflake_session.py
    Production Snowflake backend
    One session per worker thread

  config_loader.py
    Loads DQ_CHECK_CONFIG rows
    Supports Snowflake and the in-memory demo configuration

  result_logger.py
    Batched writer for:
      DQ_RESULTS
      DQ_RUN_LOG

    Supports Snowflake inserts and CSV output

  record_fetcher.py
    Fetches sample failed row keys
    Only invoked when a check actually fails

```

---

## How the engine works

At a high level, a run follows this pipeline:

```text
Config
  │
  ▼
Resolve config rows into CheckInstances
  │
  ▼
Dispatch each instance through CHECK_REGISTRY
  │
  ▼
Render SQL and execute checks
  │
  ├── SUCCESS → evaluate PASS / FAIL
  │
  └── ERROR   → capture error without stopping other checks
  │
  ▼
Fetch detail rows only for failed checks
  │
  ▼
Batch-write DQ_RESULTS
  │
  ▼
Build and write DQ_RUN_LOG
  │
  ▼
Return RunSummary
```

Checks can execute concurrently using a bounded `ThreadPoolExecutor`. Each worker uses its own Snowflake session, and failures are isolated per check.

---

## Design decisions

### Uniform check contract

Every check ultimately produces:

```text
total_rows
failed_rows
```

The shared evaluation layer derives the failure percentage and PASS/FAIL result from these values and the configured threshold.

This keeps logging, evaluation, and orchestration independent of individual check implementations.

`RECON` and `CUSTOM` are the exceptions that prove the rule:

* `RECON` compares two independent queries, so it does not naturally produce row-level totals. It is represented as a single logical result (`total_rows=1`, with `failed_rows` indicating whether the tolerance was exceeded).
* `CUSTOM` requires the administrator-authored SQL to return `TOTAL_ROWS` and `FAILED_ROWS`.

See the individual check implementations/docstrings for the details of these contracts.

---

### One config row → many checks

A single `DQ_CHECK_CONFIG` row can activate multiple check families for the same table/column.

For example:

```text
NULL_CHECK_ACTIVE = TRUE
OUTLIER_SENSITIVITY = 3
```

can resolve into two independent `CheckInstance` objects:

```text
NULL check
OUTLIER check
```

The expansion happens in:

```text
core/registry.py::resolve_check_instances
```

The driver does not need to know which configuration columns correspond to which check types.

---

### Error isolation

Check implementations **raise exceptions** when execution fails.

Only the driver is responsible for catching those exceptions and converting them into:

```text
STATUS = ERROR
PASS_FAIL_FLAG = NULL
```

This gives every check type the same error-handling behavior.

A malformed check therefore produces an error result without preventing unrelated checks in the same batch from completing.

---

### Conditional detail fetching

The initial aggregate query answers the important question:

> Did this check pass?

Fetching the actual failing row keys requires additional warehouse work, so the engine does not do it unless necessary.

`RecordFetcher` runs only when:

1. The check executed successfully.
2. The check actually failed.
3. The check has a meaningful row-level detail query.
4. `ROW_IDENTIFIER_COLUMNS` are configured where required.

Passing checks therefore pay for only their aggregate query.

---

### Concurrency

Checks are primarily **I/O-bound**: most execution time is spent waiting for the warehouse rather than consuming Python CPU.

The engine therefore uses:

```python
ThreadPoolExecutor
```

with a bounded `max_workers`.

Each worker gets its own Snowflake session rather than sharing a connection across threads.

Individual futures are also isolated so that an unexpected exception in one check does not discard results from the rest of the batch.

For debugging, concurrency can be disabled with:

```bash
--sequential
```

---

### Shadow mode

`CHECK_STATUS` supports four lifecycle states:

```text
DRAFT → SHADOW → ACTIVE → RETIRED
```

Both `SHADOW` and `ACTIVE` checks are executed and logged by the engine.

The intended distinction is for the downstream alerting layer:

* `SHADOW` - observe results without alerting
* `ACTIVE` - eligible for alerting
* `DRAFT` - not executed
* `RETIRED` - no longer executed

Alerting itself is intentionally outside this engine.

---

### Ports & adapters

The core driver depends on interfaces defined in `core/ports.py`, rather than directly depending on Snowflake or any other backend.

The main ports are:

```text
SessionPort
ConfigLoaderPort
ResultLoggerPort
RecordFetcherPort
```

This means:

* Snowflake can be replaced by the mock backend.
* A different warehouse can be introduced through a new session adapter.
* Configuration can come from another source.
* Result logging can be redirected elsewhere.
* The driver does not need to change when a new check type is added.

The goal is to keep infrastructure concerns at the edges and the orchestration logic in the core.

---

## Running the demo

The complete pipeline can be run without Snowflake.

```bash
cd dq_framework

python main.py --demo --run-all

python main.py --demo --table ORDERS

python main.py --demo --check-id 203

python main.py --demo --run-all --sequential
# disable concurrency
```

Demo mode uses `MockSession`.

The mock backend produces **deterministic-per-SQL pseudo-random results**, allowing the engine's behavior to be exercised without requiring a live warehouse.

It validates the pipeline end to end, including:

* config loading
* check resolution
* registry dispatch
* SQL rendering
* concurrency
* error isolation
* conditional detail fetching
* result evaluation
* batched logging
* run summarization

It does **not** validate the quality of real data.

Demo results are written to:

```text
./dq_output/DQ_RESULTS.csv
./dq_output/DQ_RUN_LOG.csv
```

---

## Running the tests

```bash
pip install pytest
python -m pytest
```

No Snowflake connection is required. The suite covers:

* `core/` in isolation -- SQL rendering/escaping, threshold evaluation,
  range predicates, the aggregate-check helper's error paths.
* `core/registry.py` -- every check-family resolution branch, multi-check
  rows, and required-field validation.
* `core/driver.py` -- the full orchestration pipeline against fake ports
  (`tests/conftest.py`), including error isolation for both a malformed
  config row and a failing check execution, detail-fetch gating, and
  concurrent vs. sequential equivalence.
* Every module in `checks/`, driven directly against a scriptable fake
  session (`tests/conftest.FakeSession`).
* `adapters/config_loader.py`, `adapters/record_fetcher.py`,
  `adapters/result_logger.py`, `adapters/session_registry.py`.
* `adapters/sqlite_session.py` end to end against a real (temporary)
  SQLite database -- config loading, execution, and result logging all
  actually hit disk, not fakes.
* `adapters/snowflake_session.py`'s private-key conversion (skipped
  automatically if `cryptography` isn't installed) and env-var wiring.
  `snowflake.connector` itself is never imported by the test suite --
  consistent with it being a lazy, optional dependency.
* `main.py` as a subprocess, running the real CLI (`--demo --run-all`,
  `--sequential`, `--table`, and the no-scope-flag error path) and
  checking the actual CSV files it writes.

---

## Running against Snowflake

### 1. Create the metadata and results tables

Create:

```text
DQ_CHECK_CONFIG
DQ_RESULTS
DQ_RUN_LOG
```

The column names must match the fields expected by `core/registry.py` and `adapters/result_logger.py`.

`demo_config_data.py` contains the complete set of configuration fields exercised by the resolver, including:

```text
NULL_CHECK_ACTIVE

LOWER_BOUND
UPPER_BOUND

REGEX_PATTERN

ALLOWED_VALUES

OUTLIER_SENSITIVITY

REFERENCE_TABLE
REFERENCE_COLUMN

RECON_SOURCE_SQL
RECON_TARGET_SQL

CUSTOM_SQL

ROW_IDENTIFIER_COLUMNS

CHECK_STATUS
CRITICALITY
SCHEDULE_GROUP
```

Each check family also has its corresponding:

```text
*_THRESHOLD
*_THRESHOLD_TYPE
```

fields.

---

### 2. Install the Snowflake connector

```bash
pip install snowflake-connector-python
```

---

### 3. Configure Snowflake credentials

Set the required environment variables:

```bash
export SNOWFLAKE_ACCOUNT=...
export SNOWFLAKE_USER=...
export SNOWFLAKE_PASSWORD=...
export SNOWFLAKE_ROLE=...
export SNOWFLAKE_WAREHOUSE=...
export SNOWFLAKE_DATABASE=...
```

For key-pair authentication, use:

```bash
export SNOWFLAKE_PRIVATE_KEY=...        # PEM contents, e.g. $(cat rsa_key.p8)
export SNOWFLAKE_PRIVATE_KEY_PASSPHRASE=...   # optional, if the key is encrypted
```

instead of `SNOWFLAKE_PASSWORD`. This requires the `cryptography` package
(`pip install cryptography`, or `pip install -r requirements.txt`) --
the adapter converts the PEM into the DER/PKCS8 bytes the Snowflake
connector expects.

---

### 4. Run the engine

For example:

```bash
python main.py --run-all \
  --config-table DQ_META.PUBLIC.DQ_CHECK_CONFIG \
  --results-table DQ_META.PUBLIC.DQ_RESULTS \
  --run-log-table DQ_META.PUBLIC.DQ_RUN_LOG
```

The CLI can also target narrower scopes using options such as:

```text
--check-id
--table
--schedule-group
```

See `main.py --help` for the available CLI options.

---

## Adding a new check type

Adding a check should not require changes to `core/driver.py`.

The general process is:

### 1. Add the configuration resolution

Update:

```text
core/registry.py::resolve_check_instances
```

Add the branch that detects the new configuration fields and produces a `CheckInstance`.

### 2. Add the SQL templates

Update:

```text
templates/default_templates.py
```

Add the SQL required for:

* the aggregate/pass-fail query
* optionally, a row-level detail query

### 3. Implement the check

Add a new module under:

```text
checks/
```

For a standard aggregate check, use:

```text
execute_aggregate_check
```

For checks with fundamentally different execution semantics, custom logic can be used instead, as demonstrated by:

```text
checks/recon_check.py
```

### 4. Register the check

Register the implementation using:

```python
@register("YOUR_TYPE")
```

and import it from:

```text
checks/__init__.py
```

That's it.

`core/driver.py` does not need to know that the new check exists. The registry and common contracts keep the new behavior contained.

---

## Configuration sources

The current `config_loader.py` implementation supports loading configuration from Snowflake, with the demo using an in-memory configuration list.

The loader is intentionally isolated behind `ConfigLoaderPort`.

This means another implementation can replace it without changing the driver-for example, a loader that reads configuration from:

```text
YAML
CSV
JSON
```

or another metadata/configuration service.

The engine therefore does not fundamentally require configuration to live in Snowflake; Snowflake is simply the current production adapter.

---

## What's intentionally not included

This first version deliberately keeps the engine focused on **executing and recording data quality checks**.

### Config versioning / audit history

There is no separate configuration history table in the engine.

The current design relies on:

* **RBAC** for controlling who can modify configuration when configuration is stored in Snowflake
* Snowflake's native `QUERY_HISTORY` / `ACCESS_HISTORY` capabilities when historical investigation is required

The framework therefore avoids maintaining a parallel audit mechanism for information the platform already records.

Configuration itself is deliberately decoupled from its storage mechanism. `ConfigLoaderPort` defines the contract the engine consumes, so the configuration can move from the current table-based implementation to a file-based source such as YAML, CSV, or JSON without changing the core engine, as long as the parser produces the same configuration contract expected by the resolver.

If configuration moves to a file-based source, **versioning and auditability can then be handled by the system managing that file** (for example, source control), rather than by adding configuration-history concerns to the DQ engine itself.


### Orchestration

There is no embedded scheduler.

Scheduling is expected to be handled by the surrounding platform, such as:

```text
Snowflake Tasks
Airflow
```

or another existing orchestration system.

### Alerting

There is currently no notifier implementation.

A future `NotifierPort` could support destinations such as Slack, email, PagerDuty, etc.

The engine already records the information required by such a layer, including:

```text
PASS / FAIL
CRITICALITY
CHECK_STATUS
```

### Dashboards

The framework does not own a presentation layer.

`DQ_RESULTS` and `DQ_RUN_LOG` are designed to be consumed by existing analytics/BI tools such as Snowsight, Sigma, or another platform already used by the team.

### Freshness checks

Freshness is not currently implemented.

It follows the same extension pattern as other check types:

```text
registry branch
      +
SQL template
      +
checks/<type>_check.py
```

It was left out because no sample configuration currently exercises it.

### Live DQ template table

The original design envisioned a `DQ_TEMPLATES` Snowflake table containing editable SQL templates.

The current implementation keeps templates in:

```text
templates/default_templates.py
```

Promoting them to a live metadata table can be done behind the existing adapter/port boundary without changing the core orchestration model.

### Retry logic

Transient network retry behavior is not currently implemented.

This is intended to remain an adapter-level concern rather than being embedded in individual check implementations.

### Per-schedule warehouse routing

The current implementation does not route different schedule groups to different warehouses.

This can be introduced inside the `SessionPort` / Snowflake adapter without requiring changes to the driver or check implementations.

---

## Project philosophy

The engine is intentionally built around a few simple rules:

* **Explicit beats implicit.**
* **Simple beats clever.**
* **The schema should document itself.**
* **Special cases should remain special when they genuinely have different semantics.**
* **Keep the common path cheap.**
* **Separate what a check is from how it runs.**
* **Don't rebuild capabilities the platform already provides.**

The framework is not intended to be the universally correct way to build data quality.

It is an opinionated implementation of a particular set of trade-offs: **explicit configuration, isolated execution, a uniform result contract, warehouse abstraction, and a small core that can grow without becoming the system it was originally built to replace.**
