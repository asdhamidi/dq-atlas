"""
Shared fixtures for the test suite.

Importing `checks` and `adapters` here (once, session-scoped) mirrors what
main.py does before building a driver -- it populates CHECK_REGISTRY and
SESSION_REGISTRY as a side effect of import. Tests that dispatch through
either registry depend on this having happened.
"""
import threading

import pytest

import checks  # noqa: F401 -- registers every check type
import adapters  # noqa: F401 -- registers every session backend

from core.models import CheckInstance


class FakeSession:
    """
    Test double for SessionPort. Scripted by a list of
    (predicate(sql) -> bool, response) pairs checked in order against each
    executed statement; the first match wins. `response` may be a list of
    row-dicts or a callable(sql) -> list of row-dicts. Falls back to
    `default` (or `default(sql)`) if nothing matches. Records every
    executed statement (in order) so tests can assert on rendered SQL.
    """

    def __init__(self, responses=None, default=None):
        self.responses = responses or []
        self.default = default if default is not None else []
        self.executed = []
        self._local = threading.local()

    def get_connection(self):
        if not hasattr(self._local, "conn"):
            self._local.conn = object()
        return self._local.conn

    def execute(self, connection, sql: str):
        self.executed.append(sql)
        for predicate, response in self.responses:
            if predicate(sql):
                return response(sql) if callable(response) else response
        return self.default(sql) if callable(self.default) else self.default

    def close_all(self):
        if hasattr(self._local, "conn"):
            del self._local.conn


class RecordingResultLogger:
    """Test double for ResultLoggerPort -- just remembers what it was given."""

    def __init__(self):
        self.logged_results = []
        self.logged_summaries = []

    def log_results(self, results):
        self.logged_results.append(list(results))

    def log_run_summary(self, summary):
        self.logged_summaries.append(summary)


class ListConfigLoader:
    """Test double for ConfigLoaderPort -- returns exactly the rows it was given."""

    def __init__(self, rows):
        self._rows = rows

    def load_config_rows(self, check_id=None, table_name=None, schedule_group=None, run_all=False):
        return list(self._rows)


class NullRecordFetcher:
    """Test double for RecordFetcherPort -- never returns detail rows."""

    def fetch_failed_records(self, instance, limit=20):
        return None


@pytest.fixture
def fake_session():
    return FakeSession()


@pytest.fixture
def base_row():
    """A minimal, valid DQ_CHECK_CONFIG row with the fields every check
    family needs, ready to be extended per-test with the fields that
    activate a specific check type."""
    return {
        "CHECK_ID": "1",
        "DATABASE_NAME": "DB",
        "SCHEMA_NAME": "SCHEMA",
        "TABLE_NAME": "TABLE",
        "COLUMN_NAME": "COL",
        "ROW_IDENTIFIER_COLUMNS": ["ID"],
        "CRITICALITY": "WARN",
        "CHECK_STATUS": "ACTIVE",
        "SCHEDULE_GROUP": "DAILY",
    }


@pytest.fixture
def make_instance():
    """Factory for a CheckInstance with sane defaults, for tests that want
    to exercise a single check module directly without going through
    registry resolution."""

    def _make(**overrides):
        defaults = dict(
            check_id="1",
            check_type="NULL",
            database="DB",
            schema="SCHEMA",
            table="TABLE",
            column="COL",
            params={},
            threshold_type="COUNT",
            threshold_value=0,
            criticality="WARN",
            check_status="ACTIVE",
            schedule_group="DAILY",
            row_identifier_columns=["ID"],
        )
        defaults.update(overrides)
        return CheckInstance(**defaults)

    return _make
