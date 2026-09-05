"""OUTLIER checks: z-score and IQR are genuinely different SQL shapes, not
just a parameter of one check -- so they're two registered check types,
selected via OUTLIER_TEMPLATE_ID in config, both sharing this module."""
from core.registry import register
from core.sql_render import render, safe_identifier, safe_literal
from core.exec_helpers import execute_aggregate_check
from templates.default_templates import DEFAULT_TEMPLATES


def _run_outlier(method_key, instance, session, run_id):
    sql = render(DEFAULT_TEMPLATES[method_key]["aggregate"], {
        "table": instance.fq_table,
        "column": safe_identifier(instance.column),
        "sensitivity": safe_literal(instance.params["sensitivity"]),
    })
    return execute_aggregate_check(instance, session, run_id, sql)


@register("OUTLIER_ZSCORE")
def run_zscore(instance, session, run_id):
    return _run_outlier("OUTLIER_ZSCORE", instance, session, run_id)


@register("OUTLIER_IQR")
def run_iqr(instance, session, run_id):
    return _run_outlier("OUTLIER_IQR", instance, session, run_id)
