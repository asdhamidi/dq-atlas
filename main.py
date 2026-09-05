"""
CLI entry point for the DQ framework.

Demo mode (no Snowflake needed -- uses mock data and writes CSV output):
    python main.py --demo --run-all
    python main.py --demo --table ORDERS
    python main.py --demo --check-id 203
    python main.py --demo --run-all --sequential      (disable concurrency)

Production mode (reads SNOWFLAKE_* env vars, see adapters/snowflake_session.py):
    python main.py --run-all \
        --config-table DQ_META.PUBLIC.DQ_CHECK_CONFIG \
        --results-table DQ_META.PUBLIC.DQ_RESULTS \
        --run-log-table DQ_META.PUBLIC.DQ_RUN_LOG
"""
import argparse
import logging
import sys

import checks  # noqa: F401 -- importing this registers all check functions


def build_parser():
    p = argparse.ArgumentParser(description="Snowflake DQ Framework")
    p.add_argument("--demo", action="store_true", help="Run against mock data, no Snowflake needed")
    p.add_argument("--check-id", help="Run checks for a single CHECK_ID")
    p.add_argument("--table", help="Run checks for all config rows targeting this table")
    p.add_argument("--schedule-group", help="Run checks belonging to this schedule group")
    p.add_argument("--run-all", action="store_true", help="Run every ACTIVE/SHADOW check")
    p.add_argument("--sequential", action="store_true", help="Disable concurrency (useful for debugging)")
    p.add_argument("--max-workers", type=int, default=8)
    p.add_argument("--detail-limit", type=int, default=20)
    p.add_argument("--output-dir", default="./dq_output", help="Demo mode: where CSV results are written")
    p.add_argument("--config-table", help="Fully-qualified DQ_CHECK_CONFIG table (production mode)")
    p.add_argument("--results-table", help="Fully-qualified DQ_RESULTS table (production mode)")
    p.add_argument("--run-log-table", help="Fully-qualified DQ_RUN_LOG table (production mode)")
    return p


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args()

    if not any([args.check_id, args.table, args.schedule_group, args.run_all]):
        print("Specify one of --check-id, --table, --schedule-group, or --run-all", file=sys.stderr)
        sys.exit(1)

    from core.driver import DQDriver

    if args.demo:
        from adapters.mock_session import MockSession
        from adapters.config_loader import DemoConfigLoader
        from adapters.result_logger import CsvResultLogger
        from adapters.record_fetcher import RecordFetcher
        from demo_config_data import SAMPLE_CONFIG_ROWS

        session = MockSession()
        driver = DQDriver(
            config_loader=DemoConfigLoader(SAMPLE_CONFIG_ROWS),
            session=session,
            result_logger=CsvResultLogger(args.output_dir),
            record_fetcher=RecordFetcher(session),
            max_workers=args.max_workers,
        )
    else:
        if not (args.config_table and args.results_table and args.run_log_table):
            print(
                "Production mode requires --config-table, --results-table, --run-log-table",
                file=sys.stderr,
            )
            sys.exit(1)
        from adapters.snowflake_session import SnowflakeSession
        from adapters.config_loader import SnowflakeConfigLoader
        from adapters.result_logger import SnowflakeResultLogger
        from adapters.record_fetcher import RecordFetcher

        session = SnowflakeSession()
        driver = DQDriver(
            config_loader=SnowflakeConfigLoader(session, args.config_table),
            session=session,
            result_logger=SnowflakeResultLogger(session, args.results_table, args.run_log_table),
            record_fetcher=RecordFetcher(session),
            max_workers=args.max_workers,
        )

    summary = driver.run(
        check_id=args.check_id,
        table_name=args.table,
        schedule_group=args.schedule_group,
        run_all=args.run_all,
        concurrent=not args.sequential,
        detail_limit=args.detail_limit,
    )

    print(f"\nRun {summary.run_id}: {summary.overall_status}")
    print(
        f"  attempted={summary.checks_attempted} passed={summary.checks_passed} "
        f"failed={summary.checks_failed} errored={summary.checks_errored}"
    )
    if args.demo:
        print(f"  results written to {args.output_dir}/DQ_RESULTS.csv")
        print(f"  run log written to {args.output_dir}/DQ_RUN_LOG.csv")


if __name__ == "__main__":
    main()
