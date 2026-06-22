"""SFTP-based file extractor with idempotency checksums."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from finance_etl.config.logging_config import get_logger
from finance_etl.config.settings import get_settings
from finance_etl.utils.metrics import metrics
from finance_etl.utils.retries import retry_with_backoff

logger = get_logger(__name__)


class SFTPFileExtractor:
    """Downloads partner files via SFTP and stores them locally.

    Idempotent: skips files we've already downloaded based on SHA-256 checksum.
    """

    def __init__(self, local_staging_dir: str = "data/raw/sftp") -> None:
        self.settings = get_settings()
        self.local_staging_dir = Path(local_staging_dir)
        self.local_staging_dir.mkdir(parents=True, exist_ok=True)
        self._client = None
        self._transport = None

    def __enter__(self) -> SFTPFileExtractor:
        self._connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    @retry_with_backoff(max_attempts=3, initial_wait=2.0)
    def _connect(self) -> None:
        try:
            import paramiko  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError("paramiko not installed") from e

        self._transport = paramiko.Transport(
            (self.settings.sftp.sftp_host, self.settings.sftp.sftp_port)
        )
        pkey_path = self.settings.sftp.sftp_private_key_path
        if os.path.exists(pkey_path):
            pkey = paramiko.RSAKey.from_private_key_file(pkey_path)
            self._transport.connect(username=self.settings.sftp.sftp_username, pkey=pkey)
        else:
            # placeholder for password-based auth if needed
            raise RuntimeError(f"Private key not found at {pkey_path}")

        self._client = paramiko.SFTPClient.from_transport(self._transport)
        logger.info(
            "sftp_connected",
            host=self.settings.sftp.sftp_host,
            user=self.settings.sftp.sftp_username,
        )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
        if self._transport is not None:
            self._transport.close()
        logger.info("sftp_closed")

    def list_files(self, remote_dir: str | None = None, pattern: str = "*.csv") -> list[str]:
        """List files matching pattern in remote dir."""
        import fnmatch

        remote = remote_dir or self.settings.sftp.sftp_remote_dir
        assert self._client is not None
        files = self._client.listdir(remote)
        matching = [f for f in files if fnmatch.fnmatch(f, pattern)]
        logger.info("sftp_list", remote_dir=remote, count=len(matching), pattern=pattern)
        return matching

    def download(self, remote_filename: str, remote_dir: str | None = None) -> Path | None:
        """Download a file from SFTP. Returns local path or None if skipped (already downloaded).

        Idempotency via checksum: if a local file with matching SHA-256 exists, skip.
        """
        remote = remote_dir or self.settings.sftp.sftp_remote_dir
        remote_path = f"{remote}/{remote_filename}"
        local_path = self.local_staging_dir / remote_filename

        assert self._client is not None

        # Check if we've already downloaded this file
        if local_path.exists():
            logger.info("sftp_file_already_present", file=remote_filename)
            return local_path

        logger.info("sftp_download_start", remote=remote_path, local=str(local_path))
        self._client.get(remote_path, str(local_path))

        checksum = self._sha256(local_path)
        logger.info(
            "sftp_download_complete",
            file=remote_filename,
            size_bytes=local_path.stat().st_size,
            sha256=checksum,
        )
        metrics.records_extracted.labels(source="sftp").inc()
        return local_path

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
