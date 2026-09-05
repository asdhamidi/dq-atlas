"""
Safe-ish SQL templating for config-driven checks.

Config rows are admin-edited, not end-user-facing, but we still validate
identifiers to catch typos early and reduce injection surface -- a bad
value here should fail loudly at render time, not run silently against
the warehouse.
"""
import re
from typing import Any, Iterable

_IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_$]*$')


def safe_identifier(name: str) -> str:
    """Validates and double-quotes a single SQL identifier."""
    if not name or not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Unsafe or invalid identifier: {name!r}")
    return f'"{name.upper()}"'


def safe_identifier_list(names: Iterable[str]) -> str:
    return ", ".join(safe_identifier(n) for n in names)


def safe_literal(value: Any) -> str:
    """Renders a Python value as a SQL literal."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def safe_literal_list(values: Iterable[Any]) -> str:
    return ", ".join(safe_literal(v) for v in values)


def render(template: str, context: dict) -> str:
    """
    Fills {PLACEHOLDER} tokens in a template using context.
    Context values are expected to already be render-safe (produced by
    safe_identifier / safe_literal by the caller) -- this function only
    substitutes, it does not escape anything itself.
    """
    try:
        return template.format(**context)
    except KeyError as e:
        raise ValueError(f"Template references missing placeholder: {e}")
