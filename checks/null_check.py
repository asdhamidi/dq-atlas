"""NULL check: flags rows where the target column is null."""
from core.registry import register
from core.sql_render import render, safe_identifier
from core.exec_helpers import execute_aggregate_check
from templates.default_templates import DEFAULT_TEMPLATES


@register("NULL")
def run(instance, session, run_id):
    sql = render(DEFAULT_TEMPLATES["NULL"]["aggregate"], {
        "table": instance.fq_table,
        "column": safe_identifier(instance.column),
    })
    return execute_aggregate_check(instance, session, run_id, sql)
