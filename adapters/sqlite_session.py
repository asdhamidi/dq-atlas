"""
A second real backend, deliberately chosen because it needs zero external
dependencies (stdlib sqlite3) -- this is what makes it possible to prove
the session registry genuinely swaps backends, not just claim it does.

Honest scope note: this makes the CONNECTION layer portable. It does not
by itself make every check type's SQL portable -- the templates in
templates/default_templates.py use Snowflake-specific functions
(COUNT_IF, IFF, RLIKE, STDDEV, PERCENTILE_CONT, INFORMATION_SCHEMA.COLUMNS
syntax) that SQLite doesn't have. Config loading and result logging
(adapters/config_loader.py, adapters/result_logger.py) use plain ANSI SQL
and work against this adapter unchanged. CUSTOM checks work too, since
their SQL is admin-authored and can simply be written in whatever dialect
the target database speaks. NULL/RANGE/OUTLIER/etc. templated checks would
need SQLite-flavored template variants before they'd run correctly here --
that's a separate, already-documented gap, not something this adapter
silently papers over.
"""

import os
import sqlite3
import threading

from adapters.session_registry import register_session


class SqliteSession:
    def __init__(self, db_path = None):
        self.db_path = db_path or os.environ.get("DQ_SQLITE_PATH", "dq_framework.db")
        self._local = threading.local()

    def get_connection(self):
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    def execute(self, connection, sql: str):
        cursor = connection.cursor()
        try:
            cursor.execute(sql)
            if sql.strip().upper().startswith("SELECT"):
                return [dict(row) for row in cursor.fetchall()]
            connection.commit()
            return []
        finally:
            cursor.close()

    def close_all(self):
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            del self._local.conn


@register_session("sqlite")
def _build_sqlite_session():
    return SqliteSession()
