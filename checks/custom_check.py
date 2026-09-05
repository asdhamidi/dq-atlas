"""
CUSTOM checks run admin-authored SQL directly. The only requirement is that
the SQL aliases its output as TOTAL_ROWS and FAILED_ROWS -- same contract
as every other check. If the author forgets, this fails loudly (missing
key -> ERROR status via execute_aggregate_check) rather than silently
returning nothing, which is the failure mode that bit the original design
walkthrough (a CUSTOM check referencing a non-existent column).
"""
from core.registry import register
from core.exec_helpers import execute_aggregate_check


@register("CUSTOM")
def run(instance, session, run_id):
    sql = instance.params["custom_sql"]
    return execute_aggregate_check(instance, session, run_id, sql)
