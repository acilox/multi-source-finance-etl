"""FX rate Pydantic model."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FXRate(BaseModel):
    """Daily FX rate to a base currency."""

    model_config = ConfigDict(str_strip_whitespace=True)

    base_currency: str = Field(..., min_length=3, max_length=3)
    quote_currency: str = Field(..., min_length=3, max_length=3)
    rate: Decimal = Field(..., gt=0)
    as_of_date: date
    source: str = Field(..., max_length=64)
    fetched_at: datetime

    @field_validator("base_currency", "quote_currency")
    @classmethod
    def validate_iso_code(cls, v: str) -> str:
        if not v.isalpha() or not v.isupper():
            raise ValueError(f"Currency must be 3-letter uppercase ISO, got {v!r}")
        return v
