"""Database engine and session management.

A single :class:`Database` instance owns the SQLAlchemy engine and hands out
short-lived sessions through a context manager. Each unit of work gets its own
session, which keeps the code safe to use from multiple threads during a
concurrent backfill.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import DatabaseConfig
from app.database.models import Base
from app.errors import DatabaseError

logger = logging.getLogger(__name__)


class Database:
    """Owns the engine/session factory for a single PostgreSQL database."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        try:
            self._engine: Engine = create_engine(config.url, pool_pre_ping=True, future=True)
        except SQLAlchemyError as exc:  # pragma: no cover - construction rarely fails
            raise DatabaseError(f"Could not create database engine: {exc}") from exc
        self._session_factory = sessionmaker(bind=self._engine, future=True, expire_on_commit=False)

    @property
    def engine(self) -> Engine:
        return self._engine

    def create_all(self) -> None:
        """Create the tables if they do not already exist (idempotent)."""
        try:
            Base.metadata.create_all(self._engine)
        except SQLAlchemyError as exc:
            raise DatabaseError(f"Database connection error while creating tables: {exc}") from exc
        logger.info("Database schema is ready")

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Provide a transactional session scope.

        Commits on success, rolls back on error, and always closes the session.
        """
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            raise DatabaseError(f"Database error: {exc}") from exc
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        """Release the connection pool."""
        self._engine.dispose()
