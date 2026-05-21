"""Tests for CurrencyNormalizer."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from finance_etl.transform import CurrencyNormalizer


def test_normalize_same_currency_returns_amount_unchanged(fx_rates_usd_base):
    norm = CurrencyNormalizer(base_currency="USD")
    norm.load_rates(fx_rates_usd_base)

    amount_base, rate = norm.to_base(Decimal("100"), "USD", date(2026, 5, 20))
    assert amount_base == Decimal("100")
    assert rate == Decimal("1")


def test_normalize_eur_to_usd(fx_rates_usd_base):
    norm = CurrencyNormalizer(base_currency="USD")
    norm.load_rates(fx_rates_usd_base)

    # 1 USD = 0.92 EUR, so 92 EUR -> 100 USD
    amount_base, rate = norm.to_base(Decimal("92"), "EUR", date(2026, 5, 20))
    assert amount_base == Decimal("100.0000")
    assert rate == Decimal("0.92")


def test_normalize_inr_to_usd(fx_rates_usd_base):
    norm = CurrencyNormalizer(base_currency="USD")
    norm.load_rates(fx_rates_usd_base)

    # 1 USD = 83.2 INR, so 8320 INR -> 100 USD
    amount_base, rate = norm.to_base(Decimal("8320"), "INR", date(2026, 5, 20))
    assert amount_base == Decimal("100.0000")
    assert rate == Decimal("83.2")


def test_normalize_missing_rate_raises(fx_rates_usd_base):
    norm = CurrencyNormalizer(base_currency="USD")
    norm.load_rates(fx_rates_usd_base)

    with pytest.raises(ValueError, match="No FX rate"):
        norm.to_base(Decimal("100"), "JPY", date(2026, 5, 20))


def test_normalize_falls_back_to_recent_rate(fx_rates_usd_base):
    norm = CurrencyNormalizer(base_currency="USD")
    norm.load_rates(fx_rates_usd_base)

    # Request future date — should walk back to 2026-05-20
    amount_base, rate = norm.to_base(Decimal("92"), "EUR", date(2026, 5, 21))
    assert rate == Decimal("0.92")
    assert amount_base == Decimal("100.0000")
