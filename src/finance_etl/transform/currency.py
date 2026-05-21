"""Multi-currency normalization to base currency."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from finance_etl.config.logging_config import get_logger
from finance_etl.models import FXRate, Transaction

logger = get_logger(__name__)


class CurrencyNormalizer:
    """Converts transaction amounts to a base currency using daily FX rates."""

    def __init__(self, base_currency: str = "USD") -> None:
        self.base_currency = base_currency
        # Index: (as_of_date, quote_currency) -> rate (rate is base->quote)
        self._rate_lookup: dict[tuple[date, str], Decimal] = {}

    def load_rates(self, rates: list[FXRate]) -> None:
        """Build the in-memory rate lookup."""
        self._rate_lookup = {
            (r.as_of_date, r.quote_currency): r.rate
            for r in rates
            if r.base_currency == self.base_currency
        }
        logger.info(
            "currency_rates_loaded",
            count=len(self._rate_lookup),
            base=self.base_currency,
        )

    def to_base(self, amount: Decimal, currency: str, as_of: date) -> tuple[Decimal, Decimal]:
        """Convert an amount in `currency` to `self.base_currency` using rates on `as_of`.

        Returns:
            (amount_in_base, fx_rate_used)
        """
        if currency == self.base_currency:
            return amount, Decimal("1")

        rate = self._rate_lookup.get((as_of, currency))
        if rate is None:
            # Fallback: walk back up to 7 days for missing rates
            rate = self._find_recent_rate(currency, as_of, max_days_back=7)

        if rate is None:
            raise ValueError(
                f"No FX rate available for {currency} on/before {as_of}"
            )

        # rate is base->quote, so quote->base is 1/rate
        amount_base = (amount / rate).quantize(Decimal("0.0001"))
        return amount_base, rate

    def _find_recent_rate(
        self, currency: str, as_of: date, max_days_back: int = 7
    ) -> Decimal | None:
        """Walk back days looking for a rate."""
        from datetime import timedelta

        for delta in range(1, max_days_back + 1):
            candidate = as_of - timedelta(days=delta)
            rate = self._rate_lookup.get((candidate, currency))
            if rate is not None:
                logger.debug(
                    "fx_rate_fallback",
                    currency=currency,
                    requested=str(as_of),
                    used=str(candidate),
                )
                return rate
        return None

    def normalize_transaction(self, txn: Transaction) -> tuple[Decimal, Decimal]:
        """Returns (amount_in_base, fx_rate_used) for a Transaction."""
        return self.to_base(txn.amount, txn.currency, txn.transaction_timestamp.date())
