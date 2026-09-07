import pytest

from core.driver import DQDriver
from core.registry import CHECK_REGISTRY
from tests.conftest import FakeSession, RecordingResultLogger, ListConfigLoader, NullRecordFetcher


def _row(check_id, **overrides):
    row = {
        "CHECK_ID": check_id,
        "DATABASE_NAME": "DB",
        "SCHEMA_NAME": "SCHEMA",
        "TABLE_NAME": "TABLE",
        "CRITICALITY": "WARN",
        "CHECK_STATUS": "ACTIVE",
        "SCHEDULE_GROUP": "DAILY",
    }
    row.update(overrides)
    return row


def _find(results, check_id, check_type=None):
    for r in results:
        if r.check_id == check_id and (check_type is None or r.check_type == check_type):
            return r
    raise AssertionError(f"no result for check_id={check_id!r} check_type={check_type!r}")


class RecordingRecordFetcher:
    def __init__(self, response=None):
        self.calls = []
        self.response = response or [{"SAMPLE_KEY": 1}]

    def fetch_failed_records(self, instance, limit=20):
        self.calls.append(instance)
        return self.response


def make_driver(rows, session=None, result_logger=None, record_fetcher=None, max_workers=4):
    return DQDriver(
        config_loader=ListConfigLoader(rows),
        session=session or FakeSession(default=[{"TOTAL_ROWS": 100, "FAILED_ROWS": 0}]),
        result_logger=result_logger or RecordingResultLogger(),
        record_fetcher=record_fetcher or NullRecordFetcher(),
        max_workers=max_workers,
    )


class TestHappyPath:
    def test_pass_and_fail_and_summary(self):
        session = FakeSession(responses=[
            (lambda sql: '"A_COL"' in sql, [{"TOTAL_ROWS": 100, "FAILED_ROWS": 0}]),
            (lambda sql: '"B_COL"' in sql, [{"TOTAL_ROWS": 100, "FAILED_ROWS": 50}]),
        ])
        rows = [
            _row("201", COLUMN_NAME="A_COL", NULL_CHECK_ACTIVE=True,
                 NULL_THRESHOLD=0, NULL_THRESHOLD_TYPE="COUNT",
                 ROW_IDENTIFIER_COLUMNS=["ID"]),
            _row("202", COLUMN_NAME="B_COL", LOWER_BOUND=0, UPPER_BOUND=10,
                 RANGE_THRESHOLD=1.0, RANGE_THRESHOLD_TYPE="PERCENT",
                 ROW_IDENTIFIER_COLUMNS=["ID"]),
        ]
        logger = RecordingResultLogger()
        driver = make_driver(rows, session=session, result_logger=logger)

        summary = driver.run(run_all=True, concurrent=False)

        results = logger.logged_results[0]
        assert _find(results, "201", "NULL").pass_fail_flag == "PASS"
        assert _find(results, "202", "RANGE").pass_fail_flag == "FAIL"
        assert summary.checks_attempted == 2
        assert summary.checks_passed == 1
        assert summary.checks_failed == 1
        assert summary.checks_errored == 0
        assert summary.overall_status == "FAIL"
        assert logger.logged_summaries == [summary]


class TestErrorIsolation:
    def test_malformed_config_row_does_not_abort_the_batch(self):
        """
        Regression test: a config row that fails to resolve into a
        CheckInstance (missing a required field) must surface as one
        ERROR result, and every other row must still execute normally.
        """
        good_row = _row("good-1", COLUMN_NAME="COL", NULL_CHECK_ACTIVE=True,
                         NULL_THRESHOLD=0, ROW_IDENTIFIER_COLUMNS=["ID"])
        bad_row = _row("bad-1", NULL_CHECK_ACTIVE=True)  # missing COLUMN_NAME
        del bad_row["DATABASE_NAME"]  # also missing a base field, for good measure

        logger = RecordingResultLogger()
        driver = make_driver([good_row, bad_row], result_logger=logger)

        summary = driver.run(run_all=True, concurrent=False)
        results = logger.logged_results[0]

        good_result = _find(results, "good-1")
        assert good_result.status == "SUCCESS"
        assert good_result.pass_fail_flag == "PASS"

        bad_result = _find(results, "bad-1")
        assert bad_result.status == "ERROR"
        assert bad_result.check_type == "UNRESOLVED"
        assert "DATABASE_NAME" in bad_result.error_message

        assert summary.checks_attempted == 2
        assert summary.checks_errored == 1
        assert summary.overall_status == "ERROR"

    def test_execution_error_does_not_abort_other_checks(self):
        def raise_for_boom(sql):
            raise RuntimeError("simulated warehouse failure")

        session = FakeSession(
            responses=[(lambda sql: "BOOM_MARKER" in sql, raise_for_boom)],
            default=[{"TOTAL_ROWS": 100, "FAILED_ROWS": 0}],
        )
        rows = [
            _row("ok-1", COLUMN_NAME="COL", NULL_CHECK_ACTIVE=True,
                 NULL_THRESHOLD=0, ROW_IDENTIFIER_COLUMNS=["ID"]),
            _row("err-1", CUSTOM_SQL="SELECT BOOM_MARKER AS TOTAL_ROWS",
                 CUSTOM_THRESHOLD=0, ROW_IDENTIFIER_COLUMNS=["ID"]),
        ]
        logger = RecordingResultLogger()
        driver = make_driver(rows, session=session, result_logger=logger)

        summary = driver.run(run_all=True, concurrent=False)
        results = logger.logged_results[0]

        assert _find(results, "ok-1").status == "SUCCESS"
        err_result = _find(results, "err-1", "CUSTOM")
        assert err_result.status == "ERROR"
        assert "simulated warehouse failure" in err_result.error_message
        assert summary.overall_status == "ERROR"

    def test_unregistered_check_type_produces_error_not_crash(self):
        row = _row("weird-1", COLUMN_NAME="COL", OUTLIER_SENSITIVITY=3,
                    OUTLIER_TEMPLATE_ID="OUTLIER_BOGUS")
        assert "OUTLIER_BOGUS" not in CHECK_REGISTRY

        logger = RecordingResultLogger()
        driver = make_driver([row], result_logger=logger)
        summary = driver.run(run_all=True, concurrent=False)

        result = _find(logger.logged_results[0], "weird-1")
        assert result.status == "ERROR"
        assert "OUTLIER_BOGUS" in result.error_message
        assert summary.checks_errored == 1


class TestDetailFetch:
    def test_only_invoked_for_failed_checks(self):
        session = FakeSession(responses=[
            (lambda sql: '"PASS_COL"' in sql, [{"TOTAL_ROWS": 100, "FAILED_ROWS": 0}]),
            (lambda sql: '"FAIL_COL"' in sql, [{"TOTAL_ROWS": 100, "FAILED_ROWS": 50}]),
        ])
        rows = [
            _row("pass-1", COLUMN_NAME="PASS_COL", NULL_CHECK_ACTIVE=True,
                 NULL_THRESHOLD=0, ROW_IDENTIFIER_COLUMNS=["ID"]),
            _row("fail-1", COLUMN_NAME="FAIL_COL", NULL_CHECK_ACTIVE=True,
                 NULL_THRESHOLD_TYPE="PERCENT", NULL_THRESHOLD=1.0,
                 ROW_IDENTIFIER_COLUMNS=["ID"]),
        ]
        fetcher = RecordingRecordFetcher()
        driver = make_driver(rows, session=session, record_fetcher=fetcher)

        driver.run(run_all=True, concurrent=False)

        assert len(fetcher.calls) == 1
        assert fetcher.calls[0].check_id == "fail-1"


class TestConcurrency:
    def test_concurrent_and_sequential_produce_equivalent_results(self):
        session_seq = FakeSession(default=[{"TOTAL_ROWS": 100, "FAILED_ROWS": 0}])
        session_conc = FakeSession(default=[{"TOTAL_ROWS": 100, "FAILED_ROWS": 0}])
        rows = [
            _row(str(i), COLUMN_NAME="COL", NULL_CHECK_ACTIVE=True,
                 NULL_THRESHOLD=0, ROW_IDENTIFIER_COLUMNS=["ID"])
            for i in range(6)
        ]

        seq_logger = RecordingResultLogger()
        make_driver(rows, session=session_seq, result_logger=seq_logger).run(
            run_all=True, concurrent=False
        )
        conc_logger = RecordingResultLogger()
        make_driver(rows, session=session_conc, result_logger=conc_logger).run(
            run_all=True, concurrent=True
        )

        def as_set(logger):
            return {(r.check_id, r.check_type, r.status, r.pass_fail_flag) for r in logger.logged_results[0]}

        assert as_set(seq_logger) == as_set(conc_logger)
