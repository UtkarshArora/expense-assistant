import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# app.config reads ANTHROPIC_API_KEY at import time; the guard tests never
# call the API, so a placeholder is enough when no real key is set.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app import agent  # noqa: E402


@pytest.fixture
def fake_connect(monkeypatch):
    """Replace psycopg.connect so query_db never touches a real database.

    Returns the mock, so tests can assert whether the guard let a
    statement through (connect called) or stopped it (connect not called).
    """
    cursor = MagicMock()
    cursor.fetchmany.return_value = [(1,)]
    cursor.description = [SimpleNamespace(name="col")]

    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor

    connect = MagicMock()
    connect.return_value.__enter__.return_value = conn
    connect.cursor = cursor
    connect.conn = conn

    monkeypatch.setattr(agent.psycopg, "connect", connect)
    return connect
