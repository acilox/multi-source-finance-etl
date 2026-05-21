-- ============================================================
-- Finance ETL PostgreSQL — Customer master schema
-- ============================================================

CREATE TABLE IF NOT EXISTS customers (
    customer_id    VARCHAR(64) PRIMARY KEY,
    first_name     VARCHAR(128) NOT NULL,
    last_name      VARCHAR(128) NOT NULL,
    email          VARCHAR(256) UNIQUE,
    phone          VARCHAR(32),
    date_of_birth  DATE,
    address_line1  VARCHAR(256),
    city           VARCHAR(128),
    state          VARCHAR(64),
    country        CHAR(2) NOT NULL,
    postal_code    VARCHAR(20),
    risk_tier      VARCHAR(16) DEFAULT 'STANDARD',
    kyc_status     VARCHAR(16) DEFAULT 'VERIFIED',
    customer_since DATE NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_customers_updated_at ON customers(updated_at);
CREATE INDEX idx_customers_risk_tier ON customers(risk_tier);

-- Seed sample data
INSERT INTO customers (customer_id, first_name, last_name, email, country, customer_since)
VALUES
    ('CUST-100', 'Alice',  'Anderson', 'alice@example.com',  'US', '2022-01-15'),
    ('CUST-101', 'Bob',    'Brown',    'bob@example.com',    'US', '2021-06-20'),
    ('CUST-102', 'Carol',  'Chen',     'carol@example.com',  'DE', '2020-11-03'),
    ('CUST-103', 'David',  'Davies',   'david@example.com',  'GB', '2019-08-12'),
    ('CUST-104', 'Eve',    'Edwards',  'eve@example.com',    'FR', '2023-03-30'),
    ('CUST-105', 'Frank',  'Foster',   'frank@example.com',  'IN', '2022-07-19'),
    ('CUST-106', 'Grace',  'Garcia',   'grace@example.com',  'US', '2021-02-28'),
    ('CUST-107', 'Henry',  'Hill',     'henry@example.com',  'US', '2020-05-14'),
    ('CUST-108', 'Iris',   'Ivanov',   'iris@example.com',   'US', '2022-09-01'),
    ('CUST-109', 'James',  'Johnson',  'james@example.com',  'IT', '2018-12-25'),
    ('CUST-110', 'Karen',  'King',     'karen@example.com',  'US', '2023-01-07')
ON CONFLICT (customer_id) DO NOTHING;
