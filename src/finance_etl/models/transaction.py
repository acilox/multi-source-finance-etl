"""Transaction-related Pydantic models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TransactionType(StrEnum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"
    TRANSFER = "TRANSFER"
    FEE = "FEE"
    REFUND = "REFUND"
    WITHDRAWAL = "WITHDRAWAL"
    DEPOSIT = "DEPOSIT"


class TransactionStatus(StrEnum):
    PENDING = "PENDING"
    POSTED = "POSTED"
    REVERSED = "REVERSED"
    DECLINED = "DECLINED"
    HELD_FOR_REVIEW = "HELD_FOR_REVIEW"


class Transaction(BaseModel):
    """Raw transaction record from a source system."""

    model_config = ConfigDict(str_strip_whitespace=True, frozen=False)

    transaction_id: str = Field(..., min_length=1, max_length=64)
    customer_id: str = Field(..., min_length=1, max_length=64)
    account_id: str = Field(..., min_length=1, max_length=64)
    transaction_type: TransactionType
    status: TransactionStatus = TransactionStatus.POSTED

    amount: Decimal = Field(..., gt=0, decimal_places=4)
    currency: str = Field(..., min_length=3, max_length=3)

    transaction_timestamp: datetime
    posted_timestamp: datetime | None = None

    merchant_id: str | None = Field(None, max_length=64)
    merchant_category: str | None = Field(None, max_length=64)
    merchant_country: str | None = Field(None, max_length=2)

    description: str | None = Field(None, max_length=512)
    reference_number: str | None = Field(None, max_length=64)

    # Source system tracking
    source_system: str = Field(..., max_length=32)
    source_extracted_at: datetime
    raw_payload: dict | None = None

    @field_validator("currency")
    @classmethod
    def validate_currency_code(cls, v: str) -> str:
        if not v.isalpha() or not v.isupper():
            raise ValueError(f"Currency must be a 3-letter ISO uppercase code, got {v!r}")
        return v


class FraudRuleResult(BaseModel):
    """Result of one fraud rule evaluation."""

    rule_name: str
    triggered: bool
    severity: str  # LOW | MEDIUM | HIGH | CRITICAL
    score: float = Field(..., ge=0.0, le=1.0)
    explanation: str


class FraudAlert(BaseModel):
    """A fraud alert produced for downstream consumers."""

    alert_id: str
    transaction_id: str
    customer_id: str
    risk_score: float = Field(..., ge=0.0, le=1.0)
    triggered_rules: list[FraudRuleResult]
    alerted_at: datetime
    metadata: dict = Field(default_factory=dict)


class EnrichedTransaction(BaseModel):
    """Transaction enriched with FX normalization, fraud score, and customer attrs."""

    model_config = ConfigDict(str_strip_whitespace=True)

    # Original fields
    transaction_id: str
    customer_id: str
    account_id: str
    transaction_type: TransactionType
    status: TransactionStatus

    # Original amount & currency
    original_amount: Decimal
    original_currency: str

    # Normalized to base currency (USD)
    amount_base: Decimal
    base_currency: str = "USD"
    fx_rate_used: Decimal

    # Timestamps
    transaction_timestamp: datetime
    posted_timestamp: datetime | None = None
    enriched_at: datetime

    # Merchant
    merchant_id: str | None = None
    merchant_category: str | None = None
    merchant_country: str | None = None

    # Customer enrichment
    customer_segment: str | None = None
    customer_risk_tier: str | None = None

    # Fraud
    fraud_risk_score: float = Field(0.0, ge=0.0, le=1.0)
    fraud_triggered_rules: list[str] = Field(default_factory=list)

    # SOX compliance
    sox_compliant: bool = True
    sox_violations: list[str] = Field(default_factory=list)

    # Data quality
    dq_score: float = Field(1.0, ge=0.0, le=1.0)
    dq_issues: list[str] = Field(default_factory=list)

    # Source tracking
    source_system: str
    pipeline_run_id: str
