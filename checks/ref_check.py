"""REF check: flags rows whose foreign key has no matching row in the
reference table (orphans), via a LEFT JOIN + NULL check."""
from core.registry import register
from core.sql_render import render, safe_identifier
from core.exec_helpers import execute_aggregate_check
from templates.default_templates import DEFAULT_TEMPLATES


@register("REF")
def run(instance, session, run_id):
    p = instance.params
    sql = render(DEFAULT_TEMPLATES["REF"]["aggregate"], {
        "table": instance.fq_table,
        "column": safe_identifier(instance.column),
        "reference_table": p["reference_table"],  # already fully-qualified, admin-controlled
        "reference_column": safe_identifier(p["reference_column"]),
    })
    return execute_aggregate_check(instance, session, run_id, sql)
