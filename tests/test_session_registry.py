import pytest

from adapters.session_registry import SESSION_REGISTRY, register_session, build_session


def test_builtin_backends_are_registered():
    # adapters/__init__.py (imported by conftest) registers all three.
    assert {"snowflake", "sqlite", "mock"} <= set(SESSION_REGISTRY.keys())


def test_build_session_dispatches_to_factory():
    try:
        @register_session("TEST_ONLY_BACKEND")
        def factory():
            return "sentinel-session"

        assert build_session("TEST_ONLY_BACKEND") == "sentinel-session"
    finally:
        SESSION_REGISTRY.pop("TEST_ONLY_BACKEND", None)


def test_unknown_backend_raises_with_available_list():
    with pytest.raises(ValueError, match="mock"):
        build_session("not_a_real_backend")
