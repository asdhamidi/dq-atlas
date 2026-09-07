"""
Core data shapes shared across the DQ framework.

Every check function returns a CheckResult using the SAME shape, regardless
of check type. This is what lets the driver, logger, and registry stay
generic instead of special-casing each check type.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any

from core.sql_render import safe_fq_name


@dataclass
class CheckInstance:
    """
    One executable check, resolved from a DQ_CHECK_CONFIG row.

    A single config row can resolve into MULTIPLE CheckInstances (e.g. a
    row with both NULL_CHECK_ACTIVE and OUTLIER_SENSITIVITY populated
    yields two instances: one NULL, one OUTLIER_ZSCORE). See
    core.registry.resolve_check_instances.
    """
    check_id: str
    check_type: str                 # NULL, DUPLICATE, RANGE, TYPE, DATA_TYPE,
                                     # CHECKLIST, OUTLIER_ZSCORE, OUTLIER_IQR,
                                     # REF, RECON, CUSTOM
    database: str
    schema: str
    table: str
    column: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    threshold_type: str = "PERCENT"     # COUNT or PERCENT
    threshold_value: float = 0.0
    criticality: str = "WARN"           # CRITICAL, WARN, INFO
    check_status: str = "ACTIVE"        # DRAFT, SHADOW, ACTIVE, RETIRED
    schedule_group: str = "DAILY"
    row_identifier_columns: Optional[List[str]] = None

    @property
    def fq_table(self) -> str:
        # Validated/quoted via safe_fq_name rather than raw-interpolated --
        # DATABASE_NAME/SCHEMA_NAME/TABLE_NAME are admin-edited config, but
        # so is every column name, and those already go through
        # safe_identifier. This closes that inconsistency.
        return safe_fq_name(f"{self.database}.{self.schema}.{self.table}")


@dataclass
class CheckResult:
    """Uniform output shape for every check type. Maps directly onto DQ_RESULTS."""
    run_id: str
    check_id: str
    check_type: str
    status: str                           # SUCCESS or ERROR
    total_rows: Optional[int] = None
    failed_rows: Optional[int] = None
    fail_pct: Optional[float] = None
    threshold_type: Optional[str] = None
    threshold_value: Optional[float] = None
    pass_fail_flag: Optional[str] = None  # PASS or FAIL
    criticality: Optional[str] = None
    check_status_at_run: Optional[str] = None
    rendered_sql: Optional[str] = None
    sample_failed_keys: Optional[List[Dict[str, Any]]] = None
    error_message: Optional[str] = None
    execution_time_ms: Optional[int] = None
    executed_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RunSummary:
    """One row per orchestration batch. Maps onto DQ_RUN_LOG."""
    run_id: str
    schedule_group: Optional[str]
    batch_start: datetime
    batch_end: Optional[datetime] = None
    checks_attempted: int = 0
    checks_passed: int = 0
    checks_failed: int = 0
    checks_errored: int = 0
    overall_status: str = "SUCCESS"
