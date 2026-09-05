"""
ResultLogger adapters. Batches all results from a run into a single insert
rather than one round trip per check -- matters once a run covers 50-200+
checks. Demo mode writes CSV files instead of Snowflake so output is
inspectable without a warehouse.
"""
import csv
import os
import json
from dataclasses import asdict
from typing import List
from core.models import CheckResult, RunSummary
from core.sql_render import safe_literal


class SnowflakeResultLogger:
    def __init__(self, session, results_table_fqn: str, run_log_table_fqn: str):
        self.session = session
        self.results_table_fqn = results_table_fqn
        self.run_log_table_fqn = run_log_table_fqn

    def log_results(self, results: List[CheckResult]) -> None:
        if not results:
            return
        conn = self.session.get_connection()
        value_clauses = [self._result_to_values_clause(r) for r in results]
        sql = (
            f"INSERT INTO {self.results_table_fqn} "
            "(RUN_ID, CHECK_ID, CHECK_TYPE, STATUS, TOTAL_ROWS, FAILED_ROWS, FAIL_PCT, "
            "THRESHOLD_TYPE, THRESHOLD_VALUE, PASS_FAIL_FLAG, CRITICALITY, "
            "CHECK_STATUS_AT_RUN, RENDERED_SQL, SAMPLE_FAILED_KEYS, ERROR_MESSAGE, "
            "EXECUTION_TIME_MS, EXECUTED_AT) VALUES "
            + ", ".join(value_clauses)
        )
        self.session.execute(conn, sql)

    @staticmethod
    def _result_to_values_clause(r: CheckResult) -> str:
        sample = json.dumps(r.sample_failed_keys) if r.sample_failed_keys else None
        vals = [
            safe_literal(r.run_id), safe_literal(r.check_id), safe_literal(r.check_type),
            safe_literal(r.status), safe_literal(r.total_rows), safe_literal(r.failed_rows),
            safe_literal(r.fail_pct), safe_literal(r.threshold_type), safe_literal(r.threshold_value),
            safe_literal(r.pass_fail_flag), safe_literal(r.criticality), safe_literal(r.check_status_at_run),
            safe_literal(r.rendered_sql), safe_literal(sample), safe_literal(r.error_message),
            safe_literal(r.execution_time_ms), safe_literal(r.executed_at.isoformat()),
        ]
        return f"({', '.join(vals)})"

    def log_run_summary(self, summary: RunSummary) -> None:
        conn = self.session.get_connection()
        sql = (
            f"INSERT INTO {self.run_log_table_fqn} "
            "(RUN_ID, SCHEDULE_GROUP, BATCH_START, BATCH_END, CHECKS_ATTEMPTED, "
            "CHECKS_PASSED, CHECKS_FAILED, CHECKS_ERRORED, OVERALL_STATUS) VALUES ("
            f"{safe_literal(summary.run_id)}, {safe_literal(summary.schedule_group)}, "
            f"{safe_literal(summary.batch_start.isoformat())}, "
            f"{safe_literal(summary.batch_end.isoformat() if summary.batch_end else None)}, "
            f"{safe_literal(summary.checks_attempted)}, {safe_literal(summary.checks_passed)}, "
            f"{safe_literal(summary.checks_failed)}, {safe_literal(summary.checks_errored)}, "
            f"{safe_literal(summary.overall_status)})"
        )
        self.session.execute(conn, sql)


class CsvResultLogger:
    """Demo logger -- writes DQ_RESULTS.csv / DQ_RUN_LOG.csv so output is inspectable."""

    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.results_path = os.path.join(output_dir, "DQ_RESULTS.csv")
        self.run_log_path = os.path.join(output_dir, "DQ_RUN_LOG.csv")

    def log_results(self, results: List[CheckResult]) -> None:
        if not results:
            return
        file_exists = os.path.exists(self.results_path)
        with open(self.results_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(asdict(results[0]).keys()))
            if not file_exists:
                writer.writeheader()
            for r in results:
                row = asdict(r)
                if row.get("sample_failed_keys"):
                    row["sample_failed_keys"] = json.dumps(row["sample_failed_keys"])
                writer.writerow(row)

    def log_run_summary(self, summary: RunSummary) -> None:
        file_exists = os.path.exists(self.run_log_path)
        with open(self.run_log_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(asdict(summary).keys()))
            if not file_exists:
                writer.writeheader()
            writer.writerow(asdict(summary))
