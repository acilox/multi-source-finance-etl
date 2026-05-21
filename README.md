# multi-source-finance-etl

A reference implementation of a daily financial ETL: pulls transactions
from a core banking Oracle DB, FX rates from a REST API, partner
reconciliation files from SFTP and the customer master from Postgres,
then loads a normalised, fraud-scored Snowflake warehouse with SOX
controls and RFM segmentation applied along the way.

## Problem domain

Financial institutions typically consolidate accounting and risk inputs
from several upstream systems on a fixed schedule. The patterns here
cover the operational requirements common to those builds: incremental
extraction, multi-currency normalisation, rules-based fraud detection,
SCD-2 dimension management, and data-quality gates ahead of the
warehouse.

## Sources and targets

```
sources                                targets
-------                                -------
oracle (core banking)        --->      snowflake (FACT_TRANSACTION,
postgres (customer master)   --->                 DIM_CUSTOMER, ...)
sftp (partner files)         --->      s3 (parquet, hive-partitioned)
openexchangerates.org API    --->      redis (fraud alert stream)
```

## Layout

```
src/finance_etl/
  config/        pydantic-settings, structlog setup
  extract/       one module per source system
  transform/     currency normalisation, fraud rules, SOX checks, RFM, DQ
  load/          snowflake (incl. SCD-2 MERGE), s3 parquet, redis streams
  quality/       great-expectations suite wired into the pipeline
  orchestration/ Airflow DAG (finance_etl_daily)
  models/        pydantic schemas
  utils/         metrics, retry helper
  main.py        Typer CLI (run, fraud-scan, validate)

tests/           pytest with shared fixtures
sql/             Snowflake DDL plus Postgres init for local docker-compose
data/sample/     ~25 sample transactions and an FX rate sheet
docs/            architecture.md, business_rules.md
```

## Fraud rules

Four independent rules combined into a single risk score (max across
rules). Thresholds are configurable via environment variables so risk
teams can tune them without code changes.

| rule          | trips when                                | severity |
| ------------- | ----------------------------------------- | -------- |
| velocity      | >= 10 transactions in 1 hour per customer | HIGH     |
| high_value    | amount in base ccy >= 10,000              | MEDIUM   |
| geo_velocity  | two countries inside a 1h window          | CRITICAL |
| zscore        | abs(z) >= 3 vs the customer's history     | HIGH     |

## SOX controls

Six controls are evaluated per row before load. Failures are tagged on
the row rather than blocked; the DQ layer determines hard-fail
behaviour. See `docs/business_rules.md` for the full list and
remediation paths.

## Running locally

```
cp .env.example .env
make install
make docker-up        # postgres, redis, minio
make run              # runs the demo against data/sample/
```

CLI:

```
finance_etl run --source sample --date today
finance_etl fraud-scan --input data/sample/transactions.csv
finance_etl validate --input data/sample/enriched.csv
```

## Stack

Python 3.11, pandas, polars, snowflake-connector-python, oracledb,
psycopg2, httpx + tenacity, paramiko, boto3, redis, pydantic,
structlog, great-expectations, prometheus-client, Airflow 2.x.

## Design notes

- The z-score rule is implemented with an in-memory rolling window per
  customer. For multi-worker deployments, swap the in-memory state for
  a Redis-backed structure with the same interface.
- SFTP ingestion uses polling. Where the partner side supports push
  notifications, replace the poller with an event-driven trigger.
- Great Expectations runs after the transform layer. Adding a second
  GE pass before currency normalisation catches malformed currency
  codes earlier in the pipeline.

## About this code

Open-source companion to the data infrastructure work done by
[acilox](https://github.com/acilox). For paid implementation,
hardening, or extension of these patterns into a production environment,
open an issue.
