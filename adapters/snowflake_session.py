"""
Production adapter. One Snowflake session per worker thread -- the
Snowflake connector's cursor/connection objects are not safe to share
across concurrently-running threads. Import of snowflake.connector is
lazy so the rest of the framework can be imported and demoed without the
dependency installed.
"""

import os
import threading

from adapters.session_registry import register_session


class SnowflakeSession:
    def __init__(self, connection_params: dict = None):
        self._local = threading.local()
        self._connection_params = connection_params or self._from_env()

    @staticmethod
    def _load_private_key(pem_value, passphrase: str = None) -> bytes:
        """
        Converts a PEM-formatted private key (the natural shape for
        SNOWFLAKE_PRIVATE_KEY -- the literal contents of a .p8 file) into
        the DER-encoded PKCS8 bytes snowflake.connector.connect(...)
        actually expects for its `private_key` parameter. Passing the raw
        PEM string through unconverted -- the previous behavior -- looks
        plausible but fails against the real connector.
        """
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend

        pem_bytes = pem_value.encode() if isinstance(pem_value, str) else pem_value
        password = passphrase.encode() if passphrase else None
        p_key = serialization.load_pem_private_key(
            pem_bytes, password=password, backend=default_backend()
        )
        return p_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    @classmethod
    def _from_env(cls) -> dict:
        params = dict(
            account=os.environ["SNOWFLAKE_ACCOUNT"],
            user=os.environ["SNOWFLAKE_USER"],
            role=os.environ.get("SNOWFLAKE_ROLE"),
            warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE"),
            database=os.environ.get("SNOWFLAKE_DATABASE"),
        )
        private_key_pem = os.environ.get("SNOWFLAKE_PRIVATE_KEY")
        if private_key_pem:
            params["private_key"] = cls._load_private_key(
                private_key_pem, os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
            )
        else:
            params["password"] = os.environ.get("SNOWFLAKE_PASSWORD")
        return params

    def get_connection(self):
        if not hasattr(self._local, "conn"):
            import snowflake.connector  # lazy import -- not a hard dependency for demo mode

            self._local.conn = snowflake.connector.connect(**self._connection_params)
        return self._local.conn

    def execute(self, connection, sql: str):
        cursor = connection.cursor()
        try:
            cursor.execute(sql)
            columns = [c[0] for c in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def close_all(self):
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            del self._local.conn


@register_session("snowflake")
def _build_snowflake_session():
    return SnowflakeSession()
