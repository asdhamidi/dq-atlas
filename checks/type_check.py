"""TYPE check: flags values that don't match a regex format pattern
(e.g. email, phone number formatting)."""
from core.registry import register
from core.sql_render import render, safe_identifier, safe_literal
from core.exec_helpers import execute_aggregate_check
from templates.default_templates import DEFAULT_TEMPLATES


@register("TYPE")
def run(instance, session, run_id):
    sql = render(DEFAULT_TEMPLATES["TYPE"]["aggregate"], {
        "table": instance.fq_table,
        "column": safe_identifier(instance.column),
        "regex_pattern": safe_literal(instance.params["regex_pattern"]),
    })
    return execute_aggregate_check(instance, session, run_id, sql)
