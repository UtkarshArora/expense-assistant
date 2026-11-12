# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Invite-only, multi-user (Auth0) chat assistant for questions about company spending. A hand-written agent loop (Anthropic Python SDK, `client.messages.create`, no agent framework) decides whether to query Postgres, read policy docs, or both, and the UI shows the tool calls behind each reply. No RAG, non-streaming chat.

## Commands

Setup: `cp .env.example .env` at the **repo root** and set `ANTHROPIC_API_KEY`, `AUTH0_DOMAIN`, `AUTH0_AUDIENCE` (the backend loads `.env` from the repo root, not `backend/`). The frontend reads `frontend/.env.local` (`VITE_AUTH0_DOMAIN`, `VITE_AUTH0_CLIENT_ID`, `VITE_AUTH0_AUDIENCE`; see `frontend/.env.example`). If they're missing, Vite drops the whole app as dead code and the page shows a config error. Auth0 tenant setup is in README.md.

```bash
# Postgres (on first boot only: seeds `expenses`, then db/02_security.sql adds agent_reader + RLS)
docker compose up -d db
docker compose down -v          # drop the volume so both init scripts re-run

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
python -m pytest                                    # all unit tests (integration deselected by pytest.ini)
python -m pytest tests/test_sql_guard.py -k comment # one group
python -m pytest -m integration                     # RLS tests: needs the compose DB running
```

Integration tests (`tests/integration/test_rls.py`) run in CI against a Postgres service container with both init scripts applied. To apply `db/02_security.sql` to an existing local DB without wiping it, run `docker exec -i expense-assistant-db-1 psql -U expense_user -d expense_db < db/02_security.sql`.

`tests/test_auth.py` signs RS256 tokens with a throwaway key and monkeypatches the JWKS lookup. Route tests use `app.dependency_overrides` for `get_current_user`/`get_session` and a non-context `TestClient(app)`, so the lifespan (Postgres) never runs. `conftest.py` sets test defaults for `AUTH0_DOMAIN`/`AUTH0_AUDIENCE`.

`tests/test_sql_guard.py` covers the `query_db` guard with `psycopg.connect` mocked; every rejection case asserts the connection was never opened. Manual check queries: "What did Engineering spend on software in Q2?" (DB only), "What's the per-attendee cap for client meals?" (docs only), "What client meals did Sales have last quarter, and were any over the policy cap?" (both).

## Architecture

**Request flow:** `frontend/src/api.ts` (Bearer token from `useApi`) → `POST /chat` (`backend/app/routers/chat.py`) → `get_current_user` verifies the JWT and upserts `app_user` → daily cap and conversation-ownership checks → persists the user message → runs `run_agent` in a worker thread via `asyncio.to_thread` (the SDK call is blocking) → persists the assistant message and its tool calls → returns them together.

**Agent (`backend/app/agent.py`):** tool implementations, tool schemas, and a loop (capped at `MAX_TOOL_ITERATIONS`) that continues while `stop_reason == "tool_use"`, dispatching by name through `TOOL_FUNCTIONS`. Adding a tool means adding the function, its entry in `TOOL_FUNCTIONS`, and its schema in `TOOLS`.

- `query_db(sql, *, scope)` runs model-generated SQL through three independent layers:
  1. **Regex** (`app/sql_guard.py`, unchanged from the original guard). It also rejects every `WITH`, so the prompt tells the model to use subqueries.
  2. **sqlglot AST**: one SELECT or set operation, no `INTO`, no locks, no DML/DDL anywhere in the tree, tables limited to `expenses`, and functions from an allowlist (unknown ones are rejected).
  3. **Database**: it connects as `agent_reader` (`AGENT_DATABASE_URL`) in a read-only transaction. It first sets `app.role`/`app.department`/`app.employee` with bound `set_config(..., true)` and `SET LOCAL statement_timeout`. RLS in `db/02_security.sql` then scopes rows: admin sees all, manager their department, employee their own rows. An unknown or missing scope sees nothing.

  Results are capped at 500 rows. When adding to the function allowlist, check how sqlglot classes it: `AND`/`OR`/`EXISTS` are `Func` subclasses.
- `AccessScope` is built in `chat.py` from the authenticated `app_user`. `run_agent` passes it to tools in `SCOPED_TOOLS` at dispatch. It is not in any tool schema, and a model-supplied `scope` argument is rejected. `build_system_prompt(scope)` tells the model what the user can see. That only affects UX; RLS is the enforcement.
- `search_files` globs `docs/` and returns full file contents (not just paths).
- `run_agent(history, user_message)` returns `(text, tool_calls, truncated)`. `chat.py` loads the last `HISTORY_LIMIT` (20) stored messages and passes them through `build_history`, which keeps **only user/assistant text**. Tool calls are never replayed to the model (invariant 2). `build_history` also enforces role alternation: a leading assistant turn is dropped, an unanswered trailing user turn is dropped, same-role runs are merged, and empty turns are skipped.
- The loop stops after `MAX_TOOL_ITERATIONS` (8) model turns. It then makes one more call with `tool_choice={"type": "none"}` to force an answer from the results so far, falling back to `FALLBACK_MESSAGE` if that fails. The reply is stored with `Message.truncated = True`, and the UI shows a "Partial answer" badge.
- Tool dispatch never raises. An unknown tool, bad input or tool crash becomes an `is_error` tool_result, carrying only the exception type, not its message.
- `SYSTEM_PROMPT` hardcodes the exact case-sensitive `category`/`status`/`department` values from `seed_expenses.sql`; update both together.

**Auth (`backend/app/auth.py`):** Auth0 access tokens are verified via `PyJWKClient` (RS256 only; issuer, audience, exp, iat and sub required). Role, department and employee name come from namespaced claims (`https://expense-assistant/…`) set by the tenant's post-login Action. A reference copy is in `auth0/post-login-action.js` and must be kept in sync by hand. The status codes: no or invalid token → 401; valid token without a known role → 403; `require_role(...)` → 403. Every conversation query filters on `Conversation.user_id`. Another user's conversation returns **404** (never 403), on both read and `POST /chat`.

**Two sets of tables in one Postgres DB:**

- `expenses`: owned by `seed_expenses.sql`, mounted into `docker-entrypoint-initdb.d`. Not an ORM model.
- `app_user` (not `user`, a reserved word), `conversation` (with `user_id`), `message`, `toolcall`: SQLModel models in `models.py`, created by `init_db()` on FastAPI startup (`create_all`, no migrations). Timestamps are naive UTC on purpose. Because `create_all` never alters existing tables, a new column (e.g. `message.truncated`) needs `docker compose down -v` locally.

**Two DB drivers from one `DATABASE_URL`:** the app uses async SQLAlchemy/asyncpg (`config.database_url_async` rewrites the scheme to `postgresql+asyncpg://`); `query_db` opens its own sync `psycopg` connection with the plain `postgresql://` URL.

**Frontend:** React 19 + Vite + Tailwind v4 + ShadCN primitives (`src/components/ui/`). `main.tsx` wraps the app in `Auth0Provider` (refresh tokens, `localstorage` cache so reloads don't need third-party cookies). `App.tsx` is the auth gate (`LoginPage` vs `ChatApp`). `ChatApp.tsx` holds the chat state. `@` aliases `src/`. The API base is `VITE_API_URL` (default `http://localhost:8000`); the backend's CORS allowlist comes from `CORS_ORIGINS`. `ToolCallTrace.tsx` renders the collapsible tool-call details under assistant messages.

**`minimal_agent.py`** is a standalone teaching version of the same loop (local glob and a SQLite `app.db`). It is not used by the app.

#Invariants

1. Model-generated SQL must be a single read-only SELECT, enforced in layers: regex, sqlglot AST allowlist, and a read-only least-privilege DB role with row-level security. Never weaken or remove any layer.
2. The tool call trace should be persisted for the user to see and not passed in the model
3. Never log API keys or raw model output containing user data
