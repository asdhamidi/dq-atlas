"""
Importing this package registers every session backend against
adapters.session_registry.SESSION_REGISTRY via the @register_session
decorator in each module -- same trigger mechanism as checks/__init__.py
uses for CHECK_REGISTRY. `main.py` does `import adapters` before calling
build_session(), so the registry is populated before it's ever read.
"""

from adapters import snowflake_session, mock_session, sqlite_session

__all__ = ["snowflake_session", "mock_session", "sqlite_session"]
