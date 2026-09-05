# DQ Framework - Engine

A config-driven data quality framework built around a ports-and-adapters
architecture, matching the design worked through in the conversation this
was built from.

## Architecture

```
main.py            CLI entry point - wires adapters into the driver
core/
  models.py         CheckInstance, CheckResult, RunSummary - the uniform contract
  ports.py          Protocols: SessionPort, ResultLoggerPort, RecordFetcherPort, ConfigLoaderPort
  registry.py       CHECK_TYPE -> function registry + config-row -> CheckInstance resolver
  driver.py         Orchestrator: resolve -> dispatch -> execute -> detail -> log -> summarize
  sql_render.py     Safe identifier/literal rendering
  evaluation.py     Shared pass/fail threshold logic
  predicates.py     Shared WHERE-clause builders (kept in sync between aggregate + detail queries)
  exec_helpers.py   Shared boilerplate for the common "one aggregate query" check shape
  errors.py         CheckExecutionError - carries rendered SQL through to the driver's error handler
checks/             One file per check type (NULL, DUPLICATE, RANGE, TYPE, DATA_TYPE,
                    CHECKLIST, OUTLIER_ZSCORE, OUTLIER_IQR, REF, RECON, CUSTOM).
                    Each registers itself via @register("TYPE") in registry.py.
templates/
  default_templates.py   SQL templates (aggregate + row-level detail) per check type
adapters/
  mock_session.py         Demo backend - no Snowflake required
  snowflake_session.py    Production backend - one session per worker thread
  config_loader.py        Loads DQ_CHECK_CONFIG rows (Snowflake or in-memory demo list)
  result_logger.py        Batched writer for DQ_RESULTS / DQ_RUN_LOG (Snowflake insert or CSV)
  record_fetcher.py       Fetches sample failed row keys, only when a check has failed
demo_config_data.py Sample config rows matching the conversation's ORDERS/CUSTOMERS examples
```

## Design decisions this implements

- **Uniform contract**: every check function returns `total_rows` /
  `failed_rows` (RECON and CUSTOM are forced into this shape too - see
  their docstrings for why they're special-cased).
- **One config row -> many checks**: `registry.resolve_check_instances`
  explodes a single DQ_CHECK_CONFIG row into a `CheckInstance` per
  populated check family (e.g. a row with `NULL_CHECK_ACTIVE` and
  `OUTLIER_SENSITIVITY` both set yields two instances).
- **Error isolation**: check functions raise; only `driver.py` catches
  and converts exceptions into `STATUS=ERROR` results, so every check
  type reports errors the same way.
- **Conditional detail fetch**: `RecordFetcher` only runs, and only for
  checks that failed and have a meaningful row-level detail template -
  passing checks never pay for a second query.
- **Concurrency**: `ThreadPoolExecutor` with a bounded `max_workers`
  (checks are I/O-bound, waiting on the warehouse - threads are
  appropriate, not multiprocessing). Each check's exceptions are caught
  individually so one bad check never drops others from the batch.
  `--sequential` disables this for debugging.
- **Shadow mode**: `CHECK_STATUS` (`DRAFT` / `SHADOW` / `ACTIVE` /
  `RETIRED`) is read by the config loaders - `SHADOW` and `ACTIVE` both
  run and log, only the eventual alerting layer (not built here) would
  treat them differently.
- **Ports & adapters**: `core/driver.py` depends only on the four ports
  in `core/ports.py`. Swapping Snowflake for the mock backend - or later,
  adding a new check type - never requires touching the driver.

## Running the demo (no Snowflake needed)

```bash
cd dq_framework
python main.py --demo --run-all
python main.py --demo --table ORDERS
python main.py --demo --check-id 203
python main.py --demo --run-all --sequential   # disable concurrency
```

Demo mode uses `MockSession`, which fakes query execution with
deterministic-per-SQL pseudo-random results - it proves the pipeline
(registry dispatch, concurrency, error isolation, conditional detail
fetch, batched logging) works end to end, but does **not** validate real
data. Results land in `./dq_output/DQ_RESULTS.csv` and `DQ_RUN_LOG.csv`.

## Running against real Snowflake

1. Create `DQ_CHECK_CONFIG`, `DQ_RESULTS`, and `DQ_RUN_LOG` tables. Column
   names must match what `core/registry.py` and `adapters/result_logger.py`
   expect - see `demo_config_data.py` for the full set of DQ_CHECK_CONFIG
   fields the resolver reads (`NULL_CHECK_ACTIVE`, `LOWER_BOUND`/
   `UPPER_BOUND`, `REGEX_PATTERN`, `ALLOWED_VALUES`, `OUTLIER_SENSITIVITY`,
   `REFERENCE_TABLE`/`REFERENCE_COLUMN`, `RECON_SOURCE_SQL`/
   `RECON_TARGET_SQL`, `CUSTOM_SQL`, `ROW_IDENTIFIER_COLUMNS`,
   `CHECK_STATUS`, `CRITICALITY`, `SCHEDULE_GROUP`, plus a
   `*_THRESHOLD`/`*_THRESHOLD_TYPE` pair per check family).
2. Install the connector: `pip install snowflake-connector-python`
3. Set environment variables:
   ```bash
   export SNOWFLAKE_ACCOUNT=...
   export SNOWFLAKE_USER=...
   export SNOWFLAKE_PASSWORD=...       # or SNOWFLAKE_PRIVATE_KEY for key-pair auth
   export SNOWFLAKE_ROLE=...
   export SNOWFLAKE_WAREHOUSE=...
   export SNOWFLAKE_DATABASE=...
   ```
4. Run:
   ```bash
   python main.py --run-all \
     --config-table DQ_META.PUBLIC.DQ_CHECK_CONFIG \
     --results-table DQ_META.PUBLIC.DQ_RESULTS \
     --run-log-table DQ_META.PUBLIC.DQ_RUN_LOG
   ```

## Adding a new check type

1. Add a branch to `core/registry.py::resolve_check_instances` that
   detects the new config columns and builds a `CheckInstance`.
2. Add the SQL to `templates/default_templates.py` (aggregate + optional
   detail).
3. Add a new file in `checks/` that renders the template and calls
   `execute_aggregate_check` (or writes fully custom logic, as
   `recon_check.py` does).
4. Register it with `@register("YOUR_TYPE")` and add the import to
   `checks/__init__.py`.

`core/driver.py` requires no changes for any of this - that's the point
of routing everything through `CHECK_REGISTRY`.

## What's intentionally not included here

Config versioning/audit history (handled via RBAC + Snowflake's native
query/access history, per the design discussion, not by the engine) and
freshness checks (straightforward to add via the pattern above, left out
since no sample config row exercises it yet). Additionally, as `config_loader.py` stands along, another class can stand in the place of it which can parse a yaml, csv, or json file to get the configs. 
