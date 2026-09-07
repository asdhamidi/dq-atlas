import csv
import json
from datetime import datetime

from adapters.result_logger import SqlResultLogger, CsvResultLogger
from core.models import CheckResult, RunSummary
from tests.conftest import FakeSession


def _result(**overrides):
    defaults = dict(
        run_id="run-1", check_id="1", check_type="NULL", status="SUCCESS",
        total_rows=100, failed_rows=5, fail_pct=5.0,
        threshold_type="PERCENT", threshold_value=1.0, pass_fail_flag="FAIL",
        criticality="WARN", check_status_at_run="ACTIVE",
        rendered_sql="SELECT 1", sample_failed_keys=None, error_message=None,
        execution_time_ms=12, executed_at=datetime(2026, 1, 1, 0, 0, 0),
    )
    defaults.update(overrides)
    return CheckResult(**defaults)


class TestSqlResultLogger:
    def test_empty_results_is_a_noop(self):
        session = FakeSession()
        logger = SqlResultLogger(session, "RESULTS", "RUN_LOG")
        logger.log_results([])
        assert session.executed == []

    def test_builds_insert_with_escaped_values(self):
        session = FakeSession()
        logger = SqlResultLogger(session, "RESULTS", "RUN_LOG")
        logger.log_results([_result(error_message="it broke: can't parse")])
        sql = session.executed[0]
        assert "INSERT INTO RESULTS" in sql
        assert "can''t parse" in sql  # escaped, not a raw apostrophe

    def test_sample_failed_keys_are_json_encoded(self):
        session = FakeSession()
        logger = SqlResultLogger(session, "RESULTS", "RUN_LOG")
        logger.log_results([_result(sample_failed_keys=[{"ORDER_ID": 1}])])
        sql = session.executed[0]
        assert json.dumps([{"ORDER_ID": 1}]).replace("'", "''") in sql

    def test_log_run_summary_builds_insert(self):
        session = FakeSession()
        logger = SqlResultLogger(session, "RESULTS", "RUN_LOG")
        summary = RunSummary(
            run_id="run-1", schedule_group="DAILY",
            batch_start=datetime(2026, 1, 1), batch_end=datetime(2026, 1, 1, 0, 1),
            checks_attempted=2, checks_passed=1, checks_failed=1, checks_errored=0,
            overall_status="FAIL",
        )
        logger.log_run_summary(summary)
        sql = session.executed[0]
        assert "INSERT INTO RUN_LOG" in sql
        assert "'FAIL'" in sql


class TestCsvResultLogger:
    def test_writes_header_once_and_appends_rows(self, tmp_path):
        logger = CsvResultLogger(str(tmp_path))
        logger.log_results([_result(check_id="1")])
        logger.log_results([_result(check_id="2")])

        with open(logger.results_path, newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2
        assert [r["check_id"] for r in rows] == ["1", "2"]

    def test_sample_failed_keys_are_json_encoded_in_csv(self, tmp_path):
        logger = CsvResultLogger(str(tmp_path))
        logger.log_results([_result(sample_failed_keys=[{"ORDER_ID": 1}])])
        with open(logger.results_path, newline="") as f:
            row = next(csv.DictReader(f))
        assert json.loads(row["sample_failed_keys"]) == [{"ORDER_ID": 1}]

    def test_log_run_summary_appends(self, tmp_path):
        logger = CsvResultLogger(str(tmp_path))
        summary = RunSummary(
            run_id="run-1", schedule_group="DAILY",
            batch_start=datetime(2026, 1, 1), batch_end=datetime(2026, 1, 1),
            checks_attempted=1, checks_passed=1, checks_failed=0, checks_errored=0,
        )
        logger.log_run_summary(summary)
        with open(logger.run_log_path, newline="") as f:
            row = next(csv.DictReader(f))
        assert row["run_id"] == "run-1"

    def test_empty_results_does_not_create_file_write(self, tmp_path):
        logger = CsvResultLogger(str(tmp_path))
        logger.log_results([])
        import os
        assert not os.path.exists(logger.results_path)
