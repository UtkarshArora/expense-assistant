-- Least-privilege role and row-level security for the agent's query_db tool.
--
-- Runs after 01_seed_expenses.sql on the database's first boot (mounted into
-- docker-entrypoint-initdb.d by docker-compose.yml). Re-run it by hand, or
-- `docker compose down -v`, after changing it.
--
-- The app itself still connects as the owner (expense_user) for its own
-- tables. Only model-generated SQL runs as agent_reader, which:
--   * can read `expenses` and nothing else: no grants on app tables,
--     so even unguarded SQL can't touch conversations, messages or users;
--   * sees only the rows the RLS policy allows for the current user, as
--     set per transaction by query_db with set_config(..., true);
--   * defaults to seeing nothing when no scope is set.
--
-- The password is for local development only. Use a real secret, and set
-- AGENT_DATABASE_URL to match, anywhere else.

CREATE ROLE agent_reader LOGIN PASSWORD 'agent_reader_pass' CONNECTION LIMIT 20;

-- Belt and braces alongside query_db's SET LOCAL statement_timeout.
ALTER ROLE agent_reader SET statement_timeout = '5s';
ALTER ROLE agent_reader SET default_transaction_read_only = on;

REVOKE ALL ON SCHEMA public FROM agent_reader;
GRANT CONNECT ON DATABASE expense_db TO agent_reader;
GRANT USAGE ON SCHEMA public TO agent_reader;
GRANT SELECT ON expenses TO agent_reader;

ALTER TABLE expenses ENABLE ROW LEVEL SECURITY;

-- current_setting(name, true) returns NULL (not an error) when unset, and
-- every branch compares with `=`, so a missing or unknown scope matches no
-- rows: deny by default.
CREATE POLICY expenses_scoped_read ON expenses
    FOR SELECT
    TO agent_reader
    USING (
        CASE current_setting('app.role', true)
            WHEN 'admin'    THEN true
            WHEN 'manager'  THEN department = current_setting('app.department', true)
            WHEN 'employee' THEN employee   = current_setting('app.employee', true)
            ELSE false
        END
    );
