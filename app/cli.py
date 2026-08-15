"""Command-line interface — the application's composition root.

Wires the concrete collaborators together and exposes three subcommands:

* ``download``  — process one coin/date;
* ``backfill``  — process an inclusive date range (optionally concurrent);
* ``daily``     — process yesterday for the default coin set (bitcoin,
  ethereum, cardano); intended for the 03:00 CRON job.

Every command accepts ``--database`` to enable PostgreSQL persistence.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from app import __version__
from app.api.coingecko_client import CoinGeckoClient
from app.config import Settings, get_settings
from app.database.connection import Database
from app.errors import AppError
from app.logging_config import configure_logging
from app.services.backfill_service import BackfillService
from app.services.crypto_service import CryptoService
from app.storage.file_storage import FileStorage
from app.utils.dates import parse_iso_date

logger = logging.getLogger(__name__)

DEFAULT_DAILY_COINS = ["bitcoin", "ethereum", "cardano"]


# --------------------------------------------------------------------------- #
# Wiring helpers
# --------------------------------------------------------------------------- #
def _build_database(settings: Settings) -> Database:
    """Create a Database and ensure the schema exists."""
    database = Database(settings.database)
    database.create_all()
    return database


def _build_service(settings: Settings, use_database: bool) -> CryptoService:
    client = CoinGeckoClient(settings.coingecko)
    storage = FileStorage(settings.data_dir)
    database = _build_database(settings) if use_database else None
    return CryptoService(client=client, storage=storage, database=database)


# --------------------------------------------------------------------------- #
# Command handlers
# --------------------------------------------------------------------------- #
def _cmd_download(args: argparse.Namespace, settings: Settings) -> int:
    on_date = parse_iso_date(args.date)
    service = _build_service(settings, args.database)
    result = service.process_date(args.coin, on_date, persist=args.database)
    print(
        f"{result.coin_id} {result.date.isoformat()}: "
        f"price_usd={result.price_usd} file={result.file_path} "
        f"persisted={result.persisted}"
    )
    return 0


def _cmd_backfill(args: argparse.Namespace, settings: Settings) -> int:
    start = parse_iso_date(args.start_date)
    end = parse_iso_date(args.end_date)
    service = _build_service(settings, args.database)
    backfill = BackfillService(service)
    summary = backfill.run(
        coin_id=args.coin,
        start=start,
        end=end,
        persist=args.database,
        workers=args.workers,
    )
    print(
        f"{summary.coin_id}: {summary.succeeded}/{summary.total} succeeded, "
        f"{summary.failure_count} failed"
    )
    for iso_date, message in sorted(summary.failed.items()):
        print(f"  FAILED {iso_date}: {message}")
    return 0 if summary.failure_count == 0 else 1


def _cmd_daily(args: argparse.Namespace, settings: Settings) -> int:
    on_date: date = parse_iso_date(args.date)
    coins: list[str] = args.coins or DEFAULT_DAILY_COINS
    service = _build_service(settings, args.database)

    exit_code = 0
    for coin in coins:
        try:
            result = service.process_date(coin, on_date, persist=args.database)
            print(
                f"{result.coin_id} {result.date.isoformat()}: "
                f"price_usd={result.price_usd} persisted={result.persisted}"
            )
        except AppError as exc:
            logger.error("Daily run failed for %s on %s: %s", coin, on_date.isoformat(), exc)
            exit_code = 1
    return exit_code


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="app",
        description="Collect CoinGecko historical crypto prices into files and PostgreSQL.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--log-level",
        default=None,
        help="Override log level (DEBUG, INFO, WARNING, ERROR). Defaults to LOG_LEVEL env.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # download
    download = subparsers.add_parser("download", help="Process one coin/date.")
    download.add_argument("--coin", required=True, help="Coin id, e.g. bitcoin.")
    download.add_argument(
        "--date", required=True, help="ISO date (YYYY-MM-DD), or 'today'/'yesterday'."
    )
    download.add_argument(
        "--database", action="store_true", help="Persist the result to PostgreSQL."
    )
    download.set_defaults(func=_cmd_download)

    # backfill
    backfill = subparsers.add_parser("backfill", help="Process an inclusive date range.")
    backfill.add_argument("--coin", required=True, help="Coin id, e.g. bitcoin.")
    backfill.add_argument("--start-date", required=True, dest="start_date", help="ISO start date.")
    backfill.add_argument("--end-date", required=True, dest="end_date", help="ISO end date.")
    backfill.add_argument(
        "--database", action="store_true", help="Persist each date to PostgreSQL."
    )
    backfill.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Max concurrent requests (bonus). Default 1 (sequential).",
    )
    backfill.set_defaults(func=_cmd_backfill)

    # daily
    daily = subparsers.add_parser(
        "daily", help="Process the default coin set for a day (CRON entry point)."
    )
    daily.add_argument(
        "--date",
        default="yesterday",
        help="ISO date, or 'today'/'yesterday' (default: yesterday).",
    )
    daily.add_argument(
        "--coins",
        nargs="+",
        default=None,
        help=f"Coins to process (default: {' '.join(DEFAULT_DAILY_COINS)}).",
    )
    daily.add_argument(
        "--database",
        action="store_true",
        help="Persist to PostgreSQL (recommended for the CRON job).",
    )
    daily.set_defaults(func=_cmd_daily)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(args.log_level or settings.log_level)

    try:
        return args.func(args, settings)
    except AppError as exc:
        logger.error("%s: %s", type(exc).__name__, exc)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        logger.warning("Interrupted by user.")
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
