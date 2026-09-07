import pytest

from checks import (
    null_check, duplicate_check, range_check, type_check, data_type_check,
    checklist_check, outlier_check, ref_check, recon_check, custom_check,
)
from core.errors import CheckExecutionError
from tests.conftest import FakeSession


class TestNullCheck:
    def test_renders_and_evaluates(self, make_instance):
        session = FakeSession(default=[{"TOTAL_ROWS": 10, "FAILED_ROWS": 2}])
        instance = make_instance(check_type="NULL", column="EMAIL", threshold_type="COUNT", threshold_value=0)
        result = null_check.run(instance, session, "run-1")
        assert '"EMAIL" IS NULL' in session.executed[0]
        assert result.pass_fail_flag == "FAIL"


class TestDuplicateCheck:
    def test_renders_composite_key(self, make_instance):
        session = FakeSession(default=[{"TOTAL_ROWS": 10, "FAILED_ROWS": 0}])
        instance = make_instance(
            check_type="DUPLICATE", column=None,
            params={"key_columns": ["ORDER_ID", "LINE_NO"]},
            threshold_type="COUNT", threshold_value=0,
        )
        duplicate_check.run(instance, session, "run-1")
        assert '"ORDER_ID", "LINE_NO"' in session.executed[0]

    def test_key_columns_as_bare_string_is_rejected(self, make_instance):
        """Regression test: DUPLICATE_KEY_COLUMNS misconfigured as a plain
        string (instead of a list) must raise clearly, not silently
        explode into one quoted identifier per character."""
        session = FakeSession()
        instance = make_instance(
            check_type="DUPLICATE", column=None,
            params={"key_columns": "ORDER_ID"},
        )
        with pytest.raises(ValueError, match="Expected a list"):
            duplicate_check.run(instance, session, "run-1")


class TestRangeCheck:
    def test_two_sided_bound(self, make_instance):
        session = FakeSession(default=[{"TOTAL_ROWS": 10, "FAILED_ROWS": 1}])
        instance = make_instance(
            check_type="RANGE", column="AMOUNT",
            params={"lower_bound": 0, "upper_bound": 100},
        )
        range_check.run(instance, session, "run-1")
        sql = session.executed[0]
        assert '"AMOUNT" < 0' in sql and '"AMOUNT" > 100' in sql

    def test_one_sided_bound(self, make_instance):
        session = FakeSession(default=[{"TOTAL_ROWS": 10, "FAILED_ROWS": 0}])
        instance = make_instance(
            check_type="RANGE", column="AMOUNT",
            params={"lower_bound": 0, "upper_bound": None},
        )
        range_check.run(instance, session, "run-1")
        sql = session.executed[0]
        assert '"AMOUNT" < 0' in sql
        assert " OR " not in sql


class TestTypeCheck:
    def test_regex_pattern_is_escaped_literal(self, make_instance):
        session = FakeSession(default=[{"TOTAL_ROWS": 10, "FAILED_ROWS": 0}])
        instance = make_instance(
            check_type="TYPE", column="EMAIL",
            params={"regex_pattern": r"^[\w.]+@[\w.]+$"},
        )
        type_check.run(instance, session, "run-1")
        assert r"'^[\w.]+@[\w.]+$'" in session.executed[0]

    def test_embedded_quote_in_pattern_cannot_break_out(self, make_instance):
        session = FakeSession(default=[{"TOTAL_ROWS": 10, "FAILED_ROWS": 0}])
        instance = make_instance(
            check_type="TYPE", column="EMAIL",
            params={"regex_pattern": "'; DROP TABLE x; --"},
        )
        type_check.run(instance, session, "run-1")
        sql = session.executed[0]
        assert "'''; DROP TABLE x; --'" in sql


class TestDataTypeCheck:
    def test_match_reports_pass(self, make_instance):
        session = FakeSession(default=[{"TOTAL_ROWS": 1, "FAILED_ROWS": 0}])
        instance = make_instance(
            check_type="DATA_TYPE", column="AMOUNT", threshold_type="COUNT", threshold_value=0,
            params={"expected_data_type": "NUMBER"},
        )
        result = data_type_check.run(instance, session, "run-1")
        assert result.pass_fail_flag == "PASS"

    def test_dropped_or_renamed_column_errors_instead_of_false_pass(self, make_instance):
        """Regression test for the DATA_TYPE silent-false-PASS bug: if the
        column no longer exists, INFORMATION_SCHEMA.COLUMNS returns zero
        rows -- that must raise, not report a passing check."""
        session = FakeSession(default=[])
        instance = make_instance(
            check_type="DATA_TYPE", column="RENAMED_COL",
            params={"expected_data_type": "NUMBER"},
        )
        with pytest.raises(CheckExecutionError, match="zero rows"):
            data_type_check.run(instance, session, "run-1")


class TestChecklistCheck:
    def test_allowed_values_rendered_as_literals(self, make_instance):
        session = FakeSession(default=[{"TOTAL_ROWS": 10, "FAILED_ROWS": 0}])
        instance = make_instance(
            check_type="CHECKLIST", column="STATUS",
            params={"allowed_values": ["OPEN", "CLOSED"]},
        )
        checklist_check.run(instance, session, "run-1")
        assert "'OPEN', 'CLOSED'" in session.executed[0]

    def test_allowed_values_as_bare_string_is_rejected(self, make_instance):
        session = FakeSession()
        instance = make_instance(
            check_type="CHECKLIST", column="STATUS",
            params={"allowed_values": "OPEN"},
        )
        with pytest.raises(ValueError, match="Expected a list"):
            checklist_check.run(instance, session, "run-1")


class TestOutlierCheck:
    def test_zscore_uses_zscore_template(self, make_instance):
        session = FakeSession(default=[{"TOTAL_ROWS": 10, "FAILED_ROWS": 0}])
        instance = make_instance(check_type="OUTLIER_ZSCORE", column="AMOUNT", params={"sensitivity": 3})
        outlier_check.run_zscore(instance, session, "run-1")
        assert "STDDEV" in session.executed[0]

    def test_iqr_uses_iqr_template(self, make_instance):
        session = FakeSession(default=[{"TOTAL_ROWS": 10, "FAILED_ROWS": 0}])
        instance = make_instance(check_type="OUTLIER_IQR", column="AMOUNT", params={"sensitivity": 1.5})
        outlier_check.run_iqr(instance, session, "run-1")
        assert "PERCENTILE_CONT" in session.executed[0]


class TestRefCheck:
    def test_reference_table_is_quoted_per_part(self, make_instance):
        session = FakeSession(default=[{"TOTAL_ROWS": 10, "FAILED_ROWS": 0}])
        instance = make_instance(
            check_type="REF", column="CUSTOMER_ID",
            params={"reference_table": "sales.public.customers", "reference_column": "customer_id"},
        )
        ref_check.run(instance, session, "run-1")
        assert '"SALES"."PUBLIC"."CUSTOMERS"' in session.executed[0]

    def test_malicious_reference_table_is_rejected(self, make_instance):
        """Regression test: REFERENCE_TABLE used to be interpolated raw on
        the theory it's 'admin-controlled,' the same theory that applies
        to every other identifier -- it must go through the same
        validation now."""
        session = FakeSession()
        instance = make_instance(
            check_type="REF", column="CUSTOMER_ID",
            params={"reference_table": "CUSTOMERS; DROP TABLE x; --", "reference_column": "customer_id"},
        )
        with pytest.raises(ValueError):
            ref_check.run(instance, session, "run-1")


class TestReconCheck:
    def _session_for(self, source_val, target_val):
        return FakeSession(responses=[
            (lambda sql: "SOURCE" in sql, [{"RESULT": source_val}]),
            (lambda sql: "TARGET" in sql, [{"RESULT": target_val}]),
        ])

    def test_matching_values_pass(self, make_instance):
        session = self._session_for(100, 100)
        instance = make_instance(
            check_type="RECON", column=None,
            params={"source_sql": "SELECT COUNT(*) AS RESULT FROM SOURCE", "target_sql": "SELECT COUNT(*) AS RESULT FROM TARGET"},
            threshold_type="PERCENT", threshold_value=0.5,
        )
        result = recon_check.run(instance, session, "run-1")
        assert result.pass_fail_flag == "PASS"
        assert result.fail_pct == 0.0

    def test_negative_source_value_does_not_flip_sign(self, make_instance):
        """Regression test: abs() must wrap the whole ratio -- a negative
        source value must not produce a negative diff_pct that trivially
        clears a positive threshold regardless of the real mismatch."""
        session = self._session_for(-100, 0)  # 100% mismatch in magnitude
        instance = make_instance(
            check_type="RECON", column=None,
            params={"source_sql": "SELECT COUNT(*) AS RESULT FROM SOURCE", "target_sql": "SELECT COUNT(*) AS RESULT FROM TARGET"},
            threshold_type="PERCENT", threshold_value=0.5,
        )
        result = recon_check.run(instance, session, "run-1")
        assert result.fail_pct == 100.0
        assert result.pass_fail_flag == "FAIL"

    def test_zero_source_nonzero_target_is_a_total_mismatch(self, make_instance):
        """Regression test: source_val == 0 with a nonzero target used to
        report diff_pct=0.0 (false PASS) via the old `if source_val else
        0.0` fallback."""
        session = self._session_for(0, 500)
        instance = make_instance(
            check_type="RECON", column=None,
            params={"source_sql": "SELECT COUNT(*) AS RESULT FROM SOURCE", "target_sql": "SELECT COUNT(*) AS RESULT FROM TARGET"},
            threshold_type="PERCENT", threshold_value=0.5,
        )
        result = recon_check.run(instance, session, "run-1")
        assert result.fail_pct == 100.0
        assert result.pass_fail_flag == "FAIL"

    def test_zero_source_zero_target_passes(self, make_instance):
        session = self._session_for(0, 0)
        instance = make_instance(
            check_type="RECON", column=None,
            params={"source_sql": "SELECT COUNT(*) AS RESULT FROM SOURCE", "target_sql": "SELECT COUNT(*) AS RESULT FROM TARGET"},
            threshold_type="PERCENT", threshold_value=0.5,
        )
        result = recon_check.run(instance, session, "run-1")
        assert result.fail_pct == 0.0
        assert result.pass_fail_flag == "PASS"


class TestCustomCheck:
    def test_passes_through_admin_sql_verbatim(self, make_instance):
        session = FakeSession(default=[{"TOTAL_ROWS": 10, "FAILED_ROWS": 0}])
        instance = make_instance(check_type="CUSTOM", column=None, params={"custom_sql": "SELECT ... AS TOTAL_ROWS"})
        custom_check.run(instance, session, "run-1")
        assert session.executed[0] == "SELECT ... AS TOTAL_ROWS"

    def test_missing_total_rows_alias_errors_loudly(self, make_instance):
        session = FakeSession(default=[{"NOT_WHAT_WE_EXPECT": 1}])
        instance = make_instance(check_type="CUSTOM", column=None, params={"custom_sql": "SELECT 1"})
        with pytest.raises(CheckExecutionError, match="TOTAL_ROWS"):
            custom_check.run(instance, session, "run-1")
