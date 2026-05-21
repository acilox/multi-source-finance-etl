"""Data quality & Great Expectations integrations."""

from finance_etl.quality.expectations import run_transaction_suite

__all__ = ["run_transaction_suite"]
