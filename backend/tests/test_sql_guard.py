"""
Tests for the read-only SQL guard in query_db (issue #1).

Every rejection case also asserts psycopg.connect was never called: the
guard's promise is that bad SQL is stopped before it reaches the database.
"""

from unittest.mock import call

import pytest

from app import agent
from app.agent import AccessScope
from app.config import settings

SCOPE = AccessScope(role="manager", department="Sales", employee_name="Priya Nair")


def query_db(sql: str) -> str:
    return agent.query_db(sql, scope=SCOPE)

SINGLE_STATEMENT_ERROR = "Error: only a single SQL statement is allowed."
SELECT_ONLY_ERROR = "Error: only SELECT statements are allowed."
KEYWORD_ERROR = "Error: statement contains a disallowed keyword."


# ----------------------------------------------------------------------
# Accepted: a single SELECT reaches the database
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "sql, executed",
    [
        ("SELECT 1", "SELECT 1"),
        ("select * from expenses", "select * from expenses"),
        ("  SeLeCt amount FROM expenses  ", "SeLeCt amount FROM expenses"),
        ("SELECT * FROM expenses;", "SELECT * FROM expenses"),
        ("SELECT * FROM expenses;;  ", "SELECT * FROM expenses"),
        ("\n\tSELECT\n  department,\n  SUM(amount)\nFROM expenses\nGROUP BY department",
         "SELECT\n  department,\n  SUM(amount)\nFROM expenses\nGROUP BY department"),
        ("SELECT * FROM expenses WHERE id IN (SELECT id FROM expenses WHERE amount > 100)",
         "SELECT * FROM expenses WHERE id IN (SELECT id FROM expenses WHERE amount > 100)"),
    ],
)
def test_single_select_is_executed(fake_connect, sql, executed):
    assert query_db(sql) == '[{"col": 1}]'
    fake_connect.assert_called_once()
    # The model's statement runs last, after the scope and the timeout.
    assert fake_connect.cursor.execute.call_args_list[-1] == call(executed)


def test_connection_is_read_only(fake_connect):
    query_db("SELECT 1")
    assert fake_connect.conn.read_only is True


def test_connects_as_least_privilege_role(fake_connect):
    query_db("SELECT 1")
    fake_connect.assert_called_once_with(settings.agent_database_url)
    assert settings.agent_database_url != settings.database_url


def test_scope_and_timeout_are_set_before_the_statement(fake_connect):
    query_db("SELECT amount FROM expenses")
    calls = fake_connect.cursor.execute.call_args_list
    assert len(calls) == 3
    scope_sql, scope_params = calls[0].args
    assert "set_config('app.role', %s, true)" in scope_sql
    assert scope_params == ("manager", "Sales", "Priya Nair")  # bound, not interpolated
    assert calls[1] == call("SET LOCAL statement_timeout = '5s'")
    assert calls[2] == call("SELECT amount FROM expenses")


def test_missing_scope_fields_become_empty_strings(fake_connect):
    agent.query_db("SELECT 1", scope=AccessScope(role="admin"))
    assert fake_connect.cursor.execute.call_args_list[0].args[1] == ("admin", "", "")


def test_scope_is_required():
    with pytest.raises(TypeError):
        agent.query_db("SELECT 1")  # no scope, no query


# ----------------------------------------------------------------------
# Rejected: write and DDL statements
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO expenses (amount) VALUES (1)",
        "UPDATE expenses SET amount = 0",
        "DELETE FROM expenses",
        "delete from expenses",
        "DeLeTe FROM expenses",
        "DROP TABLE expenses",
        "TRUNCATE expenses",
        "ALTER TABLE expenses ADD COLUMN x int",
        "CREATE TABLE pwned (id int)",
        "GRANT ALL ON expenses TO public",
        "COPY expenses TO '/tmp/out.csv'",
        "WITH d AS (DELETE FROM expenses RETURNING *) SELECT * FROM d",
        "",
        "   ",
    ],
)
def test_non_select_is_rejected(fake_connect, sql):
    assert query_db(sql) == SELECT_ONLY_ERROR
    fake_connect.assert_not_called()


# ----------------------------------------------------------------------
# Rejected: multiple statements
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1; SELECT 2",
        "SELECT 1; DELETE FROM expenses",
        "SELECT 1;DELETE FROM expenses;",
        "SELECT 1 ;\n DROP TABLE expenses",
        "SELECT 1;;SELECT 2",
        "DELETE FROM expenses; SELECT 1",
    ],
)
def test_multiple_statements_are_rejected(fake_connect, sql):
    assert query_db(sql) == SINGLE_STATEMENT_ERROR
    fake_connect.assert_not_called()


# ----------------------------------------------------------------------
# Rejected: comment-based bypasses
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "sql, error",
    [
        # A comment ahead of the write hides it from a naive prefix check.
        ("/* SELECT */ DELETE FROM expenses", SELECT_ONLY_ERROR),
        ("-- SELECT\nDELETE FROM expenses", SELECT_ONLY_ERROR),
        # A comment splitting the keyword.
        ("SEL/**/ECT 1", SELECT_ONLY_ERROR),
        # A semicolon inside a comment still counts as a second statement.
        ("SELECT 1 /* ; */ ; DELETE FROM expenses", SINGLE_STATEMENT_ERROR),
        ("SELECT 1 -- ;\nDELETE FROM expenses", SINGLE_STATEMENT_ERROR),
        ("SELECT 1; -- DROP TABLE expenses", SINGLE_STATEMENT_ERROR),
        # A write keyword inside a comment is still refused.
        ("SELECT 1 /* DROP TABLE expenses */", KEYWORD_ERROR),
        ("SELECT 1 -- DELETE FROM expenses", KEYWORD_ERROR),
    ],
)
def test_comment_bypasses_are_rejected(fake_connect, sql, error):
    assert query_db(sql) == error
    fake_connect.assert_not_called()


# ----------------------------------------------------------------------
# Rejected by the keyword check alone
#
# These start with SELECT and are a single statement, so only
# _FORBIDDEN_RE stops them. They fail if that check is removed.
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM expenses FOR UPDATE",
        "select * from expenses for no key update",
        "SELECT * FROM dblink('dbname=expense_db', 'DELETE FROM expenses') AS t(x int)",
        "SELECT * FROM expenses WHERE id = 1 UNION SELECT 1 FROM expenses FOR UPDATE",
    ],
)
def test_forbidden_keyword_in_select_is_rejected(fake_connect, sql):
    assert query_db(sql) == KEYWORD_ERROR
    fake_connect.assert_not_called()
