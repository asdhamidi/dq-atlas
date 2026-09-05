"""DATA_TYPE check: flags schema drift by comparing INFORMATION_SCHEMA's
declared column type against the expected type. Unlike every other check,
this reads metadata, not table rows -- but it still returns the same
TOTAL_ROWS=1 / FAILED_ROWS=0-or-1 shape so it fits the uniform contract."""
from core.registry import register
from core.sql_render import render, safe_literal
from core.exec_helpers import execute_aggregate_check
from templates.default_templates import DEFAULT_TEMPLATES


@register("DATA_TYPE")
def run(instance, session, run_id):
    sql = render(DEFAULT_TEMPLATES["DATA_TYPE"]["aggregate"], {
        "database": instance.database,
        "schema_lit": safe_literal(instance.schema.upper()),
        "table_lit": safe_literal(instance.table.upper()),
        "column_lit": safe_literal(instance.column.upper()),
        "expected_data_type": safe_literal(instance.params["expected_data_type"]),
    })
    return execute_aggregate_check(instance, session, run_id, sql)
