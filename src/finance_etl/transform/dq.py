"""Data quality scoring engine.

Computes per-record DQ scores across 4 dimensions:
- Completeness: required fields populated
- Validity: values within expected ranges/formats
- Uniqueness: deduplication tracking
- Consistency: cross-field validations
"""

from __future__ import annotations

from datetime import UTC, datetime

from finance_etl.config.logging_config import get_logger
from finance_etl.models import Transaction
from finance_etl.utils.metrics import metrics

logger = get_logger(__name__)


class DataQualityScorer:
    """Per-record DQ scoring. Returns a score in [0, 1] and list of issue codes."""

    REQUIRED_FIELDS = (
        "transaction_id",
        "customer_id",
        "account_id",
        "amount",
        "currency",
        "transaction_timestamp",
        "source_system",
    )

    def __init__(self) -> None:
        self._seen_ids: set[str] = set()

    def score(self, txn: Transaction) -> tuple[float, list[str]]:
        issues: list[str] = []

        # ---- Completeness ----
        completeness = 1.0
        missing = []
        for field in self.REQUIRED_FIELDS:
            value = getattr(txn, field, None)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(field)
        if missing:
            completeness = 1.0 - (len(missing) / len(self.REQUIRED_FIELDS))
            issues.extend([f"DQ-COMPLETENESS-MISSING_{f.upper()}" for f in missing])
            for f in missing:
                metrics.dq_failures.labels(check=f"completeness_{f}").inc()

        # ---- Validity ----
        validity = 1.0
        if txn.amount <= 0:
            issues.append("DQ-VALIDITY-NON_POSITIVE_AMOUNT")
            validity -= 0.25
            metrics.dq_failures.labels(check="validity_amount").inc()
        if txn.currency and (len(txn.currency) != 3 or not txn.currency.isalpha()):
            issues.append("DQ-VALIDITY-INVALID_CURRENCY")
            validity -= 0.25
            metrics.dq_failures.labels(check="validity_currency").inc()
        if txn.transaction_timestamp is not None:
            ts = txn.transaction_timestamp
            if ts.tzinfo is None:  # treat naive timestamps as UTC
                ts = ts.replace(tzinfo=UTC)
            if ts > datetime.now(UTC):
                issues.append("DQ-VALIDITY-FUTURE_TIMESTAMP")
                validity -= 0.25
                metrics.dq_failures.labels(check="validity_timestamp").inc()
        validity = max(0.0, validity)

        # ---- Uniqueness ----
        uniqueness = 1.0
        if txn.transaction_id in self._seen_ids:
            issues.append("DQ-UNIQUENESS-DUPLICATE_TXN_ID")
            uniqueness = 0.0
            metrics.dq_failures.labels(check="uniqueness").inc()
        else:
            self._seen_ids.add(txn.transaction_id)

        # ---- Consistency ----
        consistency = 1.0
        if txn.posted_timestamp is not None and txn.posted_timestamp < txn.transaction_timestamp:
            issues.append("DQ-CONSISTENCY-POSTED_BEFORE_TXN")
            consistency -= 0.5
            metrics.dq_failures.labels(check="consistency_ts_order").inc()

        # Composite score (weighted average)
        score = 0.35 * completeness + 0.30 * validity + 0.20 * uniqueness + 0.15 * consistency
        return max(0.0, min(1.0, score)), issues
