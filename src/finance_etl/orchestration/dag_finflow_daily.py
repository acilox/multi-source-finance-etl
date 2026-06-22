"""Airflow DAG: finance_etl_daily.

End-to-end orchestration of the Finance ETL pipeline:
1. Extract: Oracle txns, FX rates, SFTP files, Customer master
2. Transform: Currency normalize -> Fraud scoring -> SOX validation -> DQ scoring
3. Load: Snowflake facts/dims, S3 parquet, Redis fraud alerts
4. Validate: Run GE suite on enriched output
"""

from __future__ import annotations

from datetime import datetime, timedelta

try:
    from airflow import DAG  # type: ignore[import-not-found]
    from airflow.operators.python import PythonOperator  # type: ignore[import-not-found]
    from airflow.sensors.filesystem import FileSensor  # type: ignore[import-not-found]

    AIRFLOW_AVAILABLE = True
except ImportError:
    AIRFLOW_AVAILABLE = False


DEFAULT_ARGS = {
    "owner": "finance_etl-data-eng",
    "depends_on_past": False,
    "email": ["alerts@finance_etl.example.com"],
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=2),
}


def _extract_oracle(**context):
    from finance_etl.extract import OracleTransactionExtractor

    execution_date = context["data_interval_end"]
    watermark = context["data_interval_start"]
    with OracleTransactionExtractor() as ext:
        txns = list(ext.extract(watermark=watermark, as_of=execution_date))
    context["ti"].xcom_push(key="oracle_txn_count", value=len(txns))


def _extract_fx_rates(**context):
    from finance_etl.extract import FXRateExtractor

    as_of = context["data_interval_end"].date()
    with FXRateExtractor() as ext:
        rates = ext.fetch_rates(as_of_date=as_of)
    context["ti"].xcom_push(key="fx_rate_count", value=len(rates))


def _extract_customers(**context):
    from finance_etl.extract import PostgresCustomerExtractor

    watermark = context["data_interval_start"]
    with PostgresCustomerExtractor() as ext:
        customers = list(ext.extract(watermark=watermark))
    context["ti"].xcom_push(key="customer_count", value=len(customers))


def _run_pipeline_stage(stage: str, **context) -> None:
    from finance_etl.main import run_stage

    run_stage(stage, run_date=context["data_interval_end"].date())


if AIRFLOW_AVAILABLE:
    with DAG(
        dag_id="finance_etl_daily",
        description="End-to-end daily Finance ETL ETL",
        default_args=DEFAULT_ARGS,
        schedule="0 2 * * *",  # 02:00 UTC daily
        start_date=datetime(2026, 1, 1),
        catchup=False,
        max_active_runs=1,
        tags=["finance_etl", "etl", "finance"],
    ) as dag:
        extract_oracle = PythonOperator(
            task_id="extract_oracle_txns",
            python_callable=_extract_oracle,
        )
        extract_fx = PythonOperator(
            task_id="extract_fx_rates",
            python_callable=_extract_fx_rates,
        )
        sftp_sensor = FileSensor(
            task_id="wait_for_sftp_file",
            filepath="data/raw/sftp/",
            poke_interval=300,
            timeout=3600,
            mode="reschedule",
        )
        extract_customers = PythonOperator(
            task_id="extract_customer_master",
            python_callable=_extract_customers,
        )

        transform_currency = PythonOperator(
            task_id="transform_normalize_currency",
            python_callable=_run_pipeline_stage,
            op_kwargs={"stage": "currency"},
        )
        transform_fraud = PythonOperator(
            task_id="transform_fraud_scoring",
            python_callable=_run_pipeline_stage,
            op_kwargs={"stage": "fraud"},
        )
        transform_sox = PythonOperator(
            task_id="transform_sox_validation",
            python_callable=_run_pipeline_stage,
            op_kwargs={"stage": "sox"},
        )
        transform_rfm = PythonOperator(
            task_id="transform_rfm_segmentation",
            python_callable=_run_pipeline_stage,
            op_kwargs={"stage": "rfm"},
        )

        load_snowflake = PythonOperator(
            task_id="load_snowflake",
            python_callable=_run_pipeline_stage,
            op_kwargs={"stage": "load_snowflake"},
        )
        load_s3 = PythonOperator(
            task_id="load_s3_parquet",
            python_callable=_run_pipeline_stage,
            op_kwargs={"stage": "load_s3"},
        )
        publish_alerts = PythonOperator(
            task_id="publish_fraud_alerts",
            python_callable=_run_pipeline_stage,
            op_kwargs={"stage": "publish_alerts"},
        )
        dq_check = PythonOperator(
            task_id="data_quality_validation",
            python_callable=_run_pipeline_stage,
            op_kwargs={"stage": "dq"},
        )

        # Dependencies
        [extract_oracle, extract_fx, sftp_sensor, extract_customers] >> transform_currency
        transform_currency >> transform_fraud >> transform_sox >> transform_rfm
        transform_rfm >> [load_snowflake, load_s3, publish_alerts] >> dq_check
