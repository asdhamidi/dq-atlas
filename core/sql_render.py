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


def _require_non_string_iterable(values: Any, what: str) -> list:
    """
    Guards against the classic Python gotcha where a config author sets a
    list-typed field (e.g. DUPLICATE_KEY_COLUMNS, ALLOWED_VALUES,
    ROW_IDENTIFIER_COLUMNS) to a plain string instead of a list. Strings are
    iterable, so `safe_identifier_list("ORDER_ID")` would silently iterate
    character-by-character and render one quoted single-letter "identifier"
    per character -- a confusing SQL error far from the actual mistake,
    instead of a clear error at the point of misconfiguration.
    """
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise ValueError(
            f"Expected a list of {what}, got {type(values).__name__}: {values!r}"
        )
    values = list(values)
    if not values:
        raise ValueError(f"Expected a non-empty list of {what}")
    return values


def safe_identifier(name: str) -> str:
    """Validates and double-quotes a single SQL identifier."""
    if not name or not isinstance(name, str) or not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Unsafe or invalid identifier: {name!r}")
    return f'"{name.upper()}"'


def safe_identifier_list(names: Iterable[str]) -> str:
    names = _require_non_string_iterable(names, "identifiers")
    return ", ".join(safe_identifier(n) for n in names)


def safe_fq_name(fq_name: str) -> str:
    """
    Validates and quotes a dot-separated fully-qualified name (e.g.
    DB.SCHEMA.TABLE), part by part. Used anywhere a config value stands in
    for a whole table reference (CheckInstance.fq_table, REFERENCE_TABLE)
    so those get the same injection-surface protection as a single column
    identifier does via safe_identifier -- previously these were
    interpolated raw on the theory that they're "admin-controlled," which
    is the same theory that applies to every other identifier here too.
    """
    if not fq_name or not isinstance(fq_name, str):
        raise ValueError(f"Unsafe or invalid fully-qualified name: {fq_name!r}")
    parts = fq_name.split(".")
    if any(not p for p in parts):
        raise ValueError(f"Unsafe or invalid fully-qualified name: {fq_name!r}")
    return ".".join(safe_identifier(p) for p in parts)


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
    values = _require_non_string_iterable(values, "literal values")
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
