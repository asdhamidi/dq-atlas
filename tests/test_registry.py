import pytest

from core.registry import CHECK_REGISTRY, register, resolve_check_instances


class TestRegisterDecorator:
    def test_registers_function_under_check_type(self):
        try:
            @register("TEST_ONLY_TYPE")
            def fn(instance, session, run_id):
                return "sentinel"

            assert CHECK_REGISTRY["TEST_ONLY_TYPE"] is fn
        finally:
            CHECK_REGISTRY.pop("TEST_ONLY_TYPE", None)


class TestResolveCheckInstances:
    def test_null_check(self, base_row):
        base_row.update(NULL_CHECK_ACTIVE=True, NULL_THRESHOLD=0, NULL_THRESHOLD_TYPE="COUNT")
        instances = resolve_check_instances(base_row)
        assert len(instances) == 1
        assert instances[0].check_type == "NULL"
        assert instances[0].column == "COL"
        assert instances[0].threshold_type == "COUNT"

    def test_duplicate_check(self, base_row):
        base_row.update(DUPLICATE_KEY_COLUMNS=["ORDER_ID", "LINE_NO"], DUPLICATE_THRESHOLD=0)
        instances = resolve_check_instances(base_row)
        assert len(instances) == 1
        assert instances[0].check_type == "DUPLICATE"
        assert instances[0].params["key_columns"] == ["ORDER_ID", "LINE_NO"]

    def test_range_check_two_sided(self, base_row):
        base_row.update(LOWER_BOUND=0, UPPER_BOUND=100)
        instances = resolve_check_instances(base_row)
        assert len(instances) == 1
        assert instances[0].check_type == "RANGE"
        assert instances[0].params == {"lower_bound": 0, "upper_bound": 100}

    def test_range_check_one_sided(self, base_row):
        base_row.update(LOWER_BOUND=0)
        instances = resolve_check_instances(base_row)
        assert instances[0].params == {"lower_bound": 0, "upper_bound": None}

    def test_type_check(self, base_row):
        base_row.update(REGEX_PATTERN=r"^\d+$")
        instances = resolve_check_instances(base_row)
        assert instances[0].check_type == "TYPE"
        assert instances[0].params["regex_pattern"] == r"^\d+$"

    def test_data_type_check(self, base_row):
        base_row.update(EXPECTED_DATA_TYPE="TEXT")
        instances = resolve_check_instances(base_row)
        assert instances[0].check_type == "DATA_TYPE"
        assert instances[0].params["expected_data_type"] == "TEXT"

    def test_checklist_check(self, base_row):
        base_row.update(ALLOWED_VALUES=["OPEN", "CLOSED"])
        instances = resolve_check_instances(base_row)
        assert instances[0].check_type == "CHECKLIST"
        assert instances[0].params["allowed_values"] == ["OPEN", "CLOSED"]

    def test_outlier_defaults_to_zscore(self, base_row):
        base_row.update(OUTLIER_SENSITIVITY=3)
        instances = resolve_check_instances(base_row)
        assert instances[0].check_type == "OUTLIER_ZSCORE"

    def test_outlier_iqr_selected_via_template_id(self, base_row):
        base_row.update(OUTLIER_SENSITIVITY=1.5, OUTLIER_TEMPLATE_ID="OUTLIER_IQR")
        instances = resolve_check_instances(base_row)
        assert instances[0].check_type == "OUTLIER_IQR"

    def test_ref_check(self, base_row):
        base_row.update(REFERENCE_TABLE="DB.SCHEMA.OTHER", REFERENCE_COLUMN="ID")
        instances = resolve_check_instances(base_row)
        assert instances[0].check_type == "REF"
        assert instances[0].params["reference_table"] == "DB.SCHEMA.OTHER"

    def test_recon_check(self, base_row):
        base_row.update(RECON_SOURCE_SQL="SELECT COUNT(*) FROM A", RECON_TARGET_SQL="SELECT COUNT(*) FROM B")
        instances = resolve_check_instances(base_row)
        assert instances[0].check_type == "RECON"
        assert instances[0].threshold_type == "PERCENT"

    def test_custom_check(self, base_row):
        base_row.update(CUSTOM_SQL="SELECT 1 AS TOTAL_ROWS, 0 AS FAILED_ROWS")
        instances = resolve_check_instances(base_row)
        assert instances[0].check_type == "CUSTOM"

    def test_one_row_can_activate_multiple_check_families(self, base_row):
        base_row.update(
            NULL_CHECK_ACTIVE=True,
            LOWER_BOUND=0, UPPER_BOUND=100,
            OUTLIER_SENSITIVITY=3,
        )
        instances = resolve_check_instances(base_row)
        assert {i.check_type for i in instances} == {"NULL", "RANGE", "OUTLIER_ZSCORE"}

    def test_no_active_fields_yields_no_instances(self, base_row):
        assert resolve_check_instances(base_row) == []


class TestRequiredFieldValidation:
    """
    Regression tests: a malformed row must raise a clear, specific error
    (caught and isolated per-row by the driver) instead of a bare KeyError.
    """

    def test_missing_base_field_raises_clear_error(self, base_row):
        del base_row["DATABASE_NAME"]
        base_row["NULL_CHECK_ACTIVE"] = True
        with pytest.raises(ValueError, match="DATABASE_NAME"):
            resolve_check_instances(base_row)

    def test_missing_check_id_still_produces_a_readable_error(self, base_row):
        del base_row["CHECK_ID"]
        base_row["NULL_CHECK_ACTIVE"] = True
        with pytest.raises(ValueError, match="missing"):
            resolve_check_instances(base_row)

    def test_null_check_missing_column_name_raises(self, base_row):
        del base_row["COLUMN_NAME"]
        base_row["NULL_CHECK_ACTIVE"] = True
        with pytest.raises(ValueError, match="NULL.*COLUMN_NAME|COLUMN_NAME.*NULL"):
            resolve_check_instances(base_row)

    def test_ref_check_missing_reference_column_raises(self, base_row):
        base_row["REFERENCE_TABLE"] = "DB.SCHEMA.OTHER"
        # REFERENCE_COLUMN intentionally omitted
        with pytest.raises(ValueError, match="REFERENCE_COLUMN"):
            resolve_check_instances(base_row)

    def test_recon_check_missing_target_sql_raises(self, base_row):
        base_row["RECON_SOURCE_SQL"] = "SELECT COUNT(*) FROM A"
        # RECON_TARGET_SQL intentionally omitted
        with pytest.raises(ValueError, match="RECON_TARGET_SQL"):
            resolve_check_instances(base_row)
