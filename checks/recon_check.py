"""
RECON is the one check type that can't produce TOTAL_ROWS/FAILED_ROWS from
a single query -- it runs two independent statements (source vs target)
and compares them in Python. We still force the result into the same
CheckResult shape (TOTAL_ROWS=1, FAILED_ROWS=0-or-1) so the rest of the
pipeline -- logging, driver, alerting -- doesn't need a special case for it.
"""
import time
from core.registry import register
from core.models import CheckResult
from core.errors import CheckExecutionError
from core.evaluation import evaluate_pass_fail


@register("RECON")
def run(instance, session, run_id):
    source_sql = instance.params["source_sql"]
    target_sql = instance.params["target_sql"]
    combined_sql_for_log = f"-- SOURCE --\n{source_sql}\n-- TARGET --\n{target_sql}"

    start = time.perf_counter()
    try:
        conn = session.get_connection()
        source_rows = session.execute(conn, source_sql)
        target_rows = session.execute(conn, target_sql)
    except Exception as e:
        raise CheckExecutionError(str(e), rendered_sql=combined_sql_for_log, original=e)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    source_val = list(source_rows[0].values())[0]
    target_val = list(target_rows[0].values())[0]
    # abs() must wrap the whole ratio, not just the numerator -- otherwise
    # a negative source_val (e.g. RECON over a signed SUM, not just
    # COUNT(*)) can flip the sign of diff_pct and produce a false PASS
    # against a positive threshold regardless of how large the mismatch
    # actually is. A zero source_val is handled explicitly: any nonzero
    # target against a zero source is a total mismatch (100%), not the
    # "no data yet" 0.0 the old fallback silently reported.
    if source_val == 0:
        diff_pct = 0.0 if target_val == 0 else 100.0
    else:
        diff_pct = abs(source_val - target_val) / abs(source_val) * 100

    total_rows, failed_rows = 1, (1 if diff_pct > instance.threshold_value else 0)

    return CheckResult(
        run_id=run_id,
        check_id=instance.check_id,
        check_type="RECON",
        status="SUCCESS",
        total_rows=total_rows,
        failed_rows=failed_rows,
        fail_pct=round(diff_pct, 4),
        threshold_type="PERCENT",
        threshold_value=instance.threshold_value,
        pass_fail_flag=evaluate_pass_fail("PERCENT", instance.threshold_value, failed_rows, diff_pct),
        criticality=instance.criticality,
        check_status_at_run=instance.check_status,
        rendered_sql=combined_sql_for_log,
        execution_time_ms=elapsed_ms,
    )
