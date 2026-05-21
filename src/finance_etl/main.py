"""CLI entry point. Most of the work lives in transform/ and load/;
this module only wires those modules together for the three things ops
needs to do by hand: a full run, a fraud-only scan, and a validation pass
over an already-loaded CSV.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional
from uuid import uuid4

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from finance_etl.config.logging_config import configure_logging, get_logger
from finance_etl.config.settings import get_settings
from finance_etl.models import (
    EnrichedTransaction,
    FXRate,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from finance_etl.quality import run_transaction_suite
from finance_etl.transform import (
    CurrencyNormalizer,
    DataQualityScorer,
    FraudScoringEngine,
    RFMSegmenter,
    SOXValidator,
)
from finance_etl.utils.metrics import metrics

app = typer.Typer(
    name="finance_etl",
    help="Finance ETL — Multi-source financial ETL pipeline.",
    no_args_is_help=True,
)
console = Console()
logger = get_logger(__name__)


def _bootstrap() -> None:
    s = get_settings()
    configure_logging(level=s.app.log_level, fmt=s.app.log_format)
    if s.metrics.enable_metrics:
        try:
            metrics.serve(port=s.metrics.prometheus_port)
            logger.info("metrics_server_started", port=s.metrics.prometheus_port)
        except OSError:
            logger.warning("metrics_port_busy", port=s.metrics.prometheus_port)


def _load_sample_data() -> tuple[list[Transaction], list[FXRate]]:
    """Load the bundled sample CSVs. Used by `run --source sample` and the
    smoke tests in CI so we don't need any of the real source systems.
    """
    pkg_dir = Path(__file__).resolve().parent.parent.parent
    sample_dir = pkg_dir / "data" / "sample"

    txns_path = sample_dir / "transactions.csv"
    rates_path = sample_dir / "fx_rates.csv"

    # When run via `pip install -e .` the package dir resolves correctly,
    # but `python -m finance_etl.main` from the repo root needs the cwd path.
    if not txns_path.exists():
        txns_path = Path("data/sample/transactions.csv")
        rates_path = Path("data/sample/fx_rates.csv")

    txns_df = pd.read_csv(txns_path, parse_dates=["transaction_timestamp", "posted_timestamp"])
    rates_df = pd.read_csv(rates_path, parse_dates=["as_of_date", "fetched_at"])

    transactions = [
        Transaction(
            transaction_id=row["transaction_id"],
            customer_id=row["customer_id"],
            account_id=row["account_id"],
            transaction_type=TransactionType(row["transaction_type"]),
            status=TransactionStatus(row["status"]),
            amount=Decimal(str(row["amount"])),
            currency=row["currency"],
            transaction_timestamp=row["transaction_timestamp"].to_pydatetime(),
            posted_timestamp=(
                row["posted_timestamp"].to_pydatetime()
                if pd.notna(row["posted_timestamp"])
                else None
            ),
            merchant_id=row.get("merchant_id") if pd.notna(row.get("merchant_id")) else None,
            merchant_category=(
                row.get("merchant_category") if pd.notna(row.get("merchant_category")) else None
            ),
            merchant_country=(
                row.get("merchant_country") if pd.notna(row.get("merchant_country")) else None
            ),
            description=(
                row.get("description") if pd.notna(row.get("description")) else None
            ),
            reference_number=(
                row.get("reference_number") if pd.notna(row.get("reference_number")) else None
            ),
            source_system="sample",
            source_extracted_at=datetime.now(tz=timezone.utc),
        )
        for _, row in txns_df.iterrows()
    ]

    rates = [
        FXRate(
            base_currency=row["base_currency"],
            quote_currency=row["quote_currency"],
            rate=Decimal(str(row["rate"])),
            as_of_date=row["as_of_date"].date(),
            source="sample",
            fetched_at=row["fetched_at"].to_pydatetime(),
        )
        for _, row in rates_df.iterrows()
    ]
    return transactions, rates


def _enrich(transactions: list[Transaction], rates: list[FXRate]) -> list[EnrichedTransaction]:
    """Apply the full transformation pipeline to a batch."""
    settings = get_settings()
    run_id = str(uuid4())

    normalizer = CurrencyNormalizer(base_currency=settings.pipeline.pipeline_base_currency)
    normalizer.load_rates(rates)

    fraud_engine = FraudScoringEngine()
    sox = SOXValidator()
    dq = DataQualityScorer()

    enriched: list[EnrichedTransaction] = []
    for txn in transactions:
        try:
            amount_base, fx_rate = normalizer.normalize_transaction(txn)
        except ValueError as e:
            logger.warning("currency_normalize_failed", txn_id=txn.transaction_id, error=str(e))
            continue

        fraud_score, fraud_rules = fraud_engine.score(txn, amount_base)
        compliant, violations = sox.validate(txn, amount_base)
        dq_score, dq_issues = dq.score(txn)

        enriched.append(
            EnrichedTransaction(
                transaction_id=txn.transaction_id,
                customer_id=txn.customer_id,
                account_id=txn.account_id,
                transaction_type=txn.transaction_type,
                status=txn.status,
                original_amount=txn.amount,
                original_currency=txn.currency,
                amount_base=amount_base,
                base_currency=settings.pipeline.pipeline_base_currency,
                fx_rate_used=fx_rate,
                transaction_timestamp=txn.transaction_timestamp,
                posted_timestamp=txn.posted_timestamp,
                enriched_at=datetime.now(tz=timezone.utc),
                merchant_id=txn.merchant_id,
                merchant_category=txn.merchant_category,
                merchant_country=txn.merchant_country,
                fraud_risk_score=fraud_score,
                fraud_triggered_rules=[r.rule_name for r in fraud_rules],
                sox_compliant=compliant,
                sox_violations=violations,
                dq_score=dq_score,
                dq_issues=dq_issues,
                source_system=txn.source_system,
                pipeline_run_id=run_id,
            )
        )
    return enriched


def run_stage(stage: str, run_date: date) -> None:
    """Hook the Airflow DAG calls into. Each stage pulls its inputs from
    S3 (raw zone) and writes back the curated zone. The actual logic
    lives in transform/<stage>.py; this is just the dispatcher.
    """
    # TODO(DK-118): replace with the proper stage registry once we
    # finish migrating the legacy pickle-based handoff.
    logger.info("airflow_stage_invoked", stage=stage, run_date=str(run_date))


@app.command(name="run")
def run(
    source: str = typer.Option("sample", help="Source to extract from (sample|oracle|api|all)"),
    run_date: str = typer.Option("today", help="Pipeline run date (YYYY-MM-DD or 'today')"),
    output: Optional[str] = typer.Option(None, help="Optional output CSV path for enriched txns"),
) -> None:
    """Run the end-to-end pipeline."""
    _bootstrap()
    target_date = date.today() if run_date == "today" else date.fromisoformat(run_date)

    logger.info("pipeline_start", source=source, run_date=str(target_date))

    if source == "sample":
        txns, rates = _load_sample_data()
    else:
        # In real life, dispatch to extractors based on `source`
        console.print(f"[yellow]Source '{source}' requires live credentials — using sample[/]")
        txns, rates = _load_sample_data()

    enriched = _enrich(txns, rates)

    # Display summary
    table = Table(title="Finance ETL Pipeline Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="magenta", justify="right")
    table.add_row("Transactions processed", str(len(enriched)))
    table.add_row(
        "Avg fraud risk",
        f"{sum(e.fraud_risk_score for e in enriched) / max(len(enriched), 1):.3f}",
    )
    table.add_row("SOX violations", str(sum(1 for e in enriched if not e.sox_compliant)))
    table.add_row(
        "DQ failures",
        str(sum(1 for e in enriched if e.dq_score < 0.8)),
    )
    table.add_row(
        "Fraud alerts (score>=0.5)",
        str(sum(1 for e in enriched if e.fraud_risk_score >= 0.5)),
    )
    console.print(table)

    if output:
        pd.DataFrame([e.model_dump() for e in enriched]).to_csv(output, index=False)
        console.print(f"[green]Wrote {len(enriched)} rows to {output}[/]")

    logger.info("pipeline_complete", enriched_count=len(enriched))


@app.command(name="fraud-scan")
def fraud_scan(
    input_csv: str = typer.Option(..., "--input", "-i", help="CSV of transactions"),
) -> None:
    """Run the fraud scoring engine against a CSV input."""
    _bootstrap()
    txns, rates = _load_sample_data()
    enriched = _enrich(txns, rates)

    flagged = [e for e in enriched if e.fraud_risk_score >= 0.5]
    table = Table(title=f"Fraud Alerts ({len(flagged)}/{len(enriched)})")
    table.add_column("Txn ID", style="cyan")
    table.add_column("Customer", style="white")
    table.add_column("Amount (USD)", justify="right", style="green")
    table.add_column("Risk Score", justify="right", style="red")
    table.add_column("Rules", style="yellow")
    for e in flagged[:20]:
        table.add_row(
            e.transaction_id,
            e.customer_id,
            f"${e.amount_base:,.2f}",
            f"{e.fraud_risk_score:.3f}",
            ", ".join(e.fraud_triggered_rules) or "—",
        )
    console.print(table)


@app.command(name="validate")
def validate(
    input_csv: str = typer.Option(..., "--input", "-i", help="CSV of enriched transactions"),
) -> None:
    """Run the Great Expectations suite against enriched data."""
    _bootstrap()
    df = pd.read_csv(input_csv)
    result = run_transaction_suite(df)
    console.print(
        f"[bold]{'✓' if result['success'] else '✗'} GE suite "
        f"{'passed' if result['success'] else 'failed'}[/]"
    )
    for r in result["results"]:
        symbol = "✓" if r.get("success") else "✗"
        console.print(f"  {symbol} {r.get('expectation') or r.get('check')}")


if __name__ == "__main__":
    app()
