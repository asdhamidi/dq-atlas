"""Shared pass/fail evaluation logic, reused across every check type so the
COUNT vs PERCENT threshold semantics stay in exactly one place."""
from typing import Optional


def compute_fail_pct(total_rows: Optional[int], failed_rows: Optional[int]) -> float:
    if not total_rows:
        return 0.0
    return round((failed_rows / total_rows) * 100, 4)


def evaluate_pass_fail(
    threshold_type: str, threshold_value: float, failed_rows: Optional[int], fail_pct: Optional[float]
) -> Optional[str]:
    if failed_rows is None:
        return None
    metric = failed_rows if threshold_type == "COUNT" else (fail_pct or 0.0)
    return "PASS" if metric <= threshold_value else "FAIL"
