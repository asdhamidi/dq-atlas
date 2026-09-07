import pytest

from adapters.record_fetcher import RecordFetcher
from tests.conftest import FakeSession


class TestRecordFetcher:
    def test_no_detail_check_types_short_circuit(self, make_instance):
        fetcher = RecordFetcher(FakeSession())
        for check_type in ("DATA_TYPE", "RECON", "CUSTOM", "OUTLIER_IQR"):
            instance = make_instance(check_type=check_type)
            assert fetcher.fetch_failed_records(instance) is None

    def test_missing_row_identifier_columns_short_circuits(self, make_instance):
        fetcher = RecordFetcher(FakeSession())
        instance = make_instance(check_type="NULL", row_identifier_columns=None)
        assert fetcher.fetch_failed_records(instance) is None

    def test_null_check_detail_query(self, make_instance):
        session = FakeSession(default=[{"ORDER_ID": 1}])
        fetcher = RecordFetcher(session)
        instance = make_instance(check_type="NULL", column="EMAIL", row_identifier_columns=["ORDER_ID"])
        rows = fetcher.fetch_failed_records(instance, limit=5)
        assert rows == [{"ORDER_ID": 1}]
        sql = session.executed[0]
        assert '"EMAIL" IS NULL' in sql
        assert "LIMIT 5" in sql

    def test_range_check_detail_uses_range_predicate(self, make_instance):
        session = FakeSession(default=[])
        fetcher = RecordFetcher(session)
        instance = make_instance(
            check_type="RANGE", column="AMOUNT", row_identifier_columns=["ORDER_ID"],
            params={"lower_bound": 0, "upper_bound": 100},
        )
        fetcher.fetch_failed_records(instance)
        sql = session.executed[0]
        assert '"AMOUNT" < 0' in sql and '"AMOUNT" > 100' in sql

    def test_ref_check_detail_uses_safe_fq_name_for_reference_table(self, make_instance):
        """Regression test: reference_table used to be interpolated raw
        into the detail query too, not just the aggregate one."""
        session = FakeSession(default=[])
        fetcher = RecordFetcher(session)
        instance = make_instance(
            check_type="REF", column="CUSTOMER_ID", row_identifier_columns=["ORDER_ID"],
            params={"reference_table": "sales.public.customers", "reference_column": "customer_id"},
        )
        fetcher.fetch_failed_records(instance)
        assert '"SALES"."PUBLIC"."CUSTOMERS"' in session.executed[0]

    def test_ref_check_detail_rejects_malicious_reference_table(self, make_instance):
        session = FakeSession()
        fetcher = RecordFetcher(session)
        instance = make_instance(
            check_type="REF", column="CUSTOMER_ID", row_identifier_columns=["ORDER_ID"],
            params={"reference_table": "CUSTOMERS; DROP TABLE x; --", "reference_column": "customer_id"},
        )
        with pytest.raises(ValueError):
            fetcher.fetch_failed_records(instance)

    def test_checklist_detail_uses_literal_list(self, make_instance):
        session = FakeSession(default=[])
        fetcher = RecordFetcher(session)
        instance = make_instance(
            check_type="CHECKLIST", column="STATUS", row_identifier_columns=["ORDER_ID"],
            params={"allowed_values": ["OPEN", "CLOSED"]},
        )
        fetcher.fetch_failed_records(instance)
        assert "'OPEN', 'CLOSED'" in session.executed[0]

    def test_duplicate_detail_uses_key_columns(self, make_instance):
        session = FakeSession(default=[])
        fetcher = RecordFetcher(session)
        instance = make_instance(
            check_type="DUPLICATE", column=None, row_identifier_columns=["ORDER_ID", "LINE_NO"],
            params={"key_columns": ["ORDER_ID", "LINE_NO"]},
        )
        fetcher.fetch_failed_records(instance)
        assert '"ORDER_ID", "LINE_NO"' in session.executed[0]
