"""Fraud scoring rules engine.

Implements a layered rules-based fraud detection system:
- Velocity check (txn count in a sliding hour window)
- High-value anomaly (configurable threshold)
- Geo-velocity (impossible travel between countries)
- Z-score deviation from customer baseline
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from datetime import datetime, timedelta
from decimal import Decimal
from statistics import mean, pstdev
from uuid import uuid4

from finance_etl.config.logging_config import get_logger
from finance_etl.config.settings import get_settings
from finance_etl.models import FraudAlert, FraudRuleResult, Transaction
from finance_etl.utils.metrics import metrics

logger = get_logger(__name__)


class FraudScoringEngine:
    """Composable fraud-rules engine. Each rule returns a 0-1 score; final score
    is the max across all rules (so any single critical rule can flag a txn).
    """

    def __init__(self) -> None:
        s = get_settings()
        self.velocity_threshold = s.pipeline.fraud_velocity_txn_per_hour
        self.high_value_threshold = Decimal(str(s.pipeline.fraud_high_value_threshold_usd))
        self.zscore_threshold = s.pipeline.fraud_zscore_threshold

        # per-customer state for stateful rules
        self._customer_recent_txns: dict[str, deque[Transaction]] = defaultdict(
            lambda: deque(maxlen=200)
        )
        self._customer_amounts: dict[str, list[Decimal]] = defaultdict(list)

    def score(self, txn: Transaction, amount_base: Decimal) -> tuple[float, list[FraudRuleResult]]:
        """Score a transaction; returns (final_score, triggered_rules)."""
        rules: list[FraudRuleResult] = []

        rules.append(self._rule_velocity(txn))
        rules.append(self._rule_high_value(txn, amount_base))
        rules.append(self._rule_geo_velocity(txn))
        rules.append(self._rule_zscore(txn, amount_base))

        # update state for stateful rules AFTER scoring (don't bias current txn)
        self._customer_recent_txns[txn.customer_id].append(txn)
        self._customer_amounts[txn.customer_id].append(amount_base)
        # cap history at 1000 items per customer
        if len(self._customer_amounts[txn.customer_id]) > 1000:
            self._customer_amounts[txn.customer_id] = self._customer_amounts[txn.customer_id][
                -1000:
            ]

        triggered = [r for r in rules if r.triggered]
        final_score = max((r.score for r in rules), default=0.0)

        for r in triggered:
            metrics.fraud_alerts.labels(rule=r.rule_name, severity=r.severity).inc()

        return final_score, triggered

    # ---- Individual rules ----
    def _rule_velocity(self, txn: Transaction) -> FraudRuleResult:
        """Trigger if customer has more than N txns in the last hour."""
        cutoff = txn.transaction_timestamp - timedelta(hours=1)
        recent = self._customer_recent_txns[txn.customer_id]
        count_in_window = sum(1 for t in recent if t.transaction_timestamp >= cutoff)

        triggered = count_in_window >= self.velocity_threshold
        score = min(1.0, count_in_window / (self.velocity_threshold * 2.0))
        return FraudRuleResult(
            rule_name="velocity_check",
            triggered=triggered,
            severity="HIGH" if triggered else "LOW",
            score=score,
            explanation=(
                f"{count_in_window} txns in last hour " f"(threshold {self.velocity_threshold})"
            ),
        )

    def _rule_high_value(self, txn: Transaction, amount_base: Decimal) -> FraudRuleResult:
        triggered = amount_base >= self.high_value_threshold
        # log-scale score
        try:
            ratio = float(amount_base / self.high_value_threshold)
        except (ZeroDivisionError, ArithmeticError):
            ratio = 0.0
        score = min(1.0, max(0.0, (ratio - 1.0) / 5.0)) if triggered else 0.0
        return FraudRuleResult(
            rule_name="high_value",
            triggered=triggered,
            severity="MEDIUM" if triggered else "LOW",
            score=score,
            explanation=f"Amount {amount_base} (threshold {self.high_value_threshold})",
        )

    def _rule_geo_velocity(self, txn: Transaction) -> FraudRuleResult:
        """Trigger if same customer transacts in two countries within 1 hour."""
        recent = self._customer_recent_txns[txn.customer_id]
        if not recent or not txn.merchant_country:
            return FraudRuleResult(
                rule_name="geo_velocity",
                triggered=False,
                severity="LOW",
                score=0.0,
                explanation="No prior txn or merchant country missing",
            )

        cutoff = txn.transaction_timestamp - timedelta(hours=1)
        offending = [
            t
            for t in recent
            if t.transaction_timestamp >= cutoff
            and t.merchant_country
            and t.merchant_country != txn.merchant_country
        ]
        triggered = len(offending) > 0
        prev_country = offending[0].merchant_country if offending else "-"
        return FraudRuleResult(
            rule_name="geo_velocity",
            triggered=triggered,
            severity="CRITICAL" if triggered else "LOW",
            score=1.0 if triggered else 0.0,
            explanation=(
                f"Cross-country activity in <1h ({prev_country} -> {txn.merchant_country})"
                if triggered
                else "No cross-country movement"
            ),
        )

    def _rule_zscore(self, txn: Transaction, amount_base: Decimal) -> FraudRuleResult:
        """Trigger if amount is more than N std-devs from customer's mean."""
        history = self._customer_amounts[txn.customer_id]
        if len(history) < 10:
            return FraudRuleResult(
                rule_name="zscore",
                triggered=False,
                severity="LOW",
                score=0.0,
                explanation="Insufficient history (<10 txns)",
            )

        amounts = [float(a) for a in history]
        mu = mean(amounts)
        sigma = pstdev(amounts)
        if sigma == 0:
            return FraudRuleResult(
                rule_name="zscore",
                triggered=False,
                severity="LOW",
                score=0.0,
                explanation="Zero variance",
            )

        z = abs((float(amount_base) - mu) / sigma)
        triggered = z >= self.zscore_threshold
        score = min(1.0, z / (self.zscore_threshold * 2.0))
        return FraudRuleResult(
            rule_name="zscore",
            triggered=triggered,
            severity="HIGH" if triggered else "LOW",
            score=score,
            explanation=f"z={z:.2f} (threshold {self.zscore_threshold})",
        )

    # ---- Alert factory ----
    def build_alert(
        self,
        txn: Transaction,
        risk_score: float,
        triggered_rules: list[FraudRuleResult],
    ) -> FraudAlert:
        return FraudAlert(
            alert_id=str(uuid4()),
            transaction_id=txn.transaction_id,
            customer_id=txn.customer_id,
            risk_score=risk_score,
            triggered_rules=triggered_rules,
            alerted_at=datetime.utcnow(),
            metadata={
                "source_system": txn.source_system,
                "currency": txn.currency,
            },
        )

    def score_batch(
        self,
        transactions: Iterable[Transaction],
        amounts_base: Iterable[Decimal],
    ) -> list[tuple[Transaction, float, list[FraudRuleResult]]]:
        """Batch scoring for convenience."""
        return [
            (txn, *self.score(txn, amount_base))
            for txn, amount_base in zip(transactions, amounts_base, strict=True)
        ]
