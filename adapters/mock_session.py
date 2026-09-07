"""
Demo/testing adapter -- satisfies SessionPort without any real database
connection. Returns plausible, deterministic-per-SQL pseudo-random results
so a demo run exercises the full driver/registry/logging pipeline end to
end. This does NOT validate real data -- pick a real backend for that.
"""

import hashlib
import random
import threading

from adapters.session_registry import register_session


class MockSession:
    def __init__(self):
        self._local = threading.local()

    def get_connection(self):
        # One "connection" per thread, mirroring how the real adapter
        # avoids sharing a single Snowflake connection across threads.
        if not hasattr(self._local, "conn"):
            self._local.conn = object()
        return self._local.conn

    def execute(self, connection, sql: str):
        seed = int(hashlib.md5(sql.encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        upper = sql.upper()

        if "INFORMATION_SCHEMA.COLUMNS" in upper:
            return [{"TOTAL_ROWS": 1, "FAILED_ROWS": rng.choice([0, 0, 0, 1])}]

        if "LIMIT" in upper and "GROUP BY" in upper and "HAVING" in upper:
            # detail-fetch style query for duplicates -- return a couple sample rows
            return [
                {"SAMPLE_KEY": rng.randint(1000, 9999), "OCCURRENCE_COUNT": 2}
                for _ in range(rng.randint(1, 3))
            ]

        if "LIMIT" in upper:
            # any other detail-fetch query (row-level WHERE ... LIMIT n)
            return [
                {"SAMPLE_KEY": rng.randint(1000, 9999)}
                for _ in range(rng.randint(1, 5))
            ]

        if "TOTAL_ROWS" not in upper and "FAILED_ROWS" not in upper:
            # scalar query, e.g. a RECON-style "SELECT COUNT(*) FROM ..."
            return [{"RESULT": rng.randint(40000, 46000)}]

        total = rng.randint(5000, 50000)
        failed = rng.randint(0, int(total * 0.03))
        return [{"TOTAL_ROWS": total, "FAILED_ROWS": failed}]

    def close_all(self):
        """No real resources to release -- present so callers can treat
        every SessionPort implementation the same way at shutdown."""
        if hasattr(self._local, "conn"):
            del self._local.conn


@register_session("mock")
def _build_mock_session():
    return MockSession()
