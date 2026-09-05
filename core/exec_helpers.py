"""
Shared helper for check functions to avoid repeating timing/execution/
result-shaping boilerplate. Each check function still owns its own SQL
construction -- this only centralizes what's genuinely identical across
the ~7 check types that reduce to "run one aggregate query, get back
TOTAL_ROWS/FAILED_ROWS."

RECON and CUSTOM don't call this: RECON needs two queries diffed in Python,
and CUSTOM's SQL already comes fully formed from config.
"""
import time
from core.models import CheckInstance, CheckResult
from core.errors import CheckExecutionError
from core.evaluation import evaluate_pass_fail, compute_fail_pct


def execute_aggregate_check(instance: CheckInstance, session, run_id: str, sql: str) -> CheckResult:
    start = time.perf_counter()
    try:
        conn = session.get_connection()
        rows = session.execute(conn, sql)
    except Exception as e:
        raise CheckExecutionError(str(e), rendered_sql=sql, original=e)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    total = rows[0]["TOTAL_ROWS"] if rows else 0
    failed = rows[0]["FAILED_ROWS"] if rows else 0
    fail_pct = compute_fail_pct(total, failed)

    return CheckResult(
        run_id=run_id,
        check_id=instance.check_id,
        check_type=instance.check_type,
        status="SUCCESS",
        total_rows=total,
        failed_rows=failed,
        fail_pct=fail_pct,
        threshold_type=instance.threshold_type,
        threshold_value=instance.threshold_value,
        pass_fail_flag=evaluate_pass_fail(instance.threshold_type, instance.threshold_value, failed, fail_pct),
        criticality=instance.criticality,
        check_status_at_run=instance.check_status,
        rendered_sql=sql,
        execution_time_ms=elapsed_ms,
    )
