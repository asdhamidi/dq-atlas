"""CHECKLIST check: flags values not present in an allowed-values list
(e.g. ORDER_STATUS must be one of OPEN/CLOSED/PENDING/CANCELLED)."""
from core.registry import register
from core.sql_render import render, safe_identifier, safe_literal_list
from core.exec_helpers import execute_aggregate_check
from templates.default_templates import DEFAULT_TEMPLATES


@register("CHECKLIST")
def run(instance, session, run_id):
    sql = render(DEFAULT_TEMPLATES["CHECKLIST"]["aggregate"], {
        "table": instance.fq_table,
        "column": safe_identifier(instance.column),
        "allowed_values": safe_literal_list(instance.params["allowed_values"]),
    })
    return execute_aggregate_check(instance, session, run_id, sql)
