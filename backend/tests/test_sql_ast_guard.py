"""
Tests for the AST layer of the SQL guard (app/sql_guard.py).

Every case here starts with SELECT, is a single statement, and contains no
regex-forbidden keyword, so only the AST layer can stop it. Each rejection
also asserts the database was never contacted.
"""

import pytest

from app import agent
from app.agent import AccessScope
from app.sql_guard import PARSE_ERROR, SELECT_ONLY_ERROR, _check_ast, _check_regex, validate_sql

SCOPE = AccessScope(role="employee", department="Sales", employee_name="Marcus Chen")


def run(sql: str) -> str:
    return agent.query_db(sql, scope=SCOPE)


# ----------------------------------------------------------------------
# Rejected: only the AST layer catches these
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "sql, fragment",
    [
        # Changing the RLS scope from inside the query: `\bSET\b` doesn't
        # match set_config because `_` is a word character.
        ("SELECT set_config('app.role', 'admin', true)", "function set_config()"),
        ('SELECT "set_config"(\'app.role\', \'admin\', true)', "function set_config()"),
        ("SELECT pg_catalog.set_config('app.role', 'admin', false)", "function set_config()"),
        ("SELECT * FROM expenses WHERE id = (SELECT set_config('app.role','admin',false))::int",
         "function set_config()"),
        ("SELECT current_setting('app.role')", "function current_setting()"),
        # Server and file access, sleeps
        ("SELECT pg_sleep(30)", "function pg_sleep()"),
        ("SELECT pg_read_file('/etc/passwd')", "function pg_read_file()"),
        ("SELECT lo_import('/etc/passwd')", "function lo_import()"),
        ("SELECT version()", "function current_version()"),
        # Creates a table, despite being a SELECT
        ("SELECT * INTO pwned FROM expenses", "SELECT ... INTO"),
        # Catalog and app tables
        ("SELECT * FROM pg_catalog.pg_user", "pg_catalog.pg_user"),
        ("SELECT * FROM pg_user", "'pg_user'"),
        ("SELECT * FROM information_schema.tables", "information_schema.tables"),
        ('SELECT * FROM "app_user"', "'app_user'"),
        ("SELECT * FROM message", "'message'"),
        ("SELECT * FROM toolcall", "'toolcall'"),
        ("SELECT * FROM expenses UNION SELECT * FROM message", "'message'"),
        ("SELECT (SELECT count(*) FROM conversation)", "'conversation'"),
        ("SELECT * FROM expenses WHERE id IN (SELECT 1 FROM app_user)", "'app_user'"),
        ("SELECT * FROM expenses WHERE EXISTS (SELECT 1 FROM message)", "'message'"),
        ("SELECT * FROM other_db.public.expenses", "not allowed"),
        ("SELECT * FROM private.expenses", "not allowed"),
        # Table functions
        ("SELECT * FROM generate_series(1, 1000000000)", "table functions"),
        ("SELECT * FROM ROWS FROM (pg_sleep(1))", "table functions"),
    ],
)
def test_ast_rejects(fake_connect, sql, fragment):
    assert _check_regex(sql) is None, "precondition: the regex layer lets this through"
    result = run(sql)
    assert result.startswith("Error:")
    assert fragment in result
    fake_connect.assert_not_called()


def test_row_locks_are_rejected_by_ast_alone():
    # The regex also blocks FOR UPDATE (via UPDATE); check the AST layer
    # independently so removing either one still leaves a guard.
    assert "row locking" in _check_ast("SELECT * FROM expenses FOR UPDATE")
    assert "row locking" in _check_ast("SELECT * FROM expenses FOR SHARE")


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM expenses",
        "UPDATE expenses SET amount = 0",
        "WITH d AS (DELETE FROM expenses RETURNING *) SELECT * FROM d",
        "INSERT INTO expenses (amount) VALUES (1)",
    ],
)
def test_writes_are_rejected_by_ast_alone(sql):
    assert _check_ast(sql) is not None


def test_cte_body_reading_another_table_is_rejected_by_ast():
    # The regex rejects every WITH anyway; the AST layer independently
    # checks the CTE body, even when the CTE shadows an allowed name.
    assert "'message'" in _check_ast("WITH x AS (SELECT * FROM message) SELECT * FROM x")
    assert "'message'" in _check_ast(
        "WITH expenses AS (SELECT * FROM message) SELECT * FROM expenses"
    )


def test_unparseable_sql_is_rejected(fake_connect):
    assert run("SELECT FROM WHERE (((") == PARSE_ERROR
    fake_connect.assert_not_called()


def test_set_operation_is_allowed_at_root():
    assert _check_ast("SELECT amount FROM expenses UNION SELECT amount FROM expenses") is None


def test_non_select_root_is_rejected():
    assert _check_ast("SHOW search_path") == SELECT_ONLY_ERROR


# ----------------------------------------------------------------------
# Allowed: the analytical SQL the agent actually writes
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "SELECT * FROM expenses",
        "SELECT * FROM public.expenses e",
        "SELECT department, SUM(amount), ROUND(AVG(amount), 2) FROM expenses GROUP BY department",
        "SELECT category, COUNT(*) FROM expenses WHERE description ILIKE '%client%' GROUP BY 1",
        "SELECT COUNT(DISTINCT employee), SUM(amount) FILTER (WHERE status = 'flagged') FROM expenses",
        "SELECT date_trunc('month', expense_date) AS m, SUM(amount) FROM expenses GROUP BY 1 ORDER BY 1",
        "SELECT DATE_TRUNC('quarter', expense_date)::date FROM expenses",
        "SELECT EXTRACT(QUARTER FROM expense_date), date_part('year', expense_date) FROM expenses",
        "SELECT to_char(expense_date, 'YYYY-MM'), TO_CHAR(amount, 'FM999,999.00') FROM expenses",
        "SELECT * FROM expenses WHERE expense_date BETWEEN DATE '2026-04-01' AND '2026-06-30'",
        "SELECT * FROM expenses WHERE expense_date >= CURRENT_DATE - INTERVAL '3 months'",
        "SELECT employee, amount, RANK() OVER (PARTITION BY department ORDER BY amount DESC) FROM expenses",
        "SELECT ROW_NUMBER() OVER (ORDER BY amount), LAG(amount) OVER (ORDER BY expense_date) FROM expenses",
        "SELECT COALESCE(SUM(amount), 0), NULLIF(MAX(amount), 0) FROM expenses",
        "SELECT CASE WHEN amount > 100 THEN 'big' ELSE 'small' END FROM expenses",
        "SELECT employee || ' - ' || department, UPPER(employee), LENGTH(description) FROM expenses",
        "SELECT string_agg(employee, ', '), array_agg(DISTINCT category) FROM expenses",
        "SELECT * FROM expenses WHERE amount > (SELECT AVG(amount) FROM expenses)",
        "SELECT * FROM (SELECT department, SUM(amount) AS total FROM expenses GROUP BY 1) t WHERE total > 500",
        "SELECT a.employee FROM expenses a JOIN expenses b ON a.id = b.id",
        "SELECT * FROM expenses WHERE employee ILIKE ANY (ARRAY['%chen%', '%nair%'])",
        "SELECT * FROM expenses WHERE description ~* 'client'",
        "SELECT DISTINCT category FROM expenses ORDER BY category NULLS LAST LIMIT 5",
        "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY amount) FROM expenses",
        # AND / OR / EXISTS / ^ are Func subclasses in sqlglot; an earlier
        # version of the allowlist rejected them (caught by the RLS tests).
        "SELECT * FROM expenses WHERE department = 'Sales' AND amount > 100",
        "SELECT * FROM expenses WHERE category = 'Lodging' OR category = 'Airfare'",
        "SELECT * FROM expenses WHERE (status = 'flagged' OR amount > 500) AND NOT department = 'Sales'",
        "SELECT * FROM expenses e WHERE EXISTS (SELECT 1 FROM expenses x WHERE x.employee = e.employee AND x.amount > 1000)",
        "SELECT amount ^ 2 FROM expenses",
    ],
)
def test_analytical_queries_are_allowed(fake_connect, sql):
    statement, error = validate_sql(sql)
    assert error is None, error
    assert statement == sql  # executed as written, not regenerated from the AST
    assert run(sql) == '[{"col": 1}]'
    fake_connect.assert_called_once()
