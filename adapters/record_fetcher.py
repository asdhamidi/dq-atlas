"""
RecordFetcher: only invoked by the driver when a check has FAILED_ROWS > 0,
and only for check types that have a meaningful row-level DETAIL template.
Kept separate from the check functions so the common case (aggregate check,
zero failures) never pays for a second query.
"""
from typing import Optional, List, Dict, Any
from core.sql_render import render, safe_identifier_list, safe_identifier, safe_literal, safe_literal_list, safe_fq_name
from core.predicates import build_range_predicate
from templates.default_templates import DEFAULT_TEMPLATES

# Check types with no meaningful row-level detail (metadata or scalar checks).
_NO_DETAIL = {"DATA_TYPE", "RECON", "CUSTOM", "OUTLIER_IQR"}


class RecordFetcher:
    def __init__(self, session):
        self.session = session

    def fetch_failed_records(self, instance, limit: int = 20) -> Optional[List[Dict[str, Any]]]:
        if instance.check_type in _NO_DETAIL:
            return None
        if not instance.row_identifier_columns:
            return None  # can't identify individual rows without a configured natural key

        template_entry = DEFAULT_TEMPLATES.get(instance.check_type)
        if not template_entry or not template_entry.get("detail"):
            return None

        context = {
            "table": instance.fq_table,
            "row_id_cols": safe_identifier_list(instance.row_identifier_columns),
            "row_id_cols_t": ", ".join(f"t.{safe_identifier(c)}" for c in instance.row_identifier_columns),
            "limit": limit,
        }
        context.update(self._check_specific_context(instance))

        sql = render(template_entry["detail"], context)
        conn = self.session.get_connection()
        return self.session.execute(conn, sql)

    @staticmethod
    def _check_specific_context(instance) -> dict:
        p = instance.params
        ctx = {}
        if instance.column:
            ctx["column"] = safe_identifier(instance.column)

        if instance.check_type == "RANGE":
            ctx["range_predicate"] = build_range_predicate(
                ctx["column"], p.get("lower_bound"), p.get("upper_bound")
            )
        elif instance.check_type == "TYPE":
            ctx["regex_pattern"] = safe_literal(p["regex_pattern"])
        elif instance.check_type == "CHECKLIST":
            ctx["allowed_values"] = safe_literal_list(p["allowed_values"])
        elif instance.check_type == "DUPLICATE":
            ctx["key_cols"] = safe_identifier_list(p["key_columns"])
        elif instance.check_type == "OUTLIER_ZSCORE":
            ctx["sensitivity"] = safe_literal(p["sensitivity"])
        elif instance.check_type == "REF":
            ctx["reference_table"] = safe_fq_name(p["reference_table"])
            ctx["reference_column"] = safe_identifier(p["reference_column"])

        return ctx
