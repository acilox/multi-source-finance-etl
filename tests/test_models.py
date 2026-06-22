"""Tests for Pydantic models."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from finance_etl.models import Transaction, TransactionStatus, TransactionType


def test_transaction_validates_currency():
    with pytest.raises(ValidationError):
        Transaction(
            transaction_id="X",
            customer_id="C1",
            account_id="A1",
            transaction_type=TransactionType.DEBIT,
            status=TransactionStatus.POSTED,
            amount=Decimal("10"),
            currency="usd",  # lowercase — should fail
            transaction_timestamp=datetime.now(tz=UTC),
            source_system="test",
            source_extracted_at=datetime.now(tz=UTC),
        )


def test_transaction_rejects_negative_amount():
    with pytest.raises(ValidationError):
        Transaction(
            transaction_id="X",
            customer_id="C1",
            account_id="A1",
            transaction_type=TransactionType.DEBIT,
            status=TransactionStatus.POSTED,
            amount=Decimal("-10"),
            currency="USD",
            transaction_timestamp=datetime.now(tz=UTC),
            source_system="test",
            source_extracted_at=datetime.now(tz=UTC),
        )


def test_transaction_strips_whitespace():
    txn = Transaction(
        transaction_id="  TXN  ",
        customer_id="C1",
        account_id="A1",
        transaction_type=TransactionType.DEBIT,
        status=TransactionStatus.POSTED,
        amount=Decimal("10"),
        currency="USD",
        transaction_timestamp=datetime.now(tz=UTC),
        source_system="test",
        source_extracted_at=datetime.now(tz=UTC),
    )
    assert txn.transaction_id == "TXN"
