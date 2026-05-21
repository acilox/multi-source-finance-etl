-- ============================================================
-- Finance ETL Snowflake DDL — Star Schema
-- ============================================================

CREATE DATABASE IF NOT EXISTS FINANCE_ETL_DW;
USE DATABASE FINANCE_ETL_DW;
CREATE SCHEMA IF NOT EXISTS PUBLIC;

-- ============================================================
-- DIMENSION: dim_customer (SCD Type 2)
-- ============================================================
CREATE TABLE IF NOT EXISTS dim_customer (
    customer_sk        NUMBER AUTOINCREMENT PRIMARY KEY,
    customer_id        VARCHAR(64)  NOT NULL,
    first_name         VARCHAR(128),
    last_name          VARCHAR(128),
    email              VARCHAR(256),
    phone              VARCHAR(32),
    date_of_birth      DATE,
    address_line1      VARCHAR(256),
    city               VARCHAR(128),
    state              VARCHAR(64),
    country            CHAR(2),
    postal_code        VARCHAR(20),
    risk_tier          VARCHAR(16),
    kyc_status         VARCHAR(16),
    customer_since     DATE,
    effective_from     TIMESTAMP_NTZ NOT NULL,
    effective_to       TIMESTAMP_NTZ,
    is_current         BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS staging_customer LIKE dim_customer;

-- ============================================================
-- DIMENSION: dim_merchant
-- ============================================================
CREATE TABLE IF NOT EXISTS dim_merchant (
    merchant_sk        NUMBER AUTOINCREMENT PRIMARY KEY,
    merchant_id        VARCHAR(64) UNIQUE NOT NULL,
    merchant_name      VARCHAR(256),
    merchant_category  VARCHAR(64),
    merchant_country   CHAR(2),
    is_active          BOOLEAN DEFAULT TRUE
);

-- ============================================================
-- DIMENSION: dim_currency
-- ============================================================
CREATE TABLE IF NOT EXISTS dim_currency (
    currency_code      CHAR(3) PRIMARY KEY,
    currency_name      VARCHAR(64),
    decimal_places     NUMBER DEFAULT 2
);

-- ============================================================
-- DIMENSION: dim_time (calendar)
-- ============================================================
CREATE TABLE IF NOT EXISTS dim_time (
    date_key           DATE PRIMARY KEY,
    year               NUMBER,
    quarter            NUMBER,
    month              NUMBER,
    day                NUMBER,
    day_of_week        NUMBER,
    is_weekend         BOOLEAN,
    is_holiday         BOOLEAN
);

-- ============================================================
-- FACT: fact_transaction
-- ============================================================
CREATE TABLE IF NOT EXISTS fact_transaction (
    transaction_id          VARCHAR(64) PRIMARY KEY,
    customer_sk             NUMBER,
    merchant_sk             NUMBER,
    transaction_date_key    DATE,
    transaction_type        VARCHAR(16),
    status                  VARCHAR(16),
    original_amount         NUMBER(18, 4),
    original_currency       CHAR(3),
    amount_base             NUMBER(18, 4),
    base_currency           CHAR(3),
    fx_rate_used            NUMBER(18, 6),
    transaction_timestamp   TIMESTAMP_TZ,
    posted_timestamp        TIMESTAMP_TZ,
    fraud_risk_score        NUMBER(5, 4),
    fraud_triggered_rules   VARCHAR,    -- JSON array
    sox_compliant           BOOLEAN,
    sox_violations          VARCHAR,    -- JSON array
    dq_score                NUMBER(5, 4),
    dq_issues               VARCHAR,    -- JSON array
    source_system           VARCHAR(32),
    pipeline_run_id         VARCHAR(64),
    enriched_at             TIMESTAMP_TZ
)
CLUSTER BY (transaction_date_key);

-- ============================================================
-- FACT: fact_fraud_alert
-- ============================================================
CREATE TABLE IF NOT EXISTS fact_fraud_alert (
    alert_id           VARCHAR(64) PRIMARY KEY,
    transaction_id     VARCHAR(64),
    customer_sk        NUMBER,
    risk_score         NUMBER(5, 4),
    triggered_rules    VARCHAR,
    alerted_at         TIMESTAMP_TZ
);
