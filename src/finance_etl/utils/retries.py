"""Reusable retry decorator with exponential backoff."""

from __future__ import annotations

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from finance_etl.config.logging_config import get_logger

logger = get_logger(__name__)


def retry_with_backoff(
    *,
    max_attempts: int = 5,
    initial_wait: float = 1.0,
    max_wait: float = 60.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
):
    """Decorator for resilient functions with exponential backoff.

    Example:
        @retry_with_backoff(max_attempts=3, exceptions=(httpx.HTTPError,))
        def fetch_data(): ...
    """
    return retry(
        retry=retry_if_exception_type(exceptions),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=initial_wait, max=max_wait),
        before_sleep=before_sleep_log(logger, log_level=30),  # WARNING
        reraise=True,
    )
