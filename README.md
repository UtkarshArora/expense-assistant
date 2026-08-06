# Expense Assistant

Chat assistant that answers questions about company spending. An agent
decides whether a question needs a database query, a policy lookup, or
both, runs the tool(s), and answers with the tool calls shown alongside
the reply.

Stack: React/TypeScript (Vite, Tailwind, ShadCN) on FastAPI (Python,
async) on PostgreSQL. The agent calls the Anthropic API directly via
`client.messages.create` in the Python SDK, no agent framework.

## Scope

Single-user, local-only. No auth, no multi-tenancy, no RAG (`search_files`
is a glob + read over the docs folder, not embeddings), chat is
non-streaming. Built to be read end to end, not extended.

---

## Layout

```
Agent/
├── docker-compose.yml       # Postgres only
├── seed_expenses.sql        # creates + seeds the `expenses` table
├── docs/                    # policy markdown, read by search_files
├── minimal_agent.py          # standalone reference version of the agent loop
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py           # FastAPI app, CORS, router mounting
│       ├── config.py         # env/config loading
│       ├── db.py             # async engine + session, FastAPI dependency
│       ├── models.py         # Conversation / Message / ToolCall (SQLModel)
│       ├── schemas.py        # request/response shapes
│       ├── agent.py          # the agent loop + its two tools
│       └── routers/
│           ├── chat.py             # POST /chat
│           └── conversations.py    # GET /conversations, GET /conversations/{id}
└── frontend/
    └── src/
        ├── api.ts                     # fetch wrapper + types matching the backend schemas
        ├── App.tsx                    # top-level state: conversations, messages, send
        └── components/
            ├── ConversationSidebar.tsx
            ├── ChatView.tsx / MessageList.tsx / MessageBubble.tsx
            ├── ToolCallTrace.tsx      # collapsible per-message tool-call panel
            └── ui/                    # vendored ShadCN primitives (button, input, card, ...)
```

---

## Running it

Needs Docker, Python 3.11+, Node 20+.

**1. Env vars**

```bash
cp .env.example .env
# set ANTHROPIC_API_KEY
```

**2. Postgres**

```bash
docker compose up -d db
```

On first boot this creates `expense_db` and runs `seed_expenses.sql` to
build and populate the `expenses` table (mounted into Postgres's
`docker-entrypoint-initdb.d/`). Changed the seed data and want it to
re-run? Drop the volume first: `docker compose down -v`.

**3. Backend**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Swagger UI at `http://localhost:8000/docs`. On startup the backend also
creates its own tables (`conversation`, `message`, `toolcall`) if they're
missing — separate from `expenses`, which belongs to `seed_expenses.sql`.

**4. Frontend**

```bash
cd frontend
npm install
npm run dev
```

`http://localhost:5173`.

**5. Try it**

- DB only: "What did Engineering spend on software in Q2?"
- Docs only: "What's the per-attendee cap for client meals?"
- Both (the interesting case): "What client meals did Sales have last
  quarter, and were any over the policy cap?"

Click "N tool calls" under a reply to see the SQL or doc contents behind
the answer.

---

## How it works

### Agent loop

`backend/app/agent.py`: a `while True` loop that calls
`client.messages.create(...)` with a list of tool definitions, checks
`response.stop_reason`, and on `"tool_use"` runs the requested tool(s)
locally and sends results back as `tool_result` blocks keyed by
`tool_use_id`. Loops until the model answers with plain text instead of
another tool call. `minimal_agent.py` at the repo root is the same loop
in isolation, without the Postgres/FastAPI wiring — useful for seeing the
shape on its own.

`query_db` is locked to a single read-only `SELECT` (regex-checked, run
in a read-only transaction) since the SQL text is model-generated.
`search_files` reads and returns file contents from `docs/`, not just
matching paths — the agent needs the policy text itself.

The Anthropic call is synchronous, so `POST /chat` runs `run_agent` in a
worker thread via `asyncio.to_thread` rather than making the loop async —
keeps the loop itself simple and only makes the call site async-aware.

### FastAPI's async model

`async def` handlers don't block the event loop while awaiting I/O, so
one worker process can serve many requests concurrently — while one
request waits on Postgres, the loop works on another. That only holds if
everything in the request path is `async` or explicitly offloaded: a
blocking call made directly inside a handler (like the Anthropic SDK
call) would stall the loop for every other request, hence
`asyncio.to_thread`.

### DB sessions

`backend/app/db.py` creates one async SQLAlchemy engine (via SQLModel) at
import time, backed by `asyncpg`. Each request gets its own session
through a FastAPI dependency:

```python
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
```

Routes declare `session: AsyncSession = Depends(get_session)`. FastAPI
calls the generator, hands the session to the route, then resumes the
generator to close it once the route returns — success or failure. A
session's lifetime is exactly one request; nothing has to close one
manually.

### Persistence

Three tables in `backend/app/models.py`: `Conversation`, `Message` (role
+ content, FK'd to a conversation), `ToolCall` (name, input, output, FK'd
to the assistant message that triggered it). `POST /chat` writes the user
message, runs the agent, writes the assistant reply and its tool calls,
commits once. `GET /conversations/{id}` reads it all back joined for the
frontend's trace panel.

`expenses` is deliberately not one of these SQLModel tables — it belongs
to `seed_expenses.sql` and lives in the same database, but the ORM
doesn't know about it. `query_db` talks to it over a separate `psycopg`
connection.

### Frontend

Plain `fetch` (`src/api.ts`), no data-fetching library. `App.tsx` owns
the conversation list, active messages, and a `pending` flag, and is the
only thing that calls the API — everything else is presentational.
Sending a message appends the user's text immediately, then appends the
real assistant message (with `tool_calls`) once the response lands.
Assistant text renders through `react-markdown` (the model returns tables
and bold text fairly often); tool calls show in a collapsible
`ToolCallTrace` built on a vendored Radix `Collapsible`.
