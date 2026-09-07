"""
Ports (interfaces) that the driver depends on. Adapters implement these.

This is the seam that makes the engine swappable: a Snowflake adapter and a
mock/demo adapter both satisfy the same ports, so driver.py never changes
when the backend does, and a new check type is just a new function
registered against CHECK_REGISTRY -- the driver doesn't change for that
either.
"""
from typing import Protocol, List, Dict, Any, Optional, Callable


class SessionPort(Protocol):
    """Provides a DB-API-style connection. One session per worker thread."""

    def get_connection(self):
        ...

    def execute(self, connection, sql: str) -> List[Dict[str, Any]]:
        """Runs a SQL statement and returns rows as a list of dicts."""
        ...

    def close_all(self) -> None:
        """Releases every per-thread connection this session opened.
        Called once by the CLI after a run completes. Every built-in
        adapter (Snowflake, SQLite, mock) implements this."""
        ...


class ResultLoggerPort(Protocol):
    def log_results(self, results: list) -> None:
        ...

    def log_run_summary(self, summary) -> None:
        ...


class RecordFetcherPort(Protocol):
    def fetch_failed_records(self, instance, limit: int = 20) -> Optional[List[Dict[str, Any]]]:
        ...


class ConfigLoaderPort(Protocol):
    def load_config_rows(
        self,
        check_id: Optional[str] = None,
        table_name: Optional[str] = None,
        schedule_group: Optional[str] = None,
        run_all: bool = False,
    ) -> List[Dict[str, Any]]:
        ...


# A check function's signature -- every module in checks/ implements this.
CheckFunction = Callable[..., Any]
