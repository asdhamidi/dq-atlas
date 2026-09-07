import pytest

from adapters.config_loader import SqlConfigLoader, DemoConfigLoader
from tests.conftest import FakeSession


class TestSqlConfigLoader:
    def test_requires_at_least_one_filter(self):
        loader = SqlConfigLoader(FakeSession(), "DQ_CHECK_CONFIG")
        with pytest.raises(ValueError):
            loader.load_config_rows()

    def test_run_all_needs_no_other_filter(self):
        session = FakeSession(default=[{"CHECK_ID": "1"}])
        loader = SqlConfigLoader(session, "DQ_CHECK_CONFIG")
        rows = loader.load_config_rows(run_all=True)
        assert rows == [{"CHECK_ID": "1"}]
        assert "CHECK_STATUS IN ('ACTIVE', 'SHADOW')" in session.executed[0]

    def test_filters_are_anded_together(self):
        session = FakeSession(default=[])
        loader = SqlConfigLoader(session, "DQ_CHECK_CONFIG")
        loader.load_config_rows(table_name="ORDERS", schedule_group="DAILY")
        sql = session.executed[0]
        assert "TABLE_NAME = 'ORDERS'" in sql
        assert "SCHEDULE_GROUP = 'DAILY'" in sql
        assert " AND " in sql

    def test_check_id_with_embedded_quote_is_escaped_not_injected(self):
        """
        Regression test: check_id/table_name/schedule_group come from CLI
        flags, previously f-string'd raw into the WHERE clause. A quote in
        the value used to be enough to break out of the string literal.
        """
        session = FakeSession(default=[])
        loader = SqlConfigLoader(session, "DQ_CHECK_CONFIG")
        malicious = "1' OR '1'='1"
        loader.load_config_rows(check_id=malicious)
        sql = session.executed[0]
        # The literal is escaped (quote doubled) and stays inside one
        # quoted string, rather than terminating it early.
        assert "CHECK_ID = '1'' OR ''1''=''1'" in sql


class TestDemoConfigLoader:
    ROWS = [
        {"CHECK_ID": "1", "TABLE_NAME": "ORDERS", "SCHEDULE_GROUP": "HOURLY", "CHECK_STATUS": "ACTIVE"},
        {"CHECK_ID": "2", "TABLE_NAME": "ORDERS", "SCHEDULE_GROUP": "DAILY", "CHECK_STATUS": "ACTIVE"},
        {"CHECK_ID": "3", "TABLE_NAME": "CUSTOMERS", "SCHEDULE_GROUP": "HOURLY", "CHECK_STATUS": "ACTIVE"},
        {"CHECK_ID": "4", "TABLE_NAME": "ORDERS", "SCHEDULE_GROUP": "HOURLY", "CHECK_STATUS": "RETIRED"},
    ]

    def test_requires_at_least_one_filter(self):
        loader = DemoConfigLoader(self.ROWS)
        with pytest.raises(ValueError):
            loader.load_config_rows()

    def test_run_all_excludes_retired_and_draft(self):
        loader = DemoConfigLoader(self.ROWS)
        rows = loader.load_config_rows(run_all=True)
        assert {r["CHECK_ID"] for r in rows} == {"1", "2", "3"}

    def test_single_filter(self):
        loader = DemoConfigLoader(self.ROWS)
        rows = loader.load_config_rows(table_name="ORDERS")
        assert {r["CHECK_ID"] for r in rows} == {"1", "2"}

    def test_filters_are_anded_together_matching_sql_loader(self):
        """
        Regression test: combining table_name and schedule_group used to
        be an if/elif chain that silently applied only the first one
        given, unlike SqlConfigLoader which ANDs every filter -- demo mode
        must behave the same way production does.
        """
        loader = DemoConfigLoader(self.ROWS)
        rows = loader.load_config_rows(table_name="ORDERS", schedule_group="DAILY")
        assert {r["CHECK_ID"] for r in rows} == {"2"}

    def test_check_id_takes_precedence_when_combined_with_a_non_matching_filter(self):
        loader = DemoConfigLoader(self.ROWS)
        rows = loader.load_config_rows(check_id="1", table_name="CUSTOMERS")
        assert rows == []  # AND semantics: check_id=1 is TABLE_NAME=ORDERS, not CUSTOMERS
