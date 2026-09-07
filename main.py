"""
CLI entry point for the DQ framework.

The database backend is picked by name, not hardcoded -- see
adapters/session_registry.py. Built-in options: "snowflake", "sqlite",
"mock". Select one via --db-type, or the DQ_DB_TYPE environment variable,
or add a new adapter module and it becomes available the same way.

Demo mode (no real database at all -- mock data, CSV output):
    python main.py --demo --run-all
    python main.py --demo --table ORDERS
    python main.py --demo --check-id 203
    python main.py --demo --run-all --sequential      (disable concurrency)
    (--demo is sugar for --db-type mock)

Against a real database (Snowflake, SQLite, or any other registered type):
    python main.py --db-type snowflake --run-all \
        --config-table DQ_META.PUBLIC.DQ_CHECK_CONFIG \
        --results-table DQ_META.PUBLIC.DQ_RESULTS \
        --run-log-table DQ_META.PUBLIC.DQ_RUN_LOG

    python main.py --db-type sqlite --run-all \
        --config-table dq_check_config \
        --results-table dq_results \
        --run-log-table dq_run_log

Snowflake reads SNOWFLAKE_* env vars (see adapters/snowflake_session.py).
SQLite reads DQ_SQLITE_PATH, defaulting to ./dq_framework.db (see
adapters/sqlite_session.py).
"""

import argparse
import logging
import os
import sys

import checks  # noqa: F401 -- importing this registers all check functions
import adapters  # noqa: F401 -- importing this registers all session backends


def build_parser():
    p = argparse.ArgumentParser(description="Config-Driven DQ Framework")
    p.add_argument("--demo", action="store_true", help="Shortcut for --db-type mock")
    p.add_argument(
        "--db-type",
        default=os.environ.get("DQ_DB_TYPE", "snowflake"),
        help="Which registered backend to use (snowflake, sqlite, mock, or any custom adapter). "
        "Defaults to the DQ_DB_TYPE env var, then 'snowflake'.",
    )
    p.add_argument("--check-id", help="Run checks for a single CHECK_ID")
    p.add_argument(
        "--table", help="Run checks for all config rows targeting this table"
    )
    p.add_argument(
        "--schedule-group", help="Run checks belonging to this schedule group"
    )
    p.add_argument(
        "--run-all", action="store_true", help="Run every ACTIVE/SHADOW check"
    )
    p.add_argument(
        "--sequential",
        action="store_true",
        help="Disable concurrency (useful for debugging)",
    )
    p.add_argument("--max-workers", type=int, default=8)
    p.add_argument("--detail-limit", type=int, default=20)
    p.add_argument(
        "--output-dir",
        default="./dq_output",
        help="Mock backend: where CSV results are written",
    )
    p.add_argument(
        "--config-table", help="Fully-qualified DQ_CHECK_CONFIG table (real backends)"
    )
    p.add_argument(
        "--results-table", help="Fully-qualified DQ_RESULTS table (real backends)"
    )
    p.add_argument(
        "--run-log-table", help="Fully-qualified DQ_RUN_LOG table (real backends)"
    )
    return p


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    args = build_parser().parse_args()

    if not any([args.check_id, args.table, args.schedule_group, args.run_all]):
        print(
            "Specify one of --check-id, --table, --schedule-group, or --run-all",
            file=sys.stderr,
        )
        sys.exit(1)

    db_type = "mock" if args.demo else args.db_type

    from core.driver import DQDriver
    from adapters.session_registry import build_session, SESSION_REGISTRY
    from adapters.record_fetcher import RecordFetcher

    try:
        session = build_session(db_type)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if db_type == "mock":
        from adapters.config_loader import DemoConfigLoader
        from adapters.result_logger import CsvResultLogger
        from demo_config_data import SAMPLE_CONFIG_ROWS

        config_loader = DemoConfigLoader(SAMPLE_CONFIG_ROWS)
        result_logger = CsvResultLogger(args.output_dir)
    else:
        if not (args.config_table and args.results_table and args.run_log_table):
            print(
                f"--db-type {db_type} requires --config-table, --results-table, --run-log-table",
                file=sys.stderr,
            )
            sys.exit(1)
        from adapters.config_loader import SqlConfigLoader
        from adapters.result_logger import SqlResultLogger

        config_loader = SqlConfigLoader(session, args.config_table)
        result_logger = SqlResultLogger(session, args.results_table, args.run_log_table)

    driver = DQDriver(
        config_loader=config_loader,
        session=session,
        result_logger=result_logger,
        record_fetcher=RecordFetcher(session),
        max_workers=args.max_workers,
    )

    try:
        summary = driver.run(
            check_id=args.check_id,
            table_name=args.table,
            schedule_group=args.schedule_group,
            run_all=args.run_all,
            concurrent=not args.sequential,
            detail_limit=args.detail_limit,
        )
    finally:
        # Release every per-worker-thread connection the session opened.
        # A custom third-party adapter that doesn't implement close_all
        # is tolerated (getattr default) rather than required.
        close_all = getattr(session, "close_all", None)
        if close_all:
            close_all()

    print(
        f"\nBackend: {db_type} (available: {', '.join(sorted(SESSION_REGISTRY.keys()))})"
    )
    print(f"Run {summary.run_id}: {summary.overall_status}")
    print(
        f"  attempted={summary.checks_attempted} passed={summary.checks_passed} "
        f"failed={summary.checks_failed} errored={summary.checks_errored}"
    )
    if db_type == "mock":
        print(f"  results written to {args.output_dir}/DQ_RESULTS.csv")
        print(f"  run log written to {args.output_dir}/DQ_RUN_LOG.csv")


if __name__ == "__main__":
    main()
