"""RANGE check: flags values outside [LOWER_BOUND, UPPER_BOUND]. Either
bound may be absent (one-sided range) -- build_range_predicate handles that
without resorting to +/-inf literals, which Snowflake SQL can't accept."""
from core.registry import register
from core.sql_render import render, safe_identifier
from core.exec_helpers import execute_aggregate_check
from core.predicates import build_range_predicate
from templates.default_templates import DEFAULT_TEMPLATES


@register("RANGE")
def run(instance, session, run_id):
    p = instance.params
    column = safe_identifier(instance.column)
    predicate = build_range_predicate(column, p.get("lower_bound"), p.get("upper_bound"))
    sql = render(DEFAULT_TEMPLATES["RANGE"]["aggregate"], {
        "table": instance.fq_table,
        "range_predicate": predicate,
    })
    return execute_aggregate_check(instance, session, run_id, sql)
