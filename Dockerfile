# ============================================================
# ============================================================

FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libaio1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --upgrade pip && \
    pip install --prefix=/install .

# ============================================================
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libaio1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 finance_etl \
    && useradd --uid 1000 --gid finance_etl --shell /bin/bash --create-home finance_etl

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --chown=finance_etl:finance_etl src/ ./src/
COPY --chown=finance_etl:finance_etl data/sample/ ./data/sample/

USER finance_etl

EXPOSE 8000

ENTRYPOINT ["python", "-m", "finance_etl.main"]
CMD ["--help"]
