"""
The agent: a tools list, a while-loop keyed on stop_reason == "tool_use",
and tool dispatch by name with results sent back as tool_result blocks
keyed by tool_use_id. query_db is locked to a single read-only SELECT
since the SQL text is model-generated; search_files reads doc contents
directly rather than just listing matches.
"""

import glob
import json
import os
import re

import anthropic
import psycopg

from .config import settings

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """You are a finance assistant answering questions about company \
expenses. You have two tools: query_db (the 'expenses' table) and search_files \
(policy docs in docs/). Use whichever tool(s) the question needs — some questions \
need both a query and a policy lookup.

The 'expenses' table's text columns are case-sensitive and use these exact values:
- category: 'Client Meals', 'Team Meals', 'Lodging', 'Airfare', 'Transport', \
'Software', 'Conference', 'Office Supplies'
- status: 'approved', 'pending', 'flagged' (lowercase)
- department: Title Case (e.g. 'Engineering', 'Sales', 'Marketing')

If you're not sure of the exact spelling of a value (e.g. an employee name), use \
ILIKE or run a quick SELECT DISTINCT first rather than guessing — a zero-row result \
is more often a casing mismatch than an absence of data."""


# ----------------------------------------------------------------------
# 1. TOOL IMPLEMENTATIONS
# ----------------------------------------------------------------------

def search_files(pattern: str) -> str:
    """Find policy docs under docs/ by glob pattern and return their contents."""
    matches = sorted(glob.glob(os.path.join(settings.docs_dir, pattern)))
    if not matches:
        return f"No files matched {pattern!r} in docs/"
    parts = []
    for path in matches:
        try:
            with open(path) as f:
                content = f.read()
        except OSError as e:
            content = f"Error reading file: {e}"
        parts.append(f"--- {os.path.basename(path)} ---\n{content}")
    return "\n\n".join(parts)


# Only a single SELECT statement is allowed — the SQL text is model-generated.
_SELECT_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
_FORBIDDEN_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|"
    r"EXEC|CALL|MERGE|ATTACH|VACUUM|COPY|SET|RESET)\b",
    re.IGNORECASE,
)


def query_db(sql: str) -> str:
    """Run a single read-only SELECT against the expenses table and return rows as JSON."""
    statement = sql.strip().rstrip(";")
    if ";" in statement:
        return "Error: only a single SQL statement is allowed."
    if not _SELECT_RE.match(statement):
        return "Error: only SELECT statements are allowed."
    if _FORBIDDEN_RE.search(statement):
        return "Error: statement contains a disallowed keyword."

    try:
        with psycopg.connect(settings.database_url) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute(statement)
                rows = cur.fetchmany(500)
                columns = [desc.name for desc in cur.description] if cur.description else []
    except psycopg.Error as e:
        return f"SQL error: {e}"

    if not rows:
        return "Query ran, zero rows returned."
    return json.dumps([dict(zip(columns, row)) for row in rows], default=str)


TOOL_FUNCTIONS = {
    "search_files": search_files,
    "query_db": query_db,
}


# ----------------------------------------------------------------------
# 2. TOOL SCHEMAS
# ----------------------------------------------------------------------

TOOLS = [
    {
        "name": "search_files",
        "description": "Find company policy documents in docs/ by glob pattern "
                       "(e.g. '*.md' for all of them) and return their contents. "
                       "Use this to answer questions about expense policy, "
                       "reimbursement rules, spending caps, and approval thresholds.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "A glob pattern such as '*.md'",
                }
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "query_db",
        "description": "Run a read-only SELECT query against the 'expenses' table "
                       "and return the resulting rows. Columns: id, expense_date, "
                       "employee, department, category, description, amount, "
                       "status (approved | pending | flagged). Use this to answer "
                       "questions about actual company spending.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "A single SELECT statement",
                }
            },
            "required": ["sql"],
        },
    },
]


# ----------------------------------------------------------------------
# 3. THE LOOP
# ----------------------------------------------------------------------

def run_agent(user_message: str) -> tuple[str, list[dict]]:
    messages = [{"role": "user", "content": user_message}]
    tool_calls: list[dict] = []

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            final_text = "".join(
                block.text for block in response.content
                if block.type == "text"
            )
            return final_text, tool_calls

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            func = TOOL_FUNCTIONS[block.name]
            output = func(**block.input)
            tool_calls.append({"name": block.name, "input": block.input, "output": output})
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output,
            })

        messages.append({"role": "user", "content": tool_results})
