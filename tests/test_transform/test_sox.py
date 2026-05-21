"""Tests for SOXValidator."""

from __future__ import annotations

from decimal import Decimal

from finance_etl.transform import SOXValidator


def test_compliant_transaction(sample_transaction):
    validator = SOXValidator()
    compliant, violations = validator.validate(sample_transaction, Decimal("250.00"))
    assert compliant
    assert violations == []


def test_missing_reference_number_violates(sample_transaction):
    sample_transaction.reference_number = None
    validator = SOXValidator()
    compliant, violations = validator.validate(sample_transaction, Decimal("250.00"))
    assert not compliant
    assert "CTRL-001-MISSING_REFERENCE_NUMBER" in violations


def test_material_transaction_needs_merchant(sample_transaction):
    sample_transaction.merchant_id = None
    validator = SOXValidator()
    compliant, violations = validator.validate(sample_transaction, Decimal("50000.00"))
    assert not compliant
    assert "CTRL-005-MATERIAL_NO_MERCHANT" in violations


def test_dq_uniqueness(sample_transaction):
    from finance_etl.transform import DataQualityScorer

    scorer = DataQualityScorer()
    s1, _ = scorer.score(sample_transaction)
    s2, issues2 = scorer.score(sample_transaction)  # duplicate
    assert s1 > s2
    assert any("DUPLICATE" in i for i in issues2)
