"""
Shared predicate builders used by both a check function and the record
fetcher, for check types whose WHERE-clause logic must stay identical
between the aggregate count and the row-level detail query. Centralizing
this avoids the two queries drifting out of sync over time.
"""
from core.sql_render import safe_literal


def build_range_predicate(column: str, lower_bound, upper_bound) -> str:
    conditions = []
    if lower_bound is not None:
        conditions.append(f"{column} < {safe_literal(lower_bound)}")
    if upper_bound is not None:
        conditions.append(f"{column} > {safe_literal(upper_bound)}")
    return " OR ".join(conditions) if conditions else "FALSE"
