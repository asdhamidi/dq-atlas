"""
Integration test against a real SQLite database -- no mocks anywhere in
the session/config/result-logging layer. This is the test that actually
proves the "swap the backend, driver doesn't change" claim, using the one
check type documented as portable across backends (CUSTOM -- its SQL is
admin-authored and can be written in whatever dialect the target speaks;
see adapters/sqlite_session.py's module docstring).
"""
import sqlite3

from adapters.sqlite_session import SqliteSession
from adapters.config_loader import SqlConfigLoader
from adapters.result_logger import SqlResultLogger
from adapters.record_fetcher import RecordFetcher
from core.driver import DQDriver


def _setup_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE orders (order_id INTEGER, amount REAL);
        INSERT INTO orders (order_id, amount) VALUES
            (1, 100.0), (2, -5.0), (3, 50.0), (4, -1.0), (5, 20.0);

        CREATE TABLE dq_check_config (
            CHECK_ID TEXT, DATABASE_NAME TEXT, SCHEMA_NAME TEXT, TABLE_NAME TEXT,
            COLUMN_NAME TEXT, CHECK_STATUS TEXT, CRITICALITY TEXT, SCHEDULE_GROUP TEXT,
            ROW_IDENTIFIER_COLUMNS TEXT, CUSTOM_SQL TEXT, CUSTOM_THRESHOLD REAL,
            CUSTOM_THRESHOLD_TYPE TEXT
        );
        INSERT INTO dq_check_config VALUES (
            'C1', 'DB', 'SCHEMA', 'ORDERS', NULL, 'ACTIVE', 'CRITICAL', 'DAILY', NULL,
            'SELECT COUNT(*) AS TOTAL_ROWS, SUM(CASE WHEN amount < 0 THEN 1 ELSE 0 END) AS FAILED_ROWS FROM orders',
            0, 'COUNT'
        );

        CREATE TABLE dq_results (
            RUN_ID TEXT, CHECK_ID TEXT, CHECK_TYPE TEXT, STATUS TEXT,
            TOTAL_ROWS INTEGER, FAILED_ROWS INTEGER, FAIL_PCT REAL,
            THRESHOLD_TYPE TEXT, THRESHOLD_VALUE REAL, PASS_FAIL_FLAG TEXT,
            CRITICALITY TEXT, CHECK_STATUS_AT_RUN TEXT, RENDERED_SQL TEXT,
            SAMPLE_FAILED_KEYS TEXT, ERROR_MESSAGE TEXT, EXECUTION_TIME_MS INTEGER,
            EXECUTED_AT TEXT
        );

        CREATE TABLE dq_run_log (
            RUN_ID TEXT, SCHEDULE_GROUP TEXT, BATCH_START TEXT, BATCH_END TEXT,
            CHECKS_ATTEMPTED INTEGER, CHECKS_PASSED INTEGER, CHECKS_FAILED INTEGER,
            CHECKS_ERRORED INTEGER, OVERALL_STATUS TEXT
        );
        """
    )
    conn.commit()
    conn.close()


def test_full_pipeline_against_real_sqlite(tmp_path):
    db_path = str(tmp_path / "dq.db")
    _setup_db(db_path)

    session = SqliteSession(db_path)
    driver = DQDriver(
        config_loader=SqlConfigLoader(session, "dq_check_config"),
        session=session,
        result_logger=SqlResultLogger(session, "dq_results", "dq_run_log"),
        record_fetcher=RecordFetcher(session),
        max_workers=4,
    )

    try:
        summary = driver.run(run_all=True, concurrent=False)
    finally:
        session.close_all()

    assert summary.checks_attempted == 1
    assert summary.checks_failed == 1  # 2 negative amounts > COUNT threshold of 0
    assert summary.overall_status == "FAIL"

    # Verify it actually landed in SQLite, not just in the in-process result.
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    result_row = conn.execute("SELECT * FROM dq_results WHERE CHECK_ID = 'C1'").fetchone()
    assert result_row["TOTAL_ROWS"] == 5
    assert result_row["FAILED_ROWS"] == 2
    assert result_row["PASS_FAIL_FLAG"] == "FAIL"

    run_log_row = conn.execute("SELECT * FROM dq_run_log WHERE RUN_ID = ?", (summary.run_id,)).fetchone()
    assert run_log_row["OVERALL_STATUS"] == "FAIL"
    assert run_log_row["CHECKS_ATTEMPTED"] == 1
    conn.close()


def test_close_all_releases_the_thread_local_connection(tmp_path):
    session = SqliteSession(str(tmp_path / "dq.db"))
    conn = session.get_connection()
    assert conn is not None
    session.close_all()
    assert not hasattr(session._local, "conn")
