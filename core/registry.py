"""
Registry: maps CHECK_TYPE -> check function, and resolves a raw
DQ_CHECK_CONFIG row into one or more CheckInstance objects.

This module is the one place that knows "which populated columns imply
which check type." Keeping that logic centralized means adding a new
check type later means adding one branch here plus one new file in
checks/ -- the driver itself never needs to change.
"""
from typing import Callable, Dict, List
from core.models import CheckInstance

CHECK_REGISTRY: Dict[str, Callable] = {}


def register(check_type: str):
    """Decorator: registers a check function against a CHECK_TYPE key."""
    def wrapper(fn):
        CHECK_REGISTRY[check_type] = fn
        return fn
    return wrapper


def _base_kwargs(row: dict) -> dict:
    return dict(
        check_id=row["CHECK_ID"],
        database=row["DATABASE_NAME"],
        schema=row["SCHEMA_NAME"],
        table=row["TABLE_NAME"],
        criticality=row.get("CRITICALITY", "WARN"),
        check_status=row.get("CHECK_STATUS", "ACTIVE"),
        schedule_group=row.get("SCHEDULE_GROUP", "DAILY"),
        row_identifier_columns=row.get("ROW_IDENTIFIER_COLUMNS"),
    )


def resolve_check_instances(row: dict) -> List[CheckInstance]:
    """
    Explodes one config row into every active check family it declares.
    A row with NULL_CHECK_ACTIVE=True and LOWER_BOUND/UPPER_BOUND populated
    yields two CheckInstances: one NULL, one RANGE.
    """
    instances: List[CheckInstance] = []

    if row.get("NULL_CHECK_ACTIVE"):
        instances.append(CheckInstance(
            **_base_kwargs(row),
            check_type="NULL",
            column=row["COLUMN_NAME"],
            threshold_type=row.get("NULL_THRESHOLD_TYPE", "COUNT"),
            threshold_value=row.get("NULL_THRESHOLD", 0),
        ))

    if row.get("DUPLICATE_KEY_COLUMNS"):
        instances.append(CheckInstance(
            **_base_kwargs(row),
            check_type="DUPLICATE",
            params={"key_columns": row["DUPLICATE_KEY_COLUMNS"]},
            threshold_type=row.get("DUPLICATE_THRESHOLD_TYPE", "COUNT"),
            threshold_value=row.get("DUPLICATE_THRESHOLD", 0),
        ))

    if row.get("LOWER_BOUND") is not None or row.get("UPPER_BOUND") is not None:
        instances.append(CheckInstance(
            **_base_kwargs(row),
            check_type="RANGE",
            column=row["COLUMN_NAME"],
            params={"lower_bound": row.get("LOWER_BOUND"), "upper_bound": row.get("UPPER_BOUND")},
            threshold_type=row.get("RANGE_THRESHOLD_TYPE", "PERCENT"),
            threshold_value=row.get("RANGE_THRESHOLD", 0),
        ))

    if row.get("REGEX_PATTERN"):
        instances.append(CheckInstance(
            **_base_kwargs(row),
            check_type="TYPE",
            column=row["COLUMN_NAME"],
            params={"regex_pattern": row["REGEX_PATTERN"]},
            threshold_type=row.get("TYPE_THRESHOLD_TYPE", "PERCENT"),
            threshold_value=row.get("TYPE_THRESHOLD", 0),
        ))

    if row.get("EXPECTED_DATA_TYPE"):
        instances.append(CheckInstance(
            **_base_kwargs(row),
            check_type="DATA_TYPE",
            column=row["COLUMN_NAME"],
            params={"expected_data_type": row["EXPECTED_DATA_TYPE"]},
            threshold_type="COUNT",
            threshold_value=0,
        ))

    if row.get("ALLOWED_VALUES"):
        instances.append(CheckInstance(
            **_base_kwargs(row),
            check_type="CHECKLIST",
            column=row["COLUMN_NAME"],
            params={"allowed_values": row["ALLOWED_VALUES"]},
            threshold_type=row.get("CHECKLIST_THRESHOLD_TYPE", "PERCENT"),
            threshold_value=row.get("CHECKLIST_THRESHOLD", 0),
        ))

    if row.get("OUTLIER_SENSITIVITY") is not None:
        # OUTLIER_TEMPLATE_ID picks the method (ZSCORE vs IQR); the method
        # itself IS the dispatch key into CHECK_REGISTRY, since z-score and
        # IQR are genuinely different SQL shapes, not just a parameter.
        method = row.get("OUTLIER_TEMPLATE_ID", "OUTLIER_ZSCORE")
        instances.append(CheckInstance(
            **_base_kwargs(row),
            check_type=method,
            column=row["COLUMN_NAME"],
            params={"sensitivity": row["OUTLIER_SENSITIVITY"]},
            threshold_type=row.get("OUTLIER_THRESHOLD_TYPE", "PERCENT"),
            threshold_value=row.get("OUTLIER_THRESHOLD", 0),
        ))

    if row.get("REFERENCE_TABLE"):
        instances.append(CheckInstance(
            **_base_kwargs(row),
            check_type="REF",
            column=row["COLUMN_NAME"],
            params={
                "reference_table": row["REFERENCE_TABLE"],
                "reference_column": row["REFERENCE_COLUMN"],
            },
            threshold_type=row.get("REF_THRESHOLD_TYPE", "COUNT"),
            threshold_value=row.get("REF_THRESHOLD", 0),
        ))

    if row.get("RECON_SOURCE_SQL"):
        instances.append(CheckInstance(
            **_base_kwargs(row),
            check_type="RECON",
            params={
                "source_sql": row["RECON_SOURCE_SQL"],
                "target_sql": row["RECON_TARGET_SQL"],
            },
            threshold_type="PERCENT",
            threshold_value=row.get("RECON_TOLERANCE_PCT", 0),
        ))

    if row.get("CUSTOM_SQL"):
        instances.append(CheckInstance(
            **_base_kwargs(row),
            check_type="CUSTOM",
            params={"custom_sql": row["CUSTOM_SQL"]},
            threshold_type=row.get("CUSTOM_THRESHOLD_TYPE", "COUNT"),
            threshold_value=row.get("CUSTOM_THRESHOLD", 0),
        ))

    return instances
