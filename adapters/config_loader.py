"""
Loads DQ_CHECK_CONFIG rows. In production this queries Snowflake directly;
in demo mode it filters an in-memory list. Both satisfy ConfigLoaderPort,
so driver.py works unchanged against either.
"""
from typing import List, Dict, Any, Optional


class SnowflakeConfigLoader:
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
            raise ValueError("Specify check_id, table_name, schedule_group, or run_all=True")

        where = ["CHECK_STATUS IN ('ACTIVE', 'SHADOW')"]
        if check_id:
            where.append(f"CHECK_ID = '{check_id}'")
        if table_name:
            where.append(f"TABLE_NAME = '{table_name}'")
        if schedule_group:
            where.append(f"SCHEDULE_GROUP = '{schedule_group}'")

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
        rows = [r for r in self._rows if r.get("CHECK_STATUS", "ACTIVE") in ("ACTIVE", "SHADOW")]
        if check_id:
            rows = [r for r in rows if r["CHECK_ID"] == check_id]
        elif table_name:
            rows = [r for r in rows if r["TABLE_NAME"] == table_name]
        elif schedule_group:
            rows = [r for r in rows if r.get("SCHEDULE_GROUP") == schedule_group]
        elif not run_all:
            raise ValueError("Specify check_id, table_name, schedule_group, or run_all=True")
        return rows
