"""
Minimal agent loop from scratch. No frameworks.

An agent is three things: an LLM, a set of tools, and a loop.
This file is the whole thing. Read it top to bottom.

Setup:
    pip install anthropic
    export ANTHROPIC_API_KEY=sk-ant-...
    python minimal_agent.py

Then type something like:
    what python files are in this folder, and how many users are in app.db?
"""

import json
import os
import sqlite3
import glob

import anthropic

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
MODEL = "claude-opus-4-8"


# ----------------------------------------------------------------------
# 1. TOOL IMPLEMENTATIONS
# Plain Python functions. Nothing special. The model never runs these,
# your code does. The model only asks for them by name.
# ----------------------------------------------------------------------

def search_files(pattern):
    """Return file paths in the current directory matching a glob pattern."""
    matches = glob.glob(pattern)
    if not matches:
        return f"No files matched {pattern}"
    return "\n".join(matches)


def query_db(sql):
    """Run a read-only SQL query against app.db and return the rows."""
    if not os.path.exists("app.db"):
        return "Error: app.db does not exist. Create it first."
    con = sqlite3.connect("app.db")
    try:
        rows = con.execute(sql).fetchall()
        return json.dumps(rows) if rows else "Query ran, zero rows returned."
    except sqlite3.Error as e:
        return f"SQL error: {e}"  # errors go back to the model, it can retry
    finally:
        con.close()


# Map tool names to the functions above. The loop uses this to dispatch.
TOOL_FUNCTIONS = {
    "search_files": search_files,
    "query_db": query_db,
}


# ----------------------------------------------------------------------
# 2. TOOL SCHEMAS
# This is what the model actually sees. Descriptions matter. The model
# decides whether and how to call a tool based entirely on these words.
# ----------------------------------------------------------------------

TOOLS = [
    {
        "name": "search_files",
        "description": "Find files in the current directory by glob pattern, "
                       "for example '*.py' or 'data/*.csv'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "A glob pattern such as '*.py'",
                }
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "query_db",
        "description": "Run a read-only SQL query against the local SQLite "
                       "database app.db and return the resulting rows.",
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
# This is the entire agent. Everything above is just wiring.
# ----------------------------------------------------------------------

def run_agent(user_message):
    # The conversation is a growing list of messages. We append to it as
    # the model and our tools take turns.
    messages = [{"role": "user", "content": user_message}]

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            tools=TOOLS,
            messages=messages,
        )

        # Whatever the model produced this turn goes into the history.
        messages.append({"role": "assistant", "content": response.content})

        # If the model did not ask for a tool, it is done. Print and stop.
        if response.stop_reason != "tool_use":
            final_text = "".join(
                block.text for block in response.content
                if block.type == "text"
            )
            return final_text

        # Otherwise, the model asked for one or more tools. Run each one
        # and collect the results into a single user message.
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            print(f"  [tool] {block.name}({json.dumps(block.input)})")
            func = TOOL_FUNCTIONS[block.name]
            output = func(**block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,  # ties the result to the request
                "content": output,
            })

        messages.append({"role": "user", "content": tool_results})
        # Loop back around. The model now sees the tool output and decides
        # what to do next: call another tool, or answer.


# ----------------------------------------------------------------------
# 4. A tiny REPL so you can talk to it
# ----------------------------------------------------------------------

if __name__ == "__main__":
    print("Minimal agent ready. Ctrl-C to quit.\n")
    while True:
        try:
            task = input("you > ")
        except (KeyboardInterrupt, EOFError):
            print("\nbye")
            break
        if not task.strip():
            continue
        answer = run_agent(task)
        print(f"\nagent > {answer}\n")
