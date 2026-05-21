"""Extractors for source systems."""

from finance_etl.extract.api_extractor import FXRateExtractor
from finance_etl.extract.oracle_extractor import OracleTransactionExtractor
from finance_etl.extract.postgres_extractor import PostgresCustomerExtractor
from finance_etl.extract.sftp_extractor import SFTPFileExtractor

__all__ = [
    "FXRateExtractor",
    "OracleTransactionExtractor",
    "PostgresCustomerExtractor",
    "SFTPFileExtractor",
]
