"""Great Expectations data quality suite for transactions.

Uses GE's lightweight pandas integration to validate dataframes
before they're loaded to target systems. Failed expectations
route records to a Redis DLQ.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from finance_etl.config.logging_config import get_logger

logger = get_logger(__name__)


TRANSACTION_EXPECTATIONS = [
    # (expectation_type, kwargs)
    ("expect_column_to_exist", {"column": "transaction_id"}),
    ("expect_column_to_exist", {"column": "customer_id"}),
    ("expect_column_to_exist", {"column": "amount_base"}),
    ("expect_column_to_exist", {"column": "transaction_timestamp"}),
    ("expect_column_values_to_not_be_null", {"column": "transaction_id"}),
    ("expect_column_values_to_not_be_null", {"column": "customer_id"}),
    ("expect_column_values_to_not_be_null", {"column": "amount_base"}),
    ("expect_column_values_to_be_unique", {"column": "transaction_id"}),
    (
        "expect_column_values_to_be_between",
        {
            "column": "amount_base",
            "min_value": 0,
            "max_value": 10_000_000,
        },
    ),
    (
        "expect_column_values_to_be_in_set",
        {
            "column": "base_currency",
            "value_set": ["USD"],
        },
    ),
    (
        "expect_column_values_to_match_regex",
        {
            "column": "original_currency",
            "regex": r"^[A-Z]{3}$",
        },
    ),
    (
        "expect_column_values_to_be_between",
        {
            "column": "fraud_risk_score",
            "min_value": 0.0,
            "max_value": 1.0,
        },
    ),
]


def run_transaction_suite(df: pd.DataFrame) -> dict[str, Any]:
    """Run the transaction expectation suite against a DataFrame.

    Returns a dict with:
        - success: overall pass/fail
        - results: per-expectation results
        - failed_records: list of indices for records that failed validity checks
    """
    try:
        from great_expectations.dataset import PandasDataset  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("ge_not_installed_using_manual_checks")
        return _manual_validation(df)

    dataset = PandasDataset(df)

    results = []
    failed_records: set[int] = set()
    overall_success = True

    for exp_type, kwargs in TRANSACTION_EXPECTATIONS:
        method = getattr(dataset, exp_type, None)
        if method is None:
            logger.warning("ge_unknown_expectation", expectation=exp_type)
            continue
        result = method(**kwargs)
        success = (
            bool(result.get("success", False))
            if isinstance(result, dict)
            else getattr(result, "success", False)
        )
        if not success:
            overall_success = False
            # Capture row indices where applicable
            unexpected_idx = (
                result.get("result", {}).get("unexpected_index_list", [])
                if isinstance(result, dict)
                else getattr(result, "result", {}).get("unexpected_index_list", [])
            )
            failed_records.update(unexpected_idx or [])

        results.append({"expectation": exp_type, "kwargs": kwargs, "success": success})

    logger.info(
        "ge_suite_complete",
        success=overall_success,
        total=len(results),
        failed=sum(1 for r in results if not r["success"]),
    )
    return {
        "success": overall_success,
        "results": results,
        "failed_records": sorted(failed_records),
    }


def _manual_validation(df: pd.DataFrame) -> dict[str, Any]:
    """Lightweight fallback validations when Great Expectations isn't installed."""
    failed: set[int] = set()
    results: list[dict] = []

    def _record(check: str, success: bool) -> None:
        results.append({"check": check, "success": success})

    # required columns
    for col in ("transaction_id", "customer_id", "amount_base", "transaction_timestamp"):
        present = col in df.columns
        _record(f"column_exists::{col}", present)
        if not present:
            return {"success": False, "results": results, "failed_records": []}

    # non-null & unique
    for col in ("transaction_id", "customer_id", "amount_base"):
        nulls = df[df[col].isna()].index.tolist()
        _record(f"non_null::{col}", not nulls)
        failed.update(nulls)

    dup_ids = df[df["transaction_id"].duplicated()].index.tolist()
    _record("unique::transaction_id", not dup_ids)
    failed.update(dup_ids)

    # amount range
    bad_amount = df[(df["amount_base"] < 0) | (df["amount_base"] > 10_000_000)].index.tolist()
    _record("amount_in_range", not bad_amount)
    failed.update(bad_amount)

    success = all(r["success"] for r in results)
    return {"success": success, "results": results, "failed_records": sorted(failed)}
