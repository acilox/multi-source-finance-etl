"""Redis loader — publishes fraud alerts to a Stream and manages DLQ."""

from __future__ import annotations

import json
from collections.abc import Iterable

from finance_etl.config.logging_config import get_logger
from finance_etl.config.settings import get_settings
from finance_etl.models import FraudAlert
from finance_etl.utils.metrics import metrics
from finance_etl.utils.retries import retry_with_backoff

logger = get_logger(__name__)


class RedisLoader:
    """Publishes fraud alerts to a Redis Stream and stores DLQ messages."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = None

    def __enter__(self) -> RedisLoader:
        self._connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    @retry_with_backoff(max_attempts=3, initial_wait=1.0)
    def _connect(self) -> None:
        import redis  # type: ignore[import-not-found]

        s = self.settings.redis
        kwargs: dict = {
            "host": s.redis_host,
            "port": s.redis_port,
            "db": s.redis_db,
            "decode_responses": True,
        }
        pwd = s.redis_password.get_secret_value()
        if pwd:
            kwargs["password"] = pwd

        self._client = redis.Redis(**kwargs)
        self._client.ping()
        logger.info("redis_connected", host=s.redis_host, port=s.redis_port)

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001
                logger.debug("redis_close_failed", exc_info=True)
            self._client = None

    def publish_alerts(self, alerts: Iterable[FraudAlert]) -> int:
        if self._client is None:
            self._connect()
        assert self._client is not None

        stream = self.settings.redis.redis_fraud_stream
        count = 0
        pipe = self._client.pipeline()
        for alert in alerts:
            payload = alert.model_dump(mode="json")
            # Stream expects str:str map; flatten complex values to JSON
            flat = {
                "alert_id": payload["alert_id"],
                "transaction_id": payload["transaction_id"],
                "customer_id": payload["customer_id"],
                "risk_score": str(payload["risk_score"]),
                "alerted_at": payload["alerted_at"],
                "triggered_rules": json.dumps(payload["triggered_rules"]),
                "metadata": json.dumps(payload.get("metadata", {})),
            }
            pipe.xadd(stream, flat, maxlen=100_000, approximate=True)
            count += 1
        pipe.execute()

        metrics.records_loaded.labels(target="redis_fraud_stream").inc(count)
        logger.info("redis_alerts_published", stream=stream, count=count)
        return count

    def dlq_push(self, record: dict, reason: str) -> None:
        if self._client is None:
            self._connect()
        assert self._client is not None
        key = self.settings.redis.redis_dlq_key
        payload = json.dumps({"reason": reason, "record": record})
        self._client.rpush(key, payload)
        size = self._client.llen(key)
        metrics.dlq_size.set(size)
        logger.warning("dlq_push", reason=reason, dlq_size=size)
