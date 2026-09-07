import pytest

from core.exec_helpers import execute_aggregate_check
from core.errors import CheckExecutionError
from tests.conftest import FakeSession


def test_happy_path_computes_result(make_instance):
    session = FakeSession(default=[{"TOTAL_ROWS": 200, "FAILED_ROWS": 50}])
    instance = make_instance(threshold_type="PERCENT", threshold_value=10.0)

    result = execute_aggregate_check(instance, session, "run-1", "SELECT ...")

    assert result.status == "SUCCESS"
    assert result.total_rows == 200
    assert result.failed_rows == 50
    assert result.fail_pct == 25.0
    assert result.pass_fail_flag == "FAIL"  # 25% > 10% threshold
    assert result.rendered_sql == "SELECT ..."
    assert result.execution_time_ms is not None


def test_session_exception_becomes_check_execution_error_with_sql(make_instance):
    def boom(sql):
        raise RuntimeError("warehouse is on fire")

    session = FakeSession(default=boom)
    instance = make_instance()

    with pytest.raises(CheckExecutionError) as exc_info:
        execute_aggregate_check(instance, session, "run-1", "SELECT 1")

    assert exc_info.value.rendered_sql == "SELECT 1"
    assert "warehouse is on fire" in str(exc_info.value)


def test_empty_result_set_raises_instead_of_silently_passing(make_instance):
    """
    Regression test for the DATA_TYPE false-PASS bug: an aggregate query
    that returns zero rows (e.g. the target column no longer exists) must
    surface as an ERROR, not silently compute total_rows=0/failed_rows=0
    and report PASS.
    """
    session = FakeSession(default=[])
    instance = make_instance()

    with pytest.raises(CheckExecutionError, match="zero rows"):
        execute_aggregate_check(instance, session, "run-1", "SELECT ...")


def test_missing_expected_column_raises_clear_error(make_instance):
    """CUSTOM's contract requires TOTAL_ROWS/FAILED_ROWS aliases -- if the
    admin-authored SQL forgets one, this must fail loudly with the SQL
    attached, not a bare KeyError with no context."""
    session = FakeSession(default=[{"TOTAL_ROWS": 10}])  # FAILED_ROWS missing
    instance = make_instance()

    with pytest.raises(CheckExecutionError, match="FAILED_ROWS") as exc_info:
        execute_aggregate_check(instance, session, "run-1", "SELECT ...")
    assert exc_info.value.rendered_sql == "SELECT ..."
