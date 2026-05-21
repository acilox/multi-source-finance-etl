"""PostgreSQL customer master extractor."""

from __future__ import annotations

from datetime import datetime
from typing import Iterator

from sqlalchemy import create_engine, text

from finance_etl.config.logging_config import get_logger
from finance_etl.config.settings import get_settings
from finance_etl.models import Customer
from finance_etl.utils.metrics import metrics
from finance_etl.utils.retries import retry_with_backoff

logger = get_logger(__name__)


CUSTOMER_QUERY = """
SELECT
    customer_id,
    first_name,
    last_name,
    email,
    phone,
    date_of_birth,
    address_line1,
    city,
    state,
    country,
    postal_code,
    risk_tier,
    kyc_status,
    customer_since,
    created_at,
    updated_at
FROM customers
WHERE updated_at > :watermark
ORDER BY updated_at ASC
"""


class PostgresCustomerExtractor:
    """Extracts customer master data from PostgreSQL."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.engine = None

    def __enter__(self) -> "PostgresCustomerExtractor":
        self._connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    @retry_with_backoff(max_attempts=3, initial_wait=2.0)
    def _connect(self) -> None:
        self.engine = create_engine(
            self.settings.postgres.url, pool_pre_ping=True, pool_size=5
        )
        logger.info("postgres_engine_created")

    def close(self) -> None:
        if self.engine is not None:
            self.engine.dispose()
            self.engine = None
            logger.info("postgres_engine_disposed")

    def extract(self, watermark: datetime) -> Iterator[Customer]:
        """Yield customer records updated after watermark."""
        if self.engine is None:
            self._connect()
        assert self.engine is not None

        logger.info("postgres_extract_start", watermark=watermark.isoformat())

        with self.engine.connect() as conn:
            result = conn.execute(text(CUSTOMER_QUERY), {"watermark": watermark})
            count = 0
            for row in result.mappings():
                try:
                    customer = Customer(**dict(row))
                    count += 1
                    metrics.records_extracted.labels(source="postgres").inc()
                    yield customer
                except Exception as e:
                    logger.warning("postgres_row_skipped", error=str(e), row_index=count)
                    metrics.pipeline_errors.labels(stage="extract", error_type="row_parse").inc()

        logger.info("postgres_extract_complete", record_count=count)
