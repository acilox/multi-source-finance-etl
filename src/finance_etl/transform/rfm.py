"""RFM (Recency, Frequency, Monetary) customer segmentation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pandas as pd

from finance_etl.config.logging_config import get_logger
from finance_etl.models import CustomerSegment, RFMScore

logger = get_logger(__name__)


# Segment lookup table: (R, F, M) bucket -> CustomerSegment
# Based on industry-standard RFM segmentation playbook
def _classify_segment(r: int, f: int, m: int) -> CustomerSegment:
    if r >= 4 and f >= 4 and m >= 4:
        return CustomerSegment.CHAMPION
    if r >= 4 and f >= 3:
        return CustomerSegment.LOYAL
    if r >= 4 and f <= 2:
        return CustomerSegment.NEW
    if r == 3 and f >= 3:
        return CustomerSegment.POTENTIAL_LOYALIST
    if r == 3 and f <= 2:
        return CustomerSegment.PROMISING
    if r == 2 and f >= 3:
        return CustomerSegment.NEEDS_ATTENTION
    if r == 2 and f <= 2:
        return CustomerSegment.ABOUT_TO_SLEEP
    if r == 1 and f >= 3:
        return CustomerSegment.AT_RISK
    if r == 1 and m >= 4:
        return CustomerSegment.HIBERNATING
    return CustomerSegment.LOST


class RFMSegmenter:
    """Computes RFM scores from a transaction DataFrame.

    Required input columns:
        - customer_id (str)
        - transaction_timestamp (datetime)
        - amount_base (Decimal/float)
    """

    def __init__(self, as_of: datetime | None = None) -> None:
        self.as_of = as_of or datetime.utcnow()

    def segment(self, transactions_df: pd.DataFrame) -> list[RFMScore]:
        if transactions_df.empty:
            logger.info("rfm_no_data")
            return []

        df = transactions_df.copy()
        df["transaction_timestamp"] = pd.to_datetime(df["transaction_timestamp"])

        # Aggregate per customer
        agg = (
            df.groupby("customer_id")
            .agg(
                last_txn=("transaction_timestamp", "max"),
                frequency=("transaction_timestamp", "count"),
                monetary=("amount_base", "sum"),
            )
            .reset_index()
        )
        agg["recency_days"] = (self.as_of - agg["last_txn"]).dt.days.clip(lower=0)

        # Quintile scoring: 5 = best
        # For recency, lower is better, so invert quintile rank
        agg["r_score"] = pd.qcut(
            agg["recency_days"].rank(method="first", ascending=False),
            5,
            labels=[1, 2, 3, 4, 5],
        ).astype(int)
        agg["f_score"] = pd.qcut(
            agg["frequency"].rank(method="first"),
            5,
            labels=[1, 2, 3, 4, 5],
            duplicates="drop",
        ).astype(int)
        agg["m_score"] = pd.qcut(
            agg["monetary"].rank(method="first"),
            5,
            labels=[1, 2, 3, 4, 5],
            duplicates="drop",
        ).astype(int)

        out: list[RFMScore] = []
        computed_at = datetime.utcnow()
        for _, row in agg.iterrows():
            segment = _classify_segment(
                int(row["r_score"]), int(row["f_score"]), int(row["m_score"])
            )
            out.append(
                RFMScore(
                    customer_id=str(row["customer_id"]),
                    recency_days=int(row["recency_days"]),
                    frequency_count=int(row["frequency"]),
                    monetary_value=Decimal(str(row["monetary"])),
                    r_score=int(row["r_score"]),
                    f_score=int(row["f_score"]),
                    m_score=int(row["m_score"]),
                    rfm_combined=f"{int(row['r_score'])}{int(row['f_score'])}{int(row['m_score'])}",
                    segment=segment,
                    computed_at=computed_at,
                )
            )

        logger.info("rfm_segmented", customer_count=len(out))
        return out
