"""Centralized settings using Pydantic BaseSettings.

All configuration is environment-driven. Secrets are NEVER hardcoded;
load from `.env` (local dev) or your secret manager in production.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    app_env: Literal["development", "staging", "production"] = "development"
    app_name: str = "finance_etl"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"


class OracleSettings(BaseSettings):
    oracle_host: str = "oracle.example.com"
    oracle_port: int = 1521
    oracle_service_name: str = "ORCLPDB1"
    oracle_user: str = "finance_etl_reader"
    oracle_password: SecretStr = SecretStr("__PLACEHOLDER__")
    oracle_pool_size: int = 5

    @property
    def dsn(self) -> str:
        return f"{self.oracle_host}:{self.oracle_port}/{self.oracle_service_name}"


class PostgresSettings(BaseSettings):
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "finance_etl_master"
    postgres_user: str = "finance_etl"
    postgres_password: SecretStr = SecretStr("__PLACEHOLDER__")

    @property
    def url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:"
            f"{self.postgres_password.get_secret_value()}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


class APISettings(BaseSettings):
    openexchange_api_key: SecretStr = SecretStr("__PLACEHOLDER__")
    openexchange_base_url: str = "https://openexchangerates.org/api"
    alphavantage_api_key: SecretStr = SecretStr("__PLACEHOLDER__")
    alphavantage_base_url: str = "https://www.alphavantage.co/query"


class SFTPSettings(BaseSettings):
    sftp_host: str = "sftp.partner.example.com"
    sftp_port: int = 22
    sftp_username: str = "finance_etl_etl"
    sftp_private_key_path: str = "/secrets/sftp_rsa"
    sftp_remote_dir: str = "/inbound/finance_etl"


class SnowflakeSettings(BaseSettings):
    snowflake_account: str = "abc12345.us-east-1"
    snowflake_user: str = "finance_etl_etl"
    snowflake_password: SecretStr = SecretStr("__PLACEHOLDER__")
    snowflake_warehouse: str = "FINANCE_ETL_WH"
    snowflake_database: str = "FINANCE_ETL_DW"
    snowflake_schema: str = "PUBLIC"
    snowflake_role: str = "FINANCE_ETL_ETL_ROLE"


class AWSSettings(BaseSettings):
    aws_access_key_id: SecretStr = SecretStr("__PLACEHOLDER__")
    aws_secret_access_key: SecretStr = SecretStr("__PLACEHOLDER__")
    aws_region: str = "us-east-1"
    s3_bucket: str = "finance_etl-data-lake"
    s3_prefix: str = "raw/"


class RedisSettings(BaseSettings):
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: SecretStr = SecretStr("")
    redis_db: int = 0
    redis_fraud_stream: str = "finance_etl:fraud:alerts"
    redis_dlq_key: str = "finance_etl:dlq"


class PipelineSettings(BaseSettings):
    pipeline_batch_size: int = 10000
    pipeline_max_retries: int = 5
    pipeline_retry_backoff: float = 2.0
    pipeline_timeout_seconds: int = 300
    pipeline_base_currency: str = "USD"

    fraud_velocity_txn_per_hour: int = 10
    fraud_high_value_threshold_usd: float = 10000.0
    fraud_zscore_threshold: float = 3.0


class MetricsSettings(BaseSettings):
    prometheus_port: int = 8000
    enable_metrics: bool = True


class Settings(BaseSettings):
    """Aggregate settings — composed from individual settings classes."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app: AppSettings = Field(default_factory=AppSettings)
    oracle: OracleSettings = Field(default_factory=OracleSettings)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    api: APISettings = Field(default_factory=APISettings)
    sftp: SFTPSettings = Field(default_factory=SFTPSettings)
    snowflake: SnowflakeSettings = Field(default_factory=SnowflakeSettings)
    aws: AWSSettings = Field(default_factory=AWSSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)
    metrics: MetricsSettings = Field(default_factory=MetricsSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Returns a cached Settings instance."""
    return Settings()
