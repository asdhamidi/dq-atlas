"""DUPLICATE check: flags rows beyond the first occurrence of a key (single
or composite -- DUPLICATE_KEY_COLUMNS is always an array)."""
from core.registry import register
from core.sql_render import render, safe_identifier_list
from core.exec_helpers import execute_aggregate_check
from templates.default_templates import DEFAULT_TEMPLATES


@register("DUPLICATE")
def run(instance, session, run_id):
    key_cols = safe_identifier_list(instance.params["key_columns"])
    sql = render(DEFAULT_TEMPLATES["DUPLICATE"]["aggregate"], {
        "table": instance.fq_table,
        "key_cols": key_cols,
    })
    return execute_aggregate_check(instance, session, run_id, sql)
