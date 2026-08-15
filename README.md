# CoinGecko — Data Engineering Pipeline

A small, reproducible data engineering pipeline in Python. It collects historical
cryptocurrency prices from the [CoinGecko API](https://www.coingecko.com/en/api),
stores the raw responses locally as JSON, and (optionally) persists them to
PostgreSQL while maintaining a monthly **MIN / MAX** price aggregate.

```text
CoinGecko API
     │
     ▼
Python CLI ──► Validation + Logging
     │
     ├──► Raw JSON file (data/<coin>/<coin>_<date>.json)
     │
     └──► PostgreSQL
             ├── crypto_history        (one row per coin/day, UPSERT)
             └── crypto_monthly_stats  (MIN/MAX USD price per coin/month)
```

---

## Table of contents

- [Objective](#objective)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick start (Docker)](#quick-start-docker)
- [Local install (without Docker)](#local-install-without-docker)
- [Configuration](#configuration)
- [Usage](#usage)
  - [download — one coin/date](#download--one-coindate)
  - [backfill — a range of dates](#backfill--a-range-of-dates)
  - [daily — the CRON entry point](#daily--the-cron-entry-point)
- [PostgreSQL persistence & UPSERT](#postgresql-persistence--upsert)
- [Database schema](#database-schema)
- [Scheduling with CRON](#scheduling-with-cron)
- [Running the tests](#running-the-tests)
- [Linting & formatting](#linting--formatting)
- [Design decisions](#design-decisions)
- [Assumptions](#assumptions)
- [Known limitations](#known-limitations)

---

## Objective

Given a **coin id** (e.g. `bitcoin`, `ethereum`, `cardano`) and a **date** (or a
date range), the application:

1. calls CoinGecko's `/coins/{id}/history?date=dd-mm-yyyy` endpoint (the ISO date
   supplied on the CLI is converted internally to CoinGecko's `dd-mm-yyyy`);
2. saves the raw JSON response to a local file whose name contains the date;
3. optionally UPSERTs a daily row into PostgreSQL and recalculates that month's
   min/max USD price;
4. logs every step and every error.

The same unit of work (`CryptoService.process_date`) powers the single-date,
daily and backfill flows — there is no duplicated logic.

## Architecture

The code is organised by responsibility (see `app/`):

| Layer | Module | Responsibility |
|-------|--------|----------------|
| CLI / composition root | `app/cli.py` | Parse args, wire dependencies, dispatch |
| API client | `app/api/coingecko_client.py` | HTTP calls, retries, 429/timeout handling, date conversion |
| Services | `app/services/crypto_service.py`, `backfill_service.py` | Orchestration; the shared `process_date`; concurrent backfill |
| Repository | `app/repositories/crypto_repository.py` | SQL: UPSERT + monthly MIN/MAX recompute |
| ORM models | `app/database/models.py` | `crypto_history`, `crypto_monthly_stats` |
| DB connection | `app/database/connection.py` | Engine + transactional session scope |
| Domain model | `app/models/crypto.py` | Framework-agnostic `CryptoHistory`, price extraction |
| File storage | `app/storage/file_storage.py` | Atomic raw-JSON writes |
| Config | `app/config.py` | Env-driven, immutable settings |
| Logging | `app/logging_config.py` | Central log format |
| Utils | `app/utils/dates.py` | ISO ↔ CoinGecko conversion, validation, ranges |

Dependencies are **injected** (API client, storage and database are passed into
the service), which keeps the business logic decoupled and easy to unit-test
with fakes.

## Prerequisites

- **Docker + Docker Compose** — recommended, gives you PostgreSQL + the app with
  zero manual setup; **or**
- **Python 3.8+** and a reachable PostgreSQL if you want to persist data without
  Docker.

A CoinGecko API key is **optional**. Without one the public API works but is
rate-limited and (on the free plan) only serves the **last ~365 days** of
historical data.

## Quick start (Docker)

```bash
git clone <repository-url>
cd CoinGecko
cp .env.example .env          # then edit POSTGRES_PASSWORD (and API key if you have one)

# Start PostgreSQL (schema auto-created from sql/001_create_tables.sql).
docker compose up -d postgres

# Build the app image and run a command. `docker compose run` executes the CLI.
docker compose build app
docker compose run --rm app download --coin bitcoin --date 2026-08-14 --database
```

Expected result: the raw JSON lands in `./data/bitcoin/bitcoin_2026-08-14.json`,
a row is UPSERTed into `crypto_history`, and `crypto_monthly_stats` is updated
for `2026-08`.

Backfill a range:

```bash
docker compose run --rm app backfill \
    --coin bitcoin --start-date 2026-08-01 --end-date 2026-08-14 --database --workers 5
```

Tear down (add `-v` to also drop the database volume):

```bash
docker compose down
```

## Local install (without Docker)

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt      # add -r requirements-dev.txt for tests/linters
cp .env.example .env                 # set POSTGRES_* to your database

# Optional: create the schema (the app also does this automatically with --database)
psql "postgresql://crypto_user:change_me@localhost:5432/crypto" -f sql/001_create_tables.sql

python -m app download --coin bitcoin --date 2026-08-14          # file only
python -m app download --coin bitcoin --date 2026-08-14 --database  # + PostgreSQL
```

## Configuration

All configuration comes from environment variables (loaded from `.env` if
present). Secrets never live in source control — only `.env.example` is
committed. See `.env.example` for the full list; the key ones:

| Variable | Default | Description |
|----------|---------|-------------|
| `COINGECKO_API_KEY` | *(empty)* | Optional API key; sent via the header below |
| `COINGECKO_API_BASE_URL` | `https://api.coingecko.com/api/v3` | Use the pro URL for paid plans |
| `COINGECKO_API_KEY_HEADER` | `x-cg-demo-api-key` | `x-cg-demo-api-key` (demo) or `x-cg-pro-api-key` (pro) |
| `COINGECKO_TIMEOUT_SECONDS` | `30` | Per-request timeout |
| `COINGECKO_MAX_RETRIES` | `3` | Retry attempts for 429/5xx/timeout |
| `COINGECKO_BACKOFF_SECONDS` | `1.5` | Base for exponential backoff |
| `DATA_DIR` | `data` | Where raw JSON files are written |
| `POSTGRES_HOST/PORT/DB/USER/PASSWORD` | see file | PostgreSQL connection |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

## Usage

Run `python -m app --help` (or any subcommand with `--help`) for the full
reference. `--database` is optional on every command; omit it to only write the
local file.

### download — one coin/date

```bash
python -m app download --coin bitcoin --date 2026-08-14
python -m app download --coin ethereum --date yesterday --database
```

`--date` accepts an ISO date (`YYYY-MM-DD`) or the aliases `today` / `yesterday`.

### backfill — a range of dates

```bash
python -m app backfill --coin bitcoin --start-date 2026-01-01 --end-date 2026-08-14 --database
```

**Bonus — concurrency.** `--workers N` runs up to `N` dates at once (bounded by a
thread pool, appropriate for I/O-bound HTTP work), while respecting the API's
rate limits via per-request retries/backoff:

```bash
python -m app backfill --coin bitcoin --start-date 2026-01-01 --end-date 2026-12-31 --workers 5
```

A failing date is logged and counted but does **not** abort the run; the command
prints a `succeeded/total` summary and exits non-zero if any date failed.

### daily — the CRON entry point

Processes the three default coins (`bitcoin`, `ethereum`, `cardano`) for a day
(default: yesterday) in a single invocation:

```bash
python -m app daily --database
python -m app daily --date 2026-08-14 --coins bitcoin ethereum --database
```

## PostgreSQL persistence & UPSERT

Re-running the same coin/date never creates duplicates. The daily row is written
with `INSERT ... ON CONFLICT (coin_id, date) DO UPDATE`, so a corrected price
overwrites the previous value. After each write the affected month's aggregate is
recomputed from the committed daily rows and UPSERTed into `crypto_monthly_stats`:

```text
new daily value
     │
     ▼
UPSERT crypto_history  (unique on coin_id + date)
     │
     ▼
recompute MIN(price), MAX(price) for that coin/year/month
     │
     ▼
UPSERT crypto_monthly_stats  (unique on coin_id + year + month)
```

MIN/MAX are recomputed (not merged incrementally) so that lowering a previously
stored maximum is handled correctly.

## Database schema

`sql/001_create_tables.sql` (mirrored by the SQLAlchemy models):

**`crypto_history`**

| column | type | notes |
|--------|------|-------|
| `id` | BIGSERIAL | PK |
| `coin_id` | VARCHAR(100) | indexed |
| `date` | DATE | |
| `price_usd` | NUMERIC(30,10) | nullable |
| `raw_json` | JSONB | full CoinGecko response |
| `created_at` / `updated_at` | TIMESTAMPTZ | |
| — | UNIQUE | `(coin_id, date)` |

**`crypto_monthly_stats`**

| column | type | notes |
|--------|------|-------|
| `id` | BIGSERIAL | PK |
| `coin_id` | VARCHAR(100) | indexed |
| `year` / `month` | INTEGER | |
| `min_price_usd` / `max_price_usd` | NUMERIC(30,10) | nullable |
| `updated_at` | TIMESTAMPTZ | |
| — | UNIQUE | `(coin_id, year, month)` |

## Scheduling with CRON

The daily job is meant to run at **03:00**. A ready-to-edit template lives in
[`deploy/crontab.example`](deploy/crontab.example). The core line:

```cron
0 3 * * * cd /path/to/CoinGecko && /path/to/CoinGecko/.venv/bin/python -m app daily --database >> /var/log/coingecko.log 2>&1
```

Install it with `crontab deploy/crontab.example` (after fixing the paths). The
file also documents a Docker Compose variant and an equivalent one-line-per-coin
form.

## Running the tests

```bash
pip install -r requirements-dev.txt
pytest
```

The default suite uses **mocked** CoinGecko responses and needs no network or
database. The repository integration tests (UPSERT + monthly MIN/MAX) require a
real PostgreSQL and **skip automatically** when one isn't configured. To run them:

```bash
docker compose up -d postgres
export TEST_DATABASE_URL=postgresql+psycopg2://crypto_user:change_me@localhost:5432/crypto
pytest tests/test_repository.py
```

## Linting & formatting

```bash
ruff check app tests      # lint (pyflakes, isort, pyupgrade, bugbear, …)
black app tests           # format (line length 100)
```

Configuration lives in `pyproject.toml`.

## Design decisions

- **Layered, dependency-injected architecture.** The CLI is a thin composition
  root; business logic lives in services that receive their collaborators. This
  keeps modules cohesive (SRP), swappable (DIP) and unit-testable without I/O.
- **One shared unit of work.** `process_date(coin, date, persist)` is reused by
  `download`, `daily` and `backfill`, avoiding divergent code paths.
- **Raw JSON is preserved verbatim** (and stored in `raw_json`), so data can
  always be re-processed if extraction logic changes.
- **Idempotent by design.** UPSERTs on natural keys make every command safe to
  re-run; monthly stats are always recomputed from source rows.
- **Resilient HTTP.** Bounded retries with exponential backoff handle timeouts,
  HTTP 429 (honouring `Retry-After`) and 5xx; 404 maps to a clear "invalid coin"
  error.
- **Threads for concurrency.** The workload is I/O-bound, so a bounded
  `ThreadPoolExecutor` gives real speed-up with a configurable limit; each worker
  uses its own DB session for thread safety.

## Assumptions

- Dates are interpreted in **UTC** (so `yesterday` = UTC yesterday).
- The USD price is read from `market_data.current_price.usd`. For dates before a
  coin traded, `market_data` may be absent — the raw file is still saved and
  `price_usd` is stored as `NULL` (ignored by MIN/MAX). A payload missing even
  the `id` field is treated as malformed.
- On the **free/public** CoinGecko plan, historical data is limited to the last
  ~365 days; older dates return an error from the API. Supply a paid key and set
  `COINGECKO_API_BASE_URL` / `COINGECKO_API_KEY_HEADER` accordingly for deeper
  history.
- `NUMERIC(30,10)` is assumed to be wide enough for any USD price.

## Known limitations

- **Concurrent same-month writes.** During a highly concurrent backfill, two
  workers recomputing the *same* month at the same instant could briefly race on
  the `crypto_monthly_stats` row. Because every daily write triggers a fresh
  recompute from committed data, the aggregate converges to the correct value;
  for strict correctness under heavy concurrency, run one worker per month or
  serialise the monthly update.
- Retries use a fixed backoff schedule rather than a global rate-limiter; for
  very large backfills on the free tier, keep `--workers` modest.
- No historical **migration tool** (e.g. Alembic) — the schema is created from a
  single SQL file / `create_all()`, which is sufficient for this scope.
```
