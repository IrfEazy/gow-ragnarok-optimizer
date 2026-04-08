"""E2E test configuration.

Overrides the top-level conftest's autouse fixture to avoid conflicts
with the session-scoped Flask server started by test_e2e.py.
"""

import pytest


@pytest.fixture(autouse=True)
def protect_config_yaml():
    """No-op override of the parent conftest's autouse fixture.

    The E2E tests manage their own config paths via the _app_server
    session-scoped fixture, so the parent's monkeypatch-based protection
    is unnecessary and would conflict with the running server thread.
    """
    yield
