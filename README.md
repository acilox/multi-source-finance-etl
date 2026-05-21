# multi-source-finance-etl

A daily ETL that consolidates transactions from a core banking Oracle DB,
FX rates from a REST API, partner reconciliation files from SFTP, and the
customer master from Postgres, into a Snowflake warehouse with fraud
scoring, SOX checks and RFM segmentation applied along the way.

## Problem

The accounting and risk teams were stitching together CSV exports from
half a dozen places every morning. We replaced that with a pipeline that
runs at 02:00 UTC, populates `fact_transaction` and `dim_customer`
(SCD-2), and pushes fraud alerts to a Redis stream so the ops dashboard
picks them up in near real time.

## Sources & targets

```
sources                                targets
-------                                -------
oracle (core banking)        --->      snowflake (FACT_TRANSACTION,
postgres (customer master)   --->                 DIM_CUSTOMER, ...)
sftp (partner files)         --->      s3 (parquet, hive-partitioned)
openexchangerates.org API    --->      redis (fraud alert stream)
```

## What's in here

```
src/finance_etl/
  config/        pydantic-settings + structlog setup
  extract/       one module per source system
  transform/     currency normalisation, fraud rules, SOX checks, RFM, DQ
  load/          snowflake (incl. SCD-2 MERGE), s3 parquet, redis streams
  quality/       great-expectations suite wired into the pipeline
  orchestration/ Airflow DAG (finance_etl_daily)
  models/        pydantic schemas
  utils/         metrics, retry helper
  main.py        Typer CLI (run, fraud-scan, validate)

tests/           pytest, with shared fixtures
sql/             Snowflake DDL + Postgres init for local docker-compose
data/sample/     ~25 sample txns and an FX rate sheet, used by `make run`
docs/            architecture.md, business_rules.md
```

## Fraud rules

Four rules combined into a single risk score (max across rules). The
thresholds live in `.env`, so risk can tune them without a deploy.

| rule          | trips when                                | severity |
| ------------- | ----------------------------------------- | -------- |
| velocity      | >= 10 txns/hour for a customer            | HIGH     |
| high_value    | amount in base ccy >= 10,000              | MEDIUM   |
| geo_velocity  | two countries in a 1h window              | CRITICAL |
| zscore        | z >= 3 vs the customer's running history  | HIGH     |

## SOX controls

Each transaction is checked against six controls before it's allowed
into the warehouse. Misses are tagged on the row, not blocked — the
DQ layer decides what's hard-fail. See `docs/business_rules.md`.

## Running locally

```
cp .env.example .env
make install
make docker-up        # postgres, redis, minio
make run              # runs the demo against data/sample/
```

The CLI:

```
finance_etl run --source sample --date today
finance_etl fraud-scan --input data/sample/transactions.csv
finance_etl validate --input data/sample/enriched.csv
```

## Stack

Python 3.11, pandas, polars, snowflake-connector-python, oracledb,
psycopg2, httpx + tenacity, paramiko, boto3, redis, pydantic,
structlog, great-expectations, prometheus-client, Airflow 2.x.

## Things I'd still improve

- The `zscore` rule uses an in-memory rolling window per customer. Fine
  at our volume but it'll need to move to Redis if we want to scale
  beyond a single worker.
- The SFTP fetcher polls. Switching to inotify-style triggers on the
  partner side is on the wishlist.
- Great Expectations runs after the transform — we should probably gate
  *before* the FX normalisation step too, since bad currency codes
  surface late right now.
