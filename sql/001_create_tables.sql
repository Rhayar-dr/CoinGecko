-- Schema for the CoinGecko data engineering pipeline.
--
-- This file mirrors the SQLAlchemy models in app/database/models.py. It is
-- mounted into the Postgres container's /docker-entrypoint-initdb.d so the
-- schema is created automatically on first `docker compose up`. The app also
-- calls Base.metadata.create_all() defensively, so either path works.

CREATE TABLE IF NOT EXISTS crypto_history (
    id          BIGSERIAL PRIMARY KEY,
    coin_id     VARCHAR(100)   NOT NULL,
    date        DATE           NOT NULL,
    price_usd   NUMERIC(30, 10),
    raw_json    JSONB          NOT NULL,
    created_at  TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ    NOT NULL DEFAULT now(),
    CONSTRAINT uq_crypto_history_coin_date UNIQUE (coin_id, date)
);

CREATE INDEX IF NOT EXISTS ix_crypto_history_coin_id ON crypto_history (coin_id);

CREATE TABLE IF NOT EXISTS crypto_monthly_stats (
    id             BIGSERIAL PRIMARY KEY,
    coin_id        VARCHAR(100)  NOT NULL,
    year           INTEGER       NOT NULL,
    month          INTEGER       NOT NULL,
    min_price_usd  NUMERIC(30, 10),
    max_price_usd  NUMERIC(30, 10),
    updated_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT uq_crypto_monthly_coin_year_month UNIQUE (coin_id, year, month)
);

CREATE INDEX IF NOT EXISTS ix_crypto_monthly_coin_id ON crypto_monthly_stats (coin_id);
