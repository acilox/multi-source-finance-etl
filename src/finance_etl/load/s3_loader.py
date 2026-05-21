"""S3 loader for Parquet data lake with Hive partitioning."""

from __future__ import annotations

from datetime import date
from typing import Iterable

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from finance_etl.config.logging_config import get_logger
from finance_etl.config.settings import get_settings
from finance_etl.models import EnrichedTransaction
from finance_etl.utils.metrics import metrics
from finance_etl.utils.retries import retry_with_backoff

logger = get_logger(__name__)


class S3Loader:
    """Writes Parquet data to S3 with Hive-style partitioning by date."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._s3 = None

    def __enter__(self) -> "S3Loader":
        self._connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        # boto3 client doesn't need explicit close
        pass

    @retry_with_backoff(max_attempts=3, initial_wait=2.0)
    def _connect(self) -> None:
        try:
            import boto3  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError("boto3 not installed") from e

        self._s3 = boto3.client(
            "s3",
            aws_access_key_id=self.settings.aws.aws_access_key_id.get_secret_value(),
            aws_secret_access_key=self.settings.aws.aws_secret_access_key.get_secret_value(),
            region_name=self.settings.aws.aws_region,
        )
        logger.info("s3_client_initialized", region=self.settings.aws.aws_region)

    def load_transactions(
        self, records: Iterable[EnrichedTransaction], partition_date: date
    ) -> int:
        """Write enriched transactions to S3 as partitioned Parquet."""
        if self._s3 is None:
            self._connect()
        assert self._s3 is not None

        df = pd.DataFrame([r.model_dump() for r in records])
        if df.empty:
            logger.info("s3_no_records")
            return 0

        # Hive partitioning: prefix/year=YYYY/month=MM/day=DD/part-001.parquet
        key = (
            f"{self.settings.aws.s3_prefix}"
            f"transactions/"
            f"year={partition_date.year:04d}/"
            f"month={partition_date.month:02d}/"
            f"day={partition_date.day:02d}/"
            f"part-{partition_date.strftime('%Y%m%d')}.parquet"
        )

        # Convert to Arrow & serialize to bytes
        table = pa.Table.from_pandas(df)
        sink = pa.BufferOutputStream()
        pq.write_table(table, sink, compression="snappy")
        buf = sink.getvalue().to_pybytes()

        self._s3.put_object(
            Bucket=self.settings.aws.s3_bucket,
            Key=key,
            Body=buf,
            ContentType="application/octet-stream",
            Metadata={
                "record_count": str(len(df)),
                "partition_date": partition_date.isoformat(),
            },
        )

        metrics.records_loaded.labels(target="s3").inc(len(df))
        logger.info(
            "s3_loaded",
            bucket=self.settings.aws.s3_bucket,
            key=key,
            rows=len(df),
            bytes=len(buf),
        )
        return len(df)
