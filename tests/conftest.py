"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from finance_etl.models import (
    FXRate,
    Transaction,
    TransactionStatus,
    TransactionType,
)


@pytest.fixture
def sample_transaction() -> Transaction:
    return Transaction(
        transaction_id="TXN-0001",
        customer_id="CUST-100",
        account_id="ACCT-200",
        transaction_type=TransactionType.DEBIT,
        status=TransactionStatus.POSTED,
        amount=Decimal("250.00"),
        currency="USD",
        transaction_timestamp=datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC),
        posted_timestamp=datetime(2026, 5, 20, 12, 0, 5, tzinfo=UTC),
        merchant_id="MERCH-1",
        merchant_category="GROCERY",
        merchant_country="US",
        description="Grocery store purchase",
        reference_number="REF-X-9001",
        source_system="oracle_core_banking",
        source_extracted_at=datetime(2026, 5, 20, 12, 0, 30, tzinfo=UTC),
    )


@pytest.fixture
def fx_rates_usd_base() -> list[FXRate]:
    fetched = datetime(2026, 5, 20, 0, 0, 0, tzinfo=UTC)
    return [
        FXRate(
            base_currency="USD",
            quote_currency="EUR",
            rate=Decimal("0.92"),
            as_of_date=date(2026, 5, 20),
            source="test",
            fetched_at=fetched,
        ),
        FXRate(
            base_currency="USD",
            quote_currency="GBP",
            rate=Decimal("0.79"),
            as_of_date=date(2026, 5, 20),
            source="test",
            fetched_at=fetched,
        ),
        FXRate(
            base_currency="USD",
            quote_currency="INR",
            rate=Decimal("83.2"),
            as_of_date=date(2026, 5, 20),
            source="test",
            fetched_at=fetched,
        ),
    ]


@pytest.fixture
def burst_transactions() -> list[Transaction]:
    """15 transactions for one customer within 10 minutes — should trigger velocity rule."""
    base = datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    return [
        Transaction(
            transaction_id=f"BURST-{i:03d}",
            customer_id="CUST-VEL",
            account_id="ACCT-VEL-1",
            transaction_type=TransactionType.DEBIT,
            status=TransactionStatus.POSTED,
            amount=Decimal("50.00"),
            currency="USD",
            transaction_timestamp=base + timedelta(seconds=i * 30),
            posted_timestamp=base + timedelta(seconds=i * 30 + 1),
            merchant_id="MERCH-V",
            merchant_country="US",
            description="Test burst",
            reference_number=f"REF-V-{i}",
            source_system="test",
            source_extracted_at=base,
        )
        for i in range(15)
    ]
