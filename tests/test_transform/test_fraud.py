"""Tests for FraudScoringEngine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from finance_etl.models import Transaction, TransactionStatus, TransactionType
from finance_etl.transform import FraudScoringEngine


def test_normal_transaction_low_score(sample_transaction):
    engine = FraudScoringEngine()
    score, rules = engine.score(sample_transaction, Decimal("250.00"))

    assert score < 0.5
    assert not any(r.triggered for r in rules)


def test_high_value_transaction_triggers_rule(sample_transaction):
    engine = FraudScoringEngine()
    score, rules = engine.score(sample_transaction, Decimal("50000.00"))

    high_value_rule = next(r for r in rules if r.rule_name == "high_value")
    assert high_value_rule.triggered
    assert score > 0.0


def test_velocity_burst_triggers(burst_transactions):
    engine = FraudScoringEngine()
    # Process all 15 burst transactions; the later ones should hit velocity threshold (10/hr)
    scores = []
    for txn in burst_transactions:
        s, _ = engine.score(txn, Decimal("50.00"))
        scores.append(s)

    # The last few should have higher velocity scores
    assert max(scores) >= 0.5


def test_geo_velocity_cross_country():
    engine = FraudScoringEngine()
    base = datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)

    txn1 = Transaction(
        transaction_id="T1",
        customer_id="C1",
        account_id="A1",
        transaction_type=TransactionType.DEBIT,
        status=TransactionStatus.POSTED,
        amount=Decimal("100"),
        currency="USD",
        transaction_timestamp=base,
        merchant_country="US",
        reference_number="REF-1",
        source_system="test",
        source_extracted_at=base,
    )
    txn2 = Transaction(
        transaction_id="T2",
        customer_id="C1",
        account_id="A1",
        transaction_type=TransactionType.DEBIT,
        status=TransactionStatus.POSTED,
        amount=Decimal("100"),
        currency="USD",
        transaction_timestamp=base + timedelta(minutes=30),
        merchant_country="IN",
        reference_number="REF-2",
        source_system="test",
        source_extracted_at=base,
    )

    engine.score(txn1, Decimal("100"))
    score, rules = engine.score(txn2, Decimal("100"))

    geo_rule = next(r for r in rules if r.rule_name == "geo_velocity")
    assert geo_rule.triggered
    assert score == 1.0  # critical severity


def test_alert_creation(sample_transaction):
    engine = FraudScoringEngine()
    score, rules = engine.score(sample_transaction, Decimal("50000.00"))
    alert = engine.build_alert(sample_transaction, score, [r for r in rules if r.triggered])

    assert alert.transaction_id == sample_transaction.transaction_id
    assert 0.0 <= alert.risk_score <= 1.0
    assert alert.metadata["currency"] == "USD"
