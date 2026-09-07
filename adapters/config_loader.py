"""
Loads DQ_CHECK_CONFIG rows via a generic SQL query executed through
whatever SessionPort it's given. In production that's a real database
(Snowflake, SQLite, whatever build_session() constructed); in demo mode
it's swapped for DemoConfigLoader, which filters an in-memory list
instead. Both satisfy ConfigLoaderPort, so driver.py works unchanged
against either.

Named generically (not "Snowflake...") because there's nothing
warehouse-specific in the query below -- plain ANSI SELECT/WHERE. It
works against SQLite, Postgres, or anything else a SessionPort wraps.
"""

from typing import List, Dict, Any, Optional

from core.sql_render import safe_literal


class SqlConfigLoader:
    def __init__(self, session, config_table_fqn: str):
        self.session = session
        self.config_table_fqn = config_table_fqn

    def load_config_rows(
        self,
        check_id: Optional[str] = None,
        table_name: Optional[str] = None,
        schedule_group: Optional[str] = None,
        run_all: bool = False,
    ) -> List[Dict[str, Any]]:
        if not (check_id or table_name or schedule_group or run_all):
            raise ValueError(
                "Specify check_id, table_name, schedule_group, or run_all=True"
            )

        # check_id/table_name/schedule_group come from CLI flags, i.e. from
        # whoever is invoking the run -- less trusted than the config table
        # itself, so these go through safe_literal like every other
        # rendered value in the framework rather than being f-string'd in
        # raw (a stray quote used to be enough to break out of the WHERE
        # clause).
        where = ["CHECK_STATUS IN ('ACTIVE', 'SHADOW')"]
        if check_id:
            where.append(f"CHECK_ID = {safe_literal(check_id)}")
        if table_name:
            where.append(f"TABLE_NAME = {safe_literal(table_name)}")
        if schedule_group:
            where.append(f"SCHEDULE_GROUP = {safe_literal(schedule_group)}")

        sql = f"SELECT * FROM {self.config_table_fqn} WHERE {' AND '.join(where)}"
        conn = self.session.get_connection()
        return self.session.execute(conn, sql)


class DemoConfigLoader:
    def __init__(self, rows: List[Dict[str, Any]]):
        self._rows = rows

    def load_config_rows(
        self,
        check_id: Optional[str] = None,
        table_name: Optional[str] = None,
        schedule_group: Optional[str] = None,
        run_all: bool = False,
    ) -> List[Dict[str, Any]]:
        if not (check_id or table_name or schedule_group or run_all):
            raise ValueError(
                "Specify check_id, table_name, schedule_group, or run_all=True"
            )

        # Filters AND together, matching SqlConfigLoader -- previously this
        # was an if/elif chain, so passing e.g. both check_id and
        # table_name silently ignored table_name here while the SQL loader
        # applied both. Demo mode is meant to be a faithful stand-in for
        # exercising CLI filter combinations before pointing at a real
        # backend, so the two must filter identically.
        rows = [
            r
            for r in self._rows
            if r.get("CHECK_STATUS", "ACTIVE") in ("ACTIVE", "SHADOW")
        ]
        if check_id:
            rows = [r for r in rows if r["CHECK_ID"] == check_id]
        if table_name:
            rows = [r for r in rows if r["TABLE_NAME"] == table_name]
        if schedule_group:
            rows = [r for r in rows if r.get("SCHEDULE_GROUP") == schedule_group]
        return rows
