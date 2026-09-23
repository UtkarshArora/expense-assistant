# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Single-user, local-only chat assistant for questions about company spending. A hand-written agent loop (Anthropic Python SDK, `client.messages.create`, no agent framework) decides whether to query Postgres, read policy docs, or both, and the UI shows the tool calls behind each reply. No auth, no RAG, non-streaming chat.

## Commands

Setup: `cp .env.example .env` at the **repo root** and set `ANTHROPIC_API_KEY` (the backend loads `.env` from the repo root, not `backend/`).

```bash
# Postgres (seeds the `expenses` table on first boot only)
docker compose up -d db
docker compose down -v          # drop the volume so seed_expenses.sql re-runs

# Backend (from backend/)
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000   # Swagger at :8000/docs

# Frontend (from frontend/)
npm install
npm run dev      # :5173
npm run build    # tsc -b typecheck + vite build
npm run lint     # oxlint
```

Tests (from `backend/`, needs `pip install -r requirements-dev.txt`; no database or API key required):

```bash
python -m pytest                                    # all
python -m pytest tests/test_sql_guard.py -k comment # one group
```

`tests/test_sql_guard.py` covers the `query_db` guard with `psycopg.connect` mocked; every rejection case asserts the connection was never opened. Manual check queries: "What did Engineering spend on software in Q2?" (DB only), "What's the per-attendee cap for client meals?" (docs only), "What client meals did Sales have last quarter, and were any over the policy cap?" (both).

## Architecture

**Request flow:** `frontend/src/api.ts` → `POST /chat` (`backend/app/routers/chat.py`) → persists the user message → runs `run_agent` in a worker thread via `asyncio.to_thread` (the SDK call is blocking) → persists the assistant message and its tool calls → returns them together.

**Agent (`backend/app/agent.py`):** tool implementations, tool schemas, and a `while` loop that continues while `stop_reason == "tool_use"`, dispatching by name through `TOOL_FUNCTIONS`. Adding a tool means adding the function, its entry in `TOOL_FUNCTIONS`, and its schema in `TOOLS`.

- `query_db` runs model-generated SQL, so it's locked down: single statement, must start with `SELECT`, forbidden-keyword regex, read-only connection, capped at 500 rows. Keep these guards if you touch it.
- `search_files` globs `docs/` and returns full file contents (not just paths).
- `run_agent` is stateless: it sends only the current user message. Earlier turns are stored in the DB but are **not** passed back to the model.
- `SYSTEM_PROMPT` hardcodes the exact case-sensitive `category`/`status`/`department` values from `seed_expenses.sql`; update both together.

**Two sets of tables in one Postgres DB:**

- `expenses`: owned by `seed_expenses.sql`, mounted into `docker-entrypoint-initdb.d`. Not an ORM model.
- `conversation`, `message`, `toolcall`: SQLModel models in `models.py`, created by `init_db()` on FastAPI startup (`create_all`, no migrations). Timestamps are naive UTC on purpose.

**Two DB drivers from one `DATABASE_URL`:** the app uses async SQLAlchemy/asyncpg (`config.database_url_async` rewrites the scheme to `postgresql+asyncpg://`); `query_db` opens its own sync `psycopg` connection with the plain `postgresql://` URL.

**Frontend:** React 19 + Vite + Tailwind v4 + ShadCN primitives (`src/components/ui/`). `@` aliases `src/`. The API base is `VITE_API_URL` (default `http://localhost:8000`); the backend's CORS allowlist comes from `CORS_ORIGINS`. `ToolCallTrace.tsx` renders the collapsible tool-call details under assistant messages.

**`minimal_agent.py`** is a standalone teaching version of the same loop (local glob and a SQLite `app.db`). It is not used by the app.

#Invariants

1. Model-generated SQL should be a read-only SQL statement, enforced by regex, never weaken this
2. The tool call trace should be persisted for the user to see and not passed in the model
3. Never log API keys or raw model output containing user data
