# Finance ETL Business Rules

## Fraud Scoring Rules

| Rule | Threshold | Severity | Action |
|------|-----------|----------|--------|
| `velocity_check` | ≥ 10 txns in 1 hr | HIGH | Score ≥ 0.5 → Redis stream |
| `high_value` | ≥ $10,000 USD | MEDIUM | Score scales with ratio above threshold |
| `geo_velocity` | Cross-country txn within 1 hr | CRITICAL | Score = 1.0 → mandatory alert |
| `zscore` | abs(z) ≥ 3.0 from customer mean | HIGH | Requires ≥10 txn history |

Composite risk score = **max** of all rule scores (any critical rule flags the txn).

## SOX Compliance Controls

| Control ID | Description | Action on Violation |
|------------|-------------|---------------------|
| CTRL-001 | Mandatory audit fields (`source_system`, `extracted_at`, `reference_number`) | Block load |
| CTRL-002 | POSTED txns must have `posted_timestamp` | Block load |
| CTRL-003 | `posted_timestamp` ≥ `transaction_timestamp` | Block load |
| CTRL-005 | Material txns (≥ $25K) require `merchant_id` & description ≥ 5 chars | Flag for review |
| CTRL-006 | ISO 4217 currency codes only | Block load |

## RFM Segmentation Matrix

R/F/M scored on 1-5 quintiles; segment assigned by these patterns:

| R | F | M | Segment |
|---|---|---|---------|
| 4-5 | 4-5 | 4-5 | Champion |
| 4-5 | 3+ | any | Loyal |
| 4-5 | 1-2 | any | New |
| 3 | 3+ | any | Potential Loyalist |
| 3 | 1-2 | any | Promising |
| 2 | 3+ | any | Needs Attention |
| 2 | 1-2 | any | About to Sleep |
| 1 | 3+ | any | At Risk |
| 1 | any | 4-5 | Hibernating |
| 1 | 1-2 | 1-3 | Lost |

## Currency Normalization

- **Base currency**: USD (configurable via `PIPELINE_BASE_CURRENCY`)
- **Source**: Open Exchange Rates API (daily historical rates)
- **Fallback**: Walk back up to 7 days for missing rate dates
- **Precision**: 4 decimal places (`Decimal.quantize("0.0001")`)

## Data Quality Scoring

Composite score weighted across 4 dimensions:

```
DQ Score = 0.35*Completeness + 0.30*Validity + 0.20*Uniqueness + 0.15*Consistency
```

Records with `DQ Score < 0.8` are routed to the Redis DLQ for manual review.
