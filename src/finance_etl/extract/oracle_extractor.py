"""Oracle transaction extractor with incremental CDC."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Iterator

from finance_etl.config.logging_config import get_logger
from finance_etl.config.settings import get_settings
from finance_etl.models import Transaction, TransactionStatus, TransactionType
from finance_etl.utils.metrics import metrics
from finance_etl.utils.retries import retry_with_backoff

logger = get_logger(__name__)

# NOTE: oracledb is imported lazily to keep this module importable without the driver.
EXTRACT_TRANSACTIONS_SQL = """
SELECT
    txn_id,
    customer_id,
    account_id,
    txn_type,
    txn_status,
    amount,
    currency,
    txn_timestamp,
    posted_timestamp,
    merchant_id,
    merchant_category,
    merchant_country,
    description,
    reference_number,
    last_updated
FROM finance_etl.transactions
WHERE last_updated > :watermark
  AND last_updated <= :as_of
ORDER BY last_updated ASC
"""


class OracleTransactionExtractor:
    """Reads transactions from Oracle using a watermark column."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._connection = None

    def __enter__(self) -> "OracleTransactionExtractor":
        self._connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    @retry_with_backoff(max_attempts=3, initial_wait=2.0)
    def _connect(self) -> None:
        """Open Oracle connection. Lazy import keeps the module importable."""
        try:
            import oracledb  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError("oracledb driver not installed") from e

        self._connection = oracledb.connect(
            user=self.settings.oracle.oracle_user,
            password=self.settings.oracle.oracle_password.get_secret_value(),
            dsn=self.settings.oracle.dsn,
        )
        logger.info("oracle_connected", dsn=self.settings.oracle.dsn)

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
            logger.info("oracle_closed")

    def extract(
        self,
        watermark: datetime,
        as_of: datetime,
        batch_size: int | None = None,
    ) -> Iterator[Transaction]:
        """Yield Transaction objects between (watermark, as_of].

        Args:
            watermark: Lower bound on last_updated (exclusive).
            as_of: Upper bound (inclusive).
            batch_size: Cursor fetch size; defaults to pipeline setting.
        """
        batch_size = batch_size or self.settings.pipeline.pipeline_batch_size
        if self._connection is None:
            self._connect()

        assert self._connection is not None
        cursor = self._connection.cursor()
        cursor.arraysize = batch_size

        logger.info(
            "oracle_extract_start",
            watermark=watermark.isoformat(),
            as_of=as_of.isoformat(),
            batch_size=batch_size,
        )

        cursor.execute(
            EXTRACT_TRANSACTIONS_SQL,
            watermark=watermark,
            as_of=as_of,
        )

        count = 0
        for row in cursor:
            try:
                txn = self._row_to_transaction(row)
                count += 1
                metrics.records_extracted.labels(source="oracle").inc()
                yield txn
            except Exception as e:
                logger.warning("oracle_row_skipped", error=str(e), row_index=count)
                metrics.pipeline_errors.labels(stage="extract", error_type="row_parse").inc()

        cursor.close()
        logger.info("oracle_extract_complete", record_count=count)

    @staticmethod
    def _row_to_transaction(row: tuple) -> Transaction:
        """Convert a DB row to a Transaction Pydantic model."""
        return Transaction(
            transaction_id=str(row[0]),
            customer_id=str(row[1]),
            account_id=str(row[2]),
            transaction_type=TransactionType(row[3]),
            status=TransactionStatus(row[4]),
            amount=Decimal(str(row[5])),
            currency=row[6],
            transaction_timestamp=row[7],
            posted_timestamp=row[8],
            merchant_id=row[9],
            merchant_category=row[10],
            merchant_country=row[11],
            description=row[12],
            reference_number=row[13],
            source_system="oracle_core_banking",
            source_extracted_at=datetime.utcnow(),
        )
