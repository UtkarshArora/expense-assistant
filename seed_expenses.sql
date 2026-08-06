-- Seed data for the finance/expense assistant demo.
-- The agent's query_db tool runs read-only SELECTs against this table.
--
-- This is written for PostgreSQL (recommended: keep it in the same Postgres
-- instance as your app tables so the "PostgreSQL" story is one clean database).
-- To use SQLite instead, change "SERIAL PRIMARY KEY" to
-- "INTEGER PRIMARY KEY AUTOINCREMENT" and "NUMERIC(10,2)" to "REAL".

DROP TABLE IF EXISTS expenses;

CREATE TABLE expenses (
    id            SERIAL PRIMARY KEY,
    expense_date  DATE NOT NULL,
    employee      TEXT NOT NULL,
    department    TEXT NOT NULL,
    category      TEXT NOT NULL,
    description   TEXT NOT NULL,
    amount        NUMERIC(10,2) NOT NULL,
    status        TEXT NOT NULL   -- approved | pending | flagged
);

INSERT INTO expenses (expense_date, employee, department, category, description, amount, status) VALUES
-- Q1 2026 (Jan-Mar)
('2026-01-15', 'Marcus Chen',     'Sales',       'Client Meals',    'Client coffee with Beacon (2 attendees)',        28.00,  'approved'),
('2026-02-14', 'Marcus Chen',     'Sales',       'Client Meals',    'Client dinner with Nimbus (4 attendees)',        300.00, 'approved'),
('2026-02-20', 'Priya Nair',      'Sales',       'Conference',      'Sales summit registration',                      2200.00,'approved'),
('2026-03-05', 'Aisha Khan',      'Engineering', 'Team Meals',      'Team lunch (6 people)',                          210.00, 'approved'),
('2026-03-30', 'Dana Whitfield',  'Marketing',   'Office Supplies', 'Branded notebooks',                              140.00, 'approved'),
-- Q2 2026 (Apr-Jun) — this is "last quarter" as of Aug 2026
('2026-04-02', 'Tomas Rivera',    'Engineering', 'Software',        'JetBrains licenses (annual)',                    1500.00,'pending'),
('2026-04-12', 'Priya Nair',      'Sales',       'Client Meals',    'Client dinner with Acme (4 attendees)',          340.00, 'approved'),
('2026-04-18', 'Aisha Khan',      'Engineering', 'Software',        'Datadog subscription',                           600.00, 'approved'),
('2026-04-25', 'Aisha Khan',      'Engineering', 'Transport',       'Airport taxi',                                   65.00,  'approved'),
('2026-05-03', 'Marcus Chen',     'Sales',       'Client Meals',    'Client lunch with Beacon (3 attendees)',         180.00, 'approved'),
('2026-05-10', 'Marcus Chen',     'Sales',       'Lodging',         'Hotel, NYC client visit (1 night)',              420.00, 'flagged'),
('2026-05-11', 'Marcus Chen',     'Sales',       'Airfare',         'Economy flight JFK-ORD',                         240.00, 'approved'),
('2026-05-21', 'Priya Nair',      'Sales',       'Client Meals',    'Client dinner with Vertex (5 attendees)',        680.00, 'pending'),
('2026-05-28', 'Tomas Rivera',    'Engineering', 'Software',        'GPU cloud credits',                              2800.00,'pending'),
('2026-06-01', 'Priya Nair',      'Sales',       'Lodging',         'Hotel, Chicago (2 nights)',                      560.00, 'approved'),
('2026-06-09', 'Dana Whitfield',  'Marketing',   'Client Meals',    'Client dinner with Orbit (2 attendees)',         210.00, 'approved'),
('2026-06-15', 'Dana Whitfield',  'Marketing',   'Conference',      'SaaSConf registration',                          1200.00,'approved'),
('2026-06-16', 'Dana Whitfield',  'Marketing',   'Airfare',         'Business class SFO-JFK',                          1650.00,'pending'),
('2026-06-20', 'Tomas Rivera',    'Engineering', 'Team Meals',      'Team dinner (5 people)',                          260.00, 'approved');
