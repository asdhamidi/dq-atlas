"""
Registry mapping a connection-type string to a factory that builds a
SessionPort-conforming adapter. This is the piece that was missing before:
main.py used to hardcode `SnowflakeSession()` directly, which meant the
warehouse choice was baked into an if/else rather than being config-driven.

Deliberately mirrors core.registry's CHECK_REGISTRY pattern -- a plain
dict, filled by a decorator, read by one lookup function -- so anyone
already familiar with how check types register themselves recognizes this
immediately.

Adding a new backend (Postgres, BigQuery, DuckDB, ...) means: write one
adapter module implementing SessionPort, decorate its factory with
@register_session("name"), and add it to the import list in
adapters/__init__.py. Nothing in core/ ever needs to change.
"""

from typing import Callable, Dict

SESSION_REGISTRY: Dict[str, Callable[[], object]] = {}


def register_session(connection_type: str):
    """Decorator: registers a zero-argument session factory under a name."""

    def wrapper(factory):
        SESSION_REGISTRY[connection_type] = factory
        return factory

    return wrapper


def build_session(connection_type: str):
    """Looks up and calls the factory for a connection type, or raises a
    clear error listing what's actually available -- this is the only
    place that needs to know the registry exists."""
    factory = SESSION_REGISTRY.get(connection_type)
    if factory is None:
        available = (
            ", ".join(sorted(SESSION_REGISTRY.keys()))
            or "(none registered -- did you `import adapters`?)"
        )
        raise ValueError(
            f"Unknown connection type '{connection_type}'. Available: {available}"
        )
    return factory()
