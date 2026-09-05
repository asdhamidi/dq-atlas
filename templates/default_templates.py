"""
Fallback templates, keyed by CHECK_TYPE. In production these mirror rows in
DQ_TEMPLATES; this module doubles as the seed data and as the default used
by check functions. Each entry has an "aggregate" template (always run) and
a "detail" template (only run when FAILED_ROWS > 0, to fetch sample keys).
A detail value of None means that check type has no meaningful row-level
detail to show (metadata checks, scalar comparisons).
"""

DEFAULT_TEMPLATES = {
    "NULL": {
        "aggregate": (
            "SELECT COUNT(*) AS TOTAL_ROWS, "
            "COUNT_IF({column} IS NULL) AS FAILED_ROWS "
            "FROM {table}"
        ),
        "detail": (
            "SELECT {row_id_cols} FROM {table} "
            "WHERE {column} IS NULL LIMIT {limit}"
        ),
    },
    "DUPLICATE": {
        "aggregate": (
            "WITH dq_dupes AS ("
            "SELECT {key_cols}, COUNT(*) AS cnt FROM {table} "
            "GROUP BY {key_cols}) "
            "SELECT (SELECT COUNT(*) FROM {table}) AS TOTAL_ROWS, "
            "COALESCE(SUM(IFF(cnt > 1, cnt - 1, 0)), 0) AS FAILED_ROWS "
            "FROM dq_dupes"
        ),
        "detail": (
            "SELECT {key_cols}, COUNT(*) AS OCCURRENCE_COUNT FROM {table} "
            "GROUP BY {key_cols} HAVING COUNT(*) > 1 LIMIT {limit}"
        ),
    },
    "RANGE": {
        "aggregate": (
            "SELECT COUNT(*) AS TOTAL_ROWS, "
            "COUNT_IF({range_predicate}) AS FAILED_ROWS "
            "FROM {table}"
        ),
        "detail": (
            "SELECT {row_id_cols}, {column} FROM {table} "
            "WHERE {range_predicate} LIMIT {limit}"
        ),
    },
    "TYPE": {
        "aggregate": (
            "SELECT COUNT(*) AS TOTAL_ROWS, "
            "COUNT_IF(NOT RLIKE({column}, {regex_pattern})) AS FAILED_ROWS "
            "FROM {table}"
        ),
        "detail": (
            "SELECT {row_id_cols}, {column} FROM {table} "
            "WHERE NOT RLIKE({column}, {regex_pattern}) LIMIT {limit}"
        ),
    },
    "DATA_TYPE": {
        "aggregate": (
            "SELECT 1 AS TOTAL_ROWS, "
            "IFF(DATA_TYPE != {expected_data_type}, 1, 0) AS FAILED_ROWS "
            "FROM {database}.INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = {schema_lit} AND TABLE_NAME = {table_lit} "
            "AND COLUMN_NAME = {column_lit}"
        ),
        "detail": None,  # metadata check -- no row-level detail applies
    },
    "CHECKLIST": {
        "aggregate": (
            "SELECT COUNT(*) AS TOTAL_ROWS, "
            "COUNT_IF({column} NOT IN ({allowed_values})) AS FAILED_ROWS "
            "FROM {table}"
        ),
        "detail": (
            "SELECT {row_id_cols}, {column} FROM {table} "
            "WHERE {column} NOT IN ({allowed_values}) LIMIT {limit}"
        ),
    },
    "OUTLIER_ZSCORE": {
        "aggregate": (
            "WITH dq_stats AS (SELECT AVG({column}) AS m, STDDEV({column}) AS sd FROM {table}) "
            "SELECT COUNT(*) AS TOTAL_ROWS, "
            "COUNT_IF(ABS(t.{column} - s.m) > {sensitivity} * s.sd) AS FAILED_ROWS "
            "FROM {table} t, dq_stats s"
        ),
        "detail": (
            "WITH dq_stats AS (SELECT AVG({column}) AS m, STDDEV({column}) AS sd FROM {table}) "
            "SELECT {row_id_cols}, t.{column} FROM {table} t, dq_stats s "
            "WHERE ABS(t.{column} - s.m) > {sensitivity} * s.sd LIMIT {limit}"
        ),
    },
    "OUTLIER_IQR": {
        "aggregate": (
            "WITH dq_stats AS ("
            "SELECT PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY {column}) AS q1, "
            "PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY {column}) AS q3 FROM {table}) "
            "SELECT COUNT(*) AS TOTAL_ROWS, "
            "COUNT_IF(t.{column} < s.q1 - {sensitivity} * (s.q3 - s.q1) "
            "OR t.{column} > s.q3 + {sensitivity} * (s.q3 - s.q1)) AS FAILED_ROWS "
            "FROM {table} t, dq_stats s"
        ),
        "detail": None,
    },
    "REF": {
        "aggregate": (
            "SELECT COUNT(*) AS TOTAL_ROWS, "
            "COUNT_IF(r.{reference_column} IS NULL) AS FAILED_ROWS "
            "FROM {table} t LEFT JOIN {reference_table} r "
            "ON t.{column} = r.{reference_column}"
        ),
        "detail": (
            "SELECT {row_id_cols_t}, t.{column} FROM {table} t LEFT JOIN {reference_table} r "
            "ON t.{column} = r.{reference_column} "
            "WHERE r.{reference_column} IS NULL LIMIT {limit}"
        ),
    },
    # RECON and CUSTOM are executed directly from config-provided SQL, not
    # rendered from a template here -- see checks/recon_check.py and
    # checks/custom_check.py.
}
