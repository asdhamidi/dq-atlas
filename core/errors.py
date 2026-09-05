"""
Check functions raise on failure rather than catching internally -- the
driver is the single place that catches and converts an exception into an
ERROR CheckResult. This exception exists so that even on failure, whatever
SQL was rendered before the failure is preserved for debugging.
"""


class CheckExecutionError(Exception):
    def __init__(self, message: str, rendered_sql: str = None, original: Exception = None):
        super().__init__(message)
        self.rendered_sql = rendered_sql
        self.original = original
