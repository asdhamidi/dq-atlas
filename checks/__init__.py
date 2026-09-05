"""
Importing this package registers every check function against
core.registry.CHECK_REGISTRY via the @register decorator in each module.
Anything that does `import checks` before running the driver gets the
full registry populated -- no other wiring needed.
"""
from checks import (
    null_check,
    duplicate_check,
    range_check,
    type_check,
    data_type_check,
    checklist_check,
    outlier_check,
    ref_check,
    recon_check,
    custom_check,
)

__all__ = [
    "null_check", "duplicate_check", "range_check", "type_check",
    "data_type_check", "checklist_check", "outlier_check", "ref_check",
    "recon_check", "custom_check",
]
