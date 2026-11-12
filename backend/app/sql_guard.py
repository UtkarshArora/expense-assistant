"""
Validation for model-generated SQL, run before query_db opens a connection.

Defense in depth (invariant 1). Each layer stands on its own and none may
be weakened or removed:

  1. Regex (cheap, fast): single statement, starts with SELECT, no
     write/DDL keywords. Unchanged from the original guard.
  2. AST (sqlglot, Postgres dialect): exactly one SELECT/set-operation;
     no SELECT ... INTO, no row locks, no DML/DDL anywhere in the tree;
     tables limited to `expenses` (and CTEs the query defines); functions
     limited to an allowlist, so unknown ones such as set_config,
     current_setting, pg_sleep and pg_read_file are rejected.
  3. Database (see db/02_security.sql): a read-only transaction as the
     least-privilege `agent_reader` role, SELECT on `expenses` only, with
     row-level security scoping rows to the user, plus a statement timeout.

Error strings go back to the model as tool results, so they say what to
change rather than just "rejected".
"""

import re

import sqlglot
from sqlglot import exp

SINGLE_STATEMENT_ERROR = "Error: only a single SQL statement is allowed."
SELECT_ONLY_ERROR = "Error: only SELECT statements are allowed."
KEYWORD_ERROR = "Error: statement contains a disallowed keyword."
PARSE_ERROR = "Error: could not parse the SQL statement."

# ----------------------------------------------------------------------
# Layer 1: regex
# ----------------------------------------------------------------------

_SELECT_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
_FORBIDDEN_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|"
    r"EXEC|CALL|MERGE|ATTACH|VACUUM|COPY|SET|RESET)\b",
    re.IGNORECASE,
)


def _check_regex(statement: str) -> str | None:
    if ";" in statement:
        return SINGLE_STATEMENT_ERROR
    if not _SELECT_RE.match(statement):
        return SELECT_ONLY_ERROR
    if _FORBIDDEN_RE.search(statement):
        return KEYWORD_ERROR
    return None


# ----------------------------------------------------------------------
# Layer 2: AST
# ----------------------------------------------------------------------

ALLOWED_TABLES = frozenset({"expenses"})
ALLOWED_SCHEMAS = frozenset({"", "public"})

# Functions sqlglot recognises, by expression class. Aggregates, maths,
# text, dates, conditionals, casts and window functions: enough for
# spending analysis, nothing that touches the server or session.
ALLOWED_FUNCTIONS: frozenset[type[exp.Func]] = frozenset({
    # operators sqlglot models as Func subclasses (subqueries under EXISTS
    # are still walked and checked like any other)
    exp.And, exp.Or, exp.Exists, exp.Pow, exp.Collate,
    # aggregates
    exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max, exp.Stddev,
    exp.PercentileCont, exp.ArrayAgg, exp.GroupConcat,
    # maths
    exp.Round, exp.Floor, exp.Ceil, exp.Abs, exp.Greatest, exp.Least,
    # null handling / conditionals
    exp.Coalesce, exp.Nullif, exp.Case, exp.If,
    # text
    exp.Lower, exp.Upper, exp.Trim, exp.Length, exp.Concat, exp.Replace,
    exp.Substring, exp.SplitPart, exp.StrPosition, exp.RegexpLike,
    exp.RegexpILike, exp.Array,
    # dates and casts
    exp.Extract, exp.TimestampTrunc, exp.DateTrunc, exp.TimeToStr,
    exp.StrToDate, exp.CurrentDate, exp.CurrentTimestamp, exp.Localtimestamp,
    exp.Cast, exp.TryCast,
    # window functions
    exp.RowNumber, exp.Rank, exp.DenseRank, exp.Lag, exp.Lead,
})

# Functions sqlglot doesn't model (parsed as exp.Anonymous), by name.
ALLOWED_ANONYMOUS_FUNCTIONS = frozenset({"make_date", "age", "initcap"})

_FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop,
    exp.Alter, exp.Command, exp.Set, exp.Copy, exp.Grant,
)


def _function_name(func: exp.Func) -> str:
    if isinstance(func, exp.Anonymous):
        return func.name
    return func.sql_name().lower()


def _check_ast(statement: str) -> str | None:
    try:
        trees = [t for t in sqlglot.parse(statement, dialect="postgres") if t is not None]
    except sqlglot.errors.SqlglotError:
        return PARSE_ERROR
    if len(trees) != 1:
        return SINGLE_STATEMENT_ERROR
    tree = trees[0]

    if not isinstance(tree, (exp.Select, exp.SetOperation)):
        return SELECT_ONLY_ERROR
    if any(isinstance(node, _FORBIDDEN_NODES) for node in tree.walk()):
        return SELECT_ONLY_ERROR
    if tree.find(exp.Into):
        return "Error: SELECT ... INTO is not allowed."
    if tree.find(exp.Lock):
        return "Error: row locking (FOR UPDATE / FOR SHARE) is not allowed."

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if not name:
            return "Error: table functions are not allowed; query the expenses table."
        if table.catalog or table.db.lower() not in ALLOWED_SCHEMAS:
            return f"Error: table {table.sql(dialect='postgres')} is not allowed; only 'expenses' can be queried."
        if name in cte_names and not table.db:
            continue  # a CTE defined in this query; its body is checked too
        if name not in ALLOWED_TABLES:
            return f"Error: table {name!r} is not allowed; only 'expenses' can be queried."

    for func in tree.find_all(exp.Func):
        allowed = (
            func.name.lower() in ALLOWED_ANONYMOUS_FUNCTIONS
            if isinstance(func, exp.Anonymous)
            else type(func) in ALLOWED_FUNCTIONS
        )
        if not allowed:
            return f"Error: function {_function_name(func)}() is not allowed."

    return None


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

def validate_sql(sql: str) -> tuple[str | None, str | None]:
    """Return (statement, None) if allowed, else (None, error message).

    The returned statement is the caller's own text (trimmed, trailing
    semicolons removed), never SQL regenerated from the AST.
    """
    statement = sql.strip().rstrip(";")
    error = _check_regex(statement) or _check_ast(statement)
    return (None, error) if error else (statement, None)
