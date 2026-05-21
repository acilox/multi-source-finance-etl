"""Customer-related Pydantic models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CustomerSegment(str, Enum):
    CHAMPION = "CHAMPION"           # high R / high F / high M
    LOYAL = "LOYAL"
    POTENTIAL_LOYALIST = "POTENTIAL_LOYALIST"
    NEW = "NEW"
    PROMISING = "PROMISING"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    ABOUT_TO_SLEEP = "ABOUT_TO_SLEEP"
    AT_RISK = "AT_RISK"
    HIBERNATING = "HIBERNATING"
    LOST = "LOST"


class Customer(BaseModel):
    """Customer master record (from PostgreSQL)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    customer_id: str = Field(..., min_length=1, max_length=64)
    first_name: str = Field(..., min_length=1, max_length=128)
    last_name: str = Field(..., min_length=1, max_length=128)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=32)
    date_of_birth: Optional[date] = None

    address_line1: Optional[str] = Field(None, max_length=256)
    city: Optional[str] = Field(None, max_length=128)
    state: Optional[str] = Field(None, max_length=64)
    country: str = Field(..., min_length=2, max_length=2)
    postal_code: Optional[str] = Field(None, max_length=20)

    risk_tier: str = Field("STANDARD", max_length=16)  # LOW | STANDARD | HIGH | VIP
    kyc_status: str = Field("VERIFIED", max_length=16)
    customer_since: date

    created_at: datetime
    updated_at: datetime

    # SCD Type 2 attributes
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    is_current: bool = True


class RFMScore(BaseModel):
    """RFM (Recency, Frequency, Monetary) score for a customer."""

    customer_id: str
    recency_days: int = Field(..., ge=0)
    frequency_count: int = Field(..., ge=0)
    monetary_value: Decimal = Field(..., ge=0)

    r_score: int = Field(..., ge=1, le=5)
    f_score: int = Field(..., ge=1, le=5)
    m_score: int = Field(..., ge=1, le=5)

    rfm_combined: str  # e.g. "555"
    segment: CustomerSegment
    computed_at: datetime
