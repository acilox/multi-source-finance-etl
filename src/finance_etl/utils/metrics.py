"""Prometheus metrics for the Finance ETL pipeline."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, start_http_server


class _Metrics:
    """Lazy-initialized Prometheus metrics registry."""

    def __init__(self) -> None:
        self.registry = CollectorRegistry()

        self.records_extracted = Counter(
            "finance_etl_records_extracted_total",
            "Total records extracted",
            ["source"],
            registry=self.registry,
        )
        self.records_transformed = Counter(
            "finance_etl_records_transformed_total",
            "Total records transformed",
            ["stage"],
            registry=self.registry,
        )
        self.records_loaded = Counter(
            "finance_etl_records_loaded_total",
            "Total records loaded to target",
            ["target"],
            registry=self.registry,
        )
        self.pipeline_duration = Histogram(
            "finance_etl_pipeline_duration_seconds",
            "Pipeline stage duration",
            ["stage"],
            registry=self.registry,
        )
        self.fraud_alerts = Counter(
            "finance_etl_fraud_alerts_total",
            "Fraud alerts raised",
            ["rule", "severity"],
            registry=self.registry,
        )
        self.dq_failures = Counter(
            "finance_etl_dq_failures_total",
            "Data quality failures",
            ["check"],
            registry=self.registry,
        )
        self.dlq_size = Gauge(
            "finance_etl_dlq_size",
            "Records currently in dead-letter queue",
            registry=self.registry,
        )
        self.pipeline_errors = Counter(
            "finance_etl_pipeline_errors_total",
            "Pipeline errors",
            ["stage", "error_type"],
            registry=self.registry,
        )

    def serve(self, port: int = 8000) -> None:
        """Start the Prometheus HTTP server."""
        start_http_server(port, registry=self.registry)


metrics = _Metrics()
