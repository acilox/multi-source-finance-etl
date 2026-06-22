"""REST API extractors for FX rates and market data."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import httpx

from finance_etl.config.logging_config import get_logger
from finance_etl.config.settings import get_settings
from finance_etl.models import FXRate
from finance_etl.utils.metrics import metrics
from finance_etl.utils.retries import retry_with_backoff

logger = get_logger(__name__)


class FXRateExtractor:
    """Fetches FX rates from Open Exchange Rates API."""

    def __init__(self, timeout: float = 30.0) -> None:
        self.settings = get_settings()
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def __enter__(self) -> FXRateExtractor:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._client.close()

    @retry_with_backoff(
        max_attempts=5,
        initial_wait=1.0,
        max_wait=30.0,
        exceptions=(httpx.HTTPError, httpx.TimeoutException),
    )
    def fetch_rates(
        self,
        as_of_date: date,
        base_currency: str = "USD",
        symbols: list[str] | None = None,
    ) -> list[FXRate]:
        """Fetch FX rates for a given date.

        Args:
            as_of_date: Historical date to fetch rates for.
            base_currency: ISO 4217 base currency (default USD).
            symbols: Optional list of quote currencies. If None, fetch all.

        Returns:
            List of FXRate Pydantic models.
        """
        url = f"{self.settings.api.openexchange_base_url}/historical/{as_of_date.isoformat()}.json"
        params = {
            "app_id": self.settings.api.openexchange_api_key.get_secret_value(),
            "base": base_currency,
        }
        if symbols:
            params["symbols"] = ",".join(symbols)

        logger.info("fx_api_request", url=url, base=base_currency, date=str(as_of_date))
        response = self._client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        rates: list[FXRate] = []
        fetched_at = datetime.now(tz=UTC)

        for quote_ccy, raw_rate in data.get("rates", {}).items():
            try:
                rate = FXRate(
                    base_currency=base_currency,
                    quote_currency=quote_ccy,
                    rate=Decimal(str(raw_rate)),
                    as_of_date=as_of_date,
                    source="openexchangerates.org",
                    fetched_at=fetched_at,
                )
                rates.append(rate)
                metrics.records_extracted.labels(source="fx_api").inc()
            except Exception as e:
                logger.warning("fx_rate_invalid", currency=quote_ccy, error=str(e))

        logger.info("fx_api_complete", count=len(rates), as_of_date=str(as_of_date))
        return rates
