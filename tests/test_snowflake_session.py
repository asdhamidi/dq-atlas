"""
snowflake.connector itself is not installed in this environment (it's an
optional extra, lazily imported only by get_connection() -- see the
module docstring in adapters/snowflake_session.py), so these tests only
exercise the parts that don't need it: env-var wiring and private-key
conversion. `cryptography` is a hard dependency of key-pair auth, so
those tests are skipped outright if it isn't installed.
"""
import pytest

cryptography = pytest.importorskip("cryptography")

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

from adapters.snowflake_session import SnowflakeSession


def _generate_pem(passphrase: bytes = None) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    encryption = (
        serialization.BestAvailableEncryption(passphrase) if passphrase else serialization.NoEncryption()
    )
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption,
    ), key


class TestLoadPrivateKey:
    def test_converts_unencrypted_pem_to_der_bytes(self):
        pem, original_key = _generate_pem()
        der_bytes = SnowflakeSession._load_private_key(pem.decode())

        assert isinstance(der_bytes, bytes)
        # Round-trips back into an equivalent key.
        reloaded = serialization.load_der_private_key(der_bytes, password=None, backend=default_backend())
        assert reloaded.private_numbers() == original_key.private_numbers()

    def test_converts_passphrase_protected_pem(self):
        pem, original_key = _generate_pem(passphrase=b"s3cret")
        der_bytes = SnowflakeSession._load_private_key(pem.decode(), passphrase="s3cret")

        reloaded = serialization.load_der_private_key(der_bytes, password=None, backend=default_backend())
        assert reloaded.private_numbers() == original_key.private_numbers()

    def test_wrong_passphrase_raises(self):
        pem, _ = _generate_pem(passphrase=b"s3cret")
        with pytest.raises(Exception):
            SnowflakeSession._load_private_key(pem.decode(), passphrase="wrong")

    def test_accepts_bytes_as_well_as_str(self):
        pem, original_key = _generate_pem()
        der_bytes = SnowflakeSession._load_private_key(pem)  # bytes, not decoded str
        reloaded = serialization.load_der_private_key(der_bytes, password=None, backend=default_backend())
        assert reloaded.private_numbers() == original_key.private_numbers()


class TestFromEnv:
    def test_password_auth_when_no_private_key_set(self, monkeypatch):
        monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "acct")
        monkeypatch.setenv("SNOWFLAKE_USER", "user")
        monkeypatch.setenv("SNOWFLAKE_PASSWORD", "pw")
        monkeypatch.delenv("SNOWFLAKE_PRIVATE_KEY", raising=False)

        params = SnowflakeSession._from_env()

        assert params["password"] == "pw"
        assert "private_key" not in params

    def test_key_pair_auth_when_private_key_set(self, monkeypatch):
        pem, original_key = _generate_pem()
        monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "acct")
        monkeypatch.setenv("SNOWFLAKE_USER", "user")
        monkeypatch.setenv("SNOWFLAKE_PRIVATE_KEY", pem.decode())
        monkeypatch.delenv("SNOWFLAKE_PASSWORD", raising=False)

        params = SnowflakeSession._from_env()

        assert isinstance(params["private_key"], bytes)
        assert "password" not in params
        reloaded = serialization.load_der_private_key(
            params["private_key"], password=None, backend=default_backend()
        )
        assert reloaded.private_numbers() == original_key.private_numbers()
