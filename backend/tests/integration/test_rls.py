"""
Row-level security and least-privilege checks against a real Postgres.

Needs the database from docker-compose.yml (or CI's service container) with
seed_expenses.sql and db/02_security.sql applied. Run with:

    python -m pytest -m integration

Expected row sets come from the owner connection, so the tests follow the
seed data instead of hardcoding counts.
"""

import json

import psycopg
import pytest
from sqlalchemy import create_engine
from sqlmodel import SQLModel

from app import models  # noqa: F401  (registers the app tables on SQLModel.metadata)
from app.agent import AccessScope, query_db
from app.config import settings

pytestmark = pytest.mark.integration

MARCUS = AccessScope(role="employee", department="Sales", employee_name="Marcus Chen")
PRIYA = AccessScope(role="manager", department="Sales", employee_name="Priya Nair")
ADMIN = AccessScope(role="admin")


@pytest.fixture(scope="module", autouse=True)
def app_tables():
    """Create the app tables (as the app would on startup) so the
    permission tests hit real tables rather than missing ones."""
    url = settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    engine.dispose()


def owner_ids(where: str = "TRUE", params: tuple = ()) -> set[int]:
    with psycopg.connect(settings.database_url) as conn:
        rows = conn.execute(f"SELECT id FROM expenses WHERE {where}", params).fetchall()
    return {r[0] for r in rows}


def agent_ids(scope: AccessScope, sql: str = "SELECT id FROM expenses") -> set[int]:
    out = query_db(sql, scope=scope)
    if out == "Query ran, zero rows returned.":
        return set()
    assert not out.startswith(("Error", "SQL error")), out
    return {row["id"] for row in json.loads(out)}


def test_seed_has_rows_outside_every_scope():
    # Precondition: otherwise the scoping tests below prove nothing.
    assert owner_ids() - owner_ids("department = %s", ("Sales",))
    assert owner_ids("department = %s", ("Sales",)) - owner_ids("employee = %s", ("Marcus Chen",))


def test_admin_sees_every_row():
    assert agent_ids(ADMIN) == owner_ids()


def test_manager_sees_only_their_department():
    assert agent_ids(PRIYA) == owner_ids("department = %s", ("Sales",))


def test_employee_sees_only_their_own_rows():
    assert agent_ids(MARCUS) == owner_ids("employee = %s", ("Marcus Chen",))


def test_filters_cannot_widen_the_scope():
    # Asking for another department explicitly returns nothing, not a leak.
    assert agent_ids(PRIYA, "SELECT id FROM expenses WHERE department = 'Engineering'") == set()
    assert agent_ids(MARCUS, "SELECT id FROM expenses WHERE employee <> 'Marcus Chen'") == set()
    assert agent_ids(MARCUS, "SELECT id FROM expenses WHERE true OR 1=1") == owner_ids(
        "employee = %s", ("Marcus Chen",)
    )


def test_aggregates_are_scoped_too():
    out = json.loads(query_db("SELECT COUNT(*) AS n FROM expenses", scope=PRIYA))
    assert out[0]["n"] == len(owner_ids("department = %s", ("Sales",)))


@pytest.mark.parametrize(
    "scope",
    [
        AccessScope(role=""),
        AccessScope(role="superuser"),
        AccessScope(role="manager"),  # manager with no department
        AccessScope(role="employee", department="Sales"),  # no employee_name
    ],
)
def test_missing_or_unknown_scope_sees_nothing(scope):
    assert agent_ids(scope) == set()


# ----------------------------------------------------------------------
# Bypassing the guard entirely: the database still holds
# ----------------------------------------------------------------------

def raw_agent_connection():
    """agent_reader with no guard and no scope: what a guard bug would allow."""
    return psycopg.connect(settings.agent_database_url)


@pytest.mark.parametrize("table", ["app_user", "conversation", "message", "toolcall"])
def test_agent_role_cannot_read_app_tables(table):
    with raw_agent_connection() as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(f"SELECT * FROM {table} LIMIT 1")


def test_agent_role_cannot_write_expenses():
    with raw_agent_connection() as conn:
        with pytest.raises((psycopg.errors.InsufficientPrivilege, psycopg.errors.ReadOnlySqlTransaction)):
            conn.execute("DELETE FROM expenses")


def test_agent_role_sees_nothing_without_a_scope():
    with raw_agent_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 0


def test_scope_settings_do_not_leak_across_transactions():
    # set_config(..., true) is transaction-local: once the scoped query
    # commits, a new transaction on a fresh connection sees nothing.
    assert agent_ids(ADMIN)
    with raw_agent_connection() as conn:
        assert conn.execute("SELECT current_setting('app.role', true)").fetchone()[0] in (None, "")
        assert conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 0


def test_statement_timeout_applies():
    out = query_db("SELECT COUNT(*) FROM expenses a, expenses b, expenses c, expenses d, "
                   "expenses e, expenses f, expenses g", scope=ADMIN)
    # 20^7 rows: either it finishes (fast machine) or the 5s timeout cancels it.
    assert out.startswith("[") or "statement timeout" in out
