"""Snowflake loader for facts & SCD Type 2 dimensions."""

from __future__ import annotations

from typing import Iterable

import pandas as pd

from finance_etl.config.logging_config import get_logger
from finance_etl.config.settings import get_settings
from finance_etl.models import Customer, EnrichedTransaction
from finance_etl.utils.metrics import metrics
from finance_etl.utils.retries import retry_with_backoff

logger = get_logger(__name__)


MERGE_DIM_CUSTOMER_SQL = """
MERGE INTO dim_customer AS tgt
USING staging_customer AS src
ON tgt.customer_id = src.customer_id AND tgt.is_current = TRUE
WHEN MATCHED AND (
       tgt.first_name <> src.first_name
    OR tgt.last_name <> src.last_name
    OR tgt.email <> src.email
    OR tgt.address_line1 <> src.address_line1
    OR tgt.risk_tier <> src.risk_tier
    OR tgt.kyc_status <> src.kyc_status
) THEN UPDATE SET
    effective_to = CURRENT_TIMESTAMP(),
    is_current = FALSE
WHEN NOT MATCHED THEN INSERT (
    customer_id, first_name, last_name, email, phone,
    date_of_birth, address_line1, city, state, country, postal_code,
    risk_tier, kyc_status, customer_since,
    effective_from, effective_to, is_current
) VALUES (
    src.customer_id, src.first_name, src.last_name, src.email, src.phone,
    src.date_of_birth, src.address_line1, src.city, src.state, src.country, src.postal_code,
    src.risk_tier, src.kyc_status, src.customer_since,
    CURRENT_TIMESTAMP(), NULL, TRUE
);
"""


class SnowflakeLoader:
    """Loads enriched data into a Snowflake star schema with SCD Type 2 dimensions."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._conn = None

    def __enter__(self) -> "SnowflakeLoader":
        self._connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    @retry_with_backoff(max_attempts=3, initial_wait=2.0)
    def _connect(self) -> None:
        try:
            import snowflake.connector  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError("snowflake-connector-python not installed") from e

        s = self.settings.snowflake
        self._conn = snowflake.connector.connect(
            account=s.snowflake_account,
            user=s.snowflake_user,
            password=s.snowflake_password.get_secret_value(),
            warehouse=s.snowflake_warehouse,
            database=s.snowflake_database,
            schema=s.snowflake_schema,
            role=s.snowflake_role,
        )
        logger.info("snowflake_connected", account=s.snowflake_account)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.info("snowflake_closed")

    def load_facts(self, records: Iterable[EnrichedTransaction]) -> int:
        """Insert enriched transactions into FACT_TRANSACTION."""
        if self._conn is None:
            self._connect()
        assert self._conn is not None

        df = pd.DataFrame([r.model_dump() for r in records])
        if df.empty:
            logger.info("snowflake_facts_no_records")
            return 0

        # write_pandas is bulk-loaded via internal staging
        from snowflake.connector.pandas_tools import write_pandas  # type: ignore[import-not-found]

        success, nchunks, nrows, _ = write_pandas(
            self._conn,
            df,
            table_name="FACT_TRANSACTION",
            quote_identifiers=False,
            auto_create_table=False,
            overwrite=False,
        )
        if not success:
            raise RuntimeError("write_pandas to FACT_TRANSACTION failed")

        metrics.records_loaded.labels(target="snowflake_facts").inc(nrows)
        logger.info("snowflake_facts_loaded", chunks=nchunks, rows=nrows)
        return nrows

    def load_customer_scd2(self, customers: Iterable[Customer]) -> int:
        """Load customer dimension with SCD Type 2 logic via MERGE."""
        if self._conn is None:
            self._connect()
        assert self._conn is not None

        df = pd.DataFrame([c.model_dump() for c in customers])
        if df.empty:
            return 0

        from snowflake.connector.pandas_tools import write_pandas  # type: ignore[import-not-found]

        # Stage to STAGING_CUSTOMER (truncate-and-load)
        cursor = self._conn.cursor()
        cursor.execute("TRUNCATE TABLE IF EXISTS staging_customer")
        write_pandas(self._conn, df, table_name="STAGING_CUSTOMER", quote_identifiers=False)

        # Apply SCD2 merge
        cursor.execute(MERGE_DIM_CUSTOMER_SQL)
        merged = cursor.rowcount or 0
        cursor.close()

        metrics.records_loaded.labels(target="snowflake_dim_customer").inc(merged)
        logger.info("snowflake_customer_scd2_merged", rows=merged)
        return merged
